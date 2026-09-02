"""Build reproducible, sanitized receipts for the hourly/realtime trial."""

from __future__ import annotations

import hashlib
import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from config import REALTIME_SOURCE_TYPES
from db.models import Article, CollectorRun, SourceRegistry

logger = logging.getLogger(__name__)

_REQUIRED_SMOKE_FIELDS = ("source", "source_id", "title", "url", "published_at")


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _iso(value: datetime | None) -> str | None:
    return _utc_naive(value).isoformat() if value else None


def _lane_for_source(
    source_type: str,
    source_key: str | None,
    registry_by_key: dict[str, SourceRegistry],
    realtime_types: set[str],
) -> str:
    if source_key and source_key in registry_by_key:
        return getattr(registry_by_key[source_key], "lane", "hourly")
    return "realtime" if source_type in realtime_types else "hourly"


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction, 3)


def _latency_summary(articles: list[Article]) -> dict[str, Any]:
    latencies: list[float] = []
    for article in articles:
        if article.published_at is None or article.collected_at is None:
            continue
        delta = (
            _utc_naive(article.collected_at) - _utc_naive(article.published_at)
        ).total_seconds()
        if delta >= 0:
            latencies.append(delta)
    return {
        "count": len(latencies),
        "p50_seconds": _percentile(latencies, 0.50),
        "p95_seconds": _percentile(latencies, 0.95),
        "max_seconds": round(max(latencies), 3) if latencies else None,
    }


def _timestamp_metrics(articles: list[Article], runs: list[CollectorRun]) -> dict[str, Any]:
    persisted_missing = 0
    persisted_invalid = 0
    for article in articles:
        if article.published_at is None:
            persisted_missing += 1
        elif (
            article.collected_at
            and _utc_naive(article.published_at) > _utc_naive(article.collected_at)
        ):
            persisted_invalid += 1

    observed_missing = sum(
        max(getattr(run, "articles_missing_timestamp", 0) or 0, 0)
        for run in runs
    )
    observed_invalid = sum(
        max(getattr(run, "articles_invalid_timestamp", 0) or 0, 0)
        for run in runs
    )
    timestamp_error_runs = sum(
        1
        for run in runs
        if run.error_category == "parse"
        and re.search(r"time|date|timestamp", run.error_message or "", re.IGNORECASE)
    )
    missing = max(observed_missing, persisted_missing)
    invalid = max(observed_invalid, persisted_invalid)
    total_observations = sum(max(run.articles_fetched or 0, 0) for run in runs) or len(articles)
    timestamped = max(total_observations - missing - invalid, 0)
    completeness = timestamped / total_observations if total_observations else None
    return {
        "missing_timestamps": missing,
        "invalid_timestamps": invalid,
        "persisted_missing_timestamps": persisted_missing,
        "persisted_invalid_timestamps": persisted_invalid,
        "timestamp_error_runs": timestamp_error_runs,
        "timestamped_rows": timestamped,
        "timestamp_completeness": round(completeness, 4) if completeness is not None else None,
    }


def _source_health(
    sources: list[SourceRegistry],
    runs: list[CollectorRun],
    articles: list[Article],
    window_end: datetime,
    realtime_types: set[str],
) -> list[dict[str, Any]]:
    latest_runs: dict[str, CollectorRun] = {}
    for run in runs:
        key = run.source_key or f"type:{run.source_type}"
        if key not in latest_runs or run.completed_at > latest_runs[key].completed_at:
            latest_runs[key] = run

    latest_articles: dict[str, Article] = {}
    for article in articles:
        if (
            article.source not in latest_articles
            or article.collected_at > latest_articles[article.source].collected_at
        ):
            latest_articles[article.source] = article

    result: list[dict[str, Any]] = []
    for source in sources:
        lane = getattr(source, "lane", "hourly")
        if source.source_type in realtime_types and lane == "hourly":
            lane = "realtime"
        run = latest_runs.get(source.source_key) or latest_runs.get(f"type:{source.source_type}")
        article = latest_articles.get(source.source_type)
        evidence_status = "observed"
        if not source.is_active:
            status = "disabled"
            evidence_status = "disabled"
        elif run is not None and run.status != "ok":
            status = "failed"
            evidence_status = "failed_attempt"
        elif run is not None and (run.articles_fetched or 0) == 0:
            status = "stale"
            evidence_status = "empty_success"
        elif run is not None and (
            (getattr(run, "articles_missing_timestamp", 0) or 0)
            + (getattr(run, "articles_invalid_timestamp", 0) or 0)
        ) > 0:
            status = "stale"
            evidence_status = "timestamp_quality_issue"
        elif run is not None and article is None:
            status = "failed"
            evidence_status = "run_without_persisted_item"
        elif run is None and article is None:
            status = "stale"
            evidence_status = "no_evidence"
        else:
            latest_at = article.collected_at if article is not None else None
            age_hours = (
                (_utc_naive(window_end) - _utc_naive(latest_at)).total_seconds() / 3600
                if latest_at is not None
                else None
            )
            expected = source.expected_freshness_hours or (0.1 if lane == "realtime" else 4.0)
            if age_hours is None:
                status = "stale"
                evidence_status = "no_persisted_item"
            elif age_hours <= expected:
                status = "healthy"
            elif age_hours <= expected * 2:
                status = "stale"
            else:
                status = "failed"
        result.append({
            "source_key": source.source_key,
            "source_type": source.source_type,
            "lane": lane,
            "status": status,
            "evidence_status": evidence_status,
            "last_attempt_at": _iso(run.completed_at) if run else None,
            "last_success_at": _iso(run.completed_at) if run and run.status == "ok" else None,
            "last_item_at": _iso(article.collected_at) if article else None,
        })
    return result


def _fingerprint(article: Article) -> str:
    title = re.sub(r"\s+", " ", (article.title or "").strip().lower())
    published = _iso(article.published_at) or ""
    url = (article.url or "").strip().lower()
    raw = "|".join((title, published, url if not title else ""))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _comparison(articles: list[Article]) -> dict[str, Any]:
    groups: dict[str, list[Article]] = defaultdict(list)
    for article in articles:
        groups[_fingerprint(article)].append(article)

    overlap_items: list[dict[str, Any]] = []
    cross_source_evidence_items: list[dict[str, Any]] = []
    for fingerprint, group in groups.items():
        lanes = sorted({getattr(article, "collection_lane", "hourly") for article in group})
        sources = sorted({article.source for article in group})
        if len(lanes) > 1 or len(sources) > 1:
            evidence = {
                "fingerprint": fingerprint,
                "lanes": lanes,
                "sources": sources,
                "observations": len(group),
            }
            if len(lanes) > 1:
                overlap_items.append(evidence)
            if len(sources) > 1:
                cross_source_evidence_items.append(evidence)

    return {
        "observed_rows": len(articles),
        "independent_event_count": len(groups),
        "cross_lane_overlap_count": len(overlap_items),
        "cross_source_evidence_count": len(cross_source_evidence_items),
        "cross_source_evidence_items": cross_source_evidence_items,
        "overlap_items": overlap_items,
    }


def _lane_metrics(
    lane: str,
    articles: list[Article],
    runs: list[CollectorRun],
    window_end: datetime,
) -> dict[str, Any]:
    raw_rows = sum(max(run.articles_fetched or 0, 0) for run in runs)
    unique_ids = {
        article.source_id or f"article:{article.id}"
        for article in articles
    }
    unique_rows = len(unique_ids)
    new_rows = sum(max(run.articles_saved or 0, 0) for run in runs)
    if not runs:
        raw_rows = unique_rows
        new_rows = unique_rows
        duplicate_rows = 0
        save_failures = 0
        unclassified_not_saved_rows = 0
        evidence_status = "no_evidence" if not articles else "article_only"
    else:
        duplicate_rows = sum(max(getattr(run, "articles_duplicate", 0) or 0, 0) for run in runs)
        save_failures = sum(max(getattr(run, "articles_failed", 0) or 0, 0) for run in runs)
        unclassified_not_saved_rows = max(raw_rows - new_rows - duplicate_rows - save_failures, 0)
        if raw_rows == 0 and all(run.status == "ok" for run in runs):
            evidence_status = "empty_success"
        elif unclassified_not_saved_rows:
            evidence_status = "partial_unclassified_loss"
        else:
            evidence_status = "observed"
    latest_collected = max((article.collected_at for article in articles), default=None)
    latest_success = max(
        (run.completed_at for run in runs if run.status == "ok"),
        default=None,
    )
    # A successful run is not data freshness. An empty/blocked response must
    # remain visible instead of borrowing the run completion timestamp.
    freshness_at = latest_collected
    freshness_age = (
        max((_utc_naive(window_end) - _utc_naive(freshness_at)).total_seconds(), 0)
        if freshness_at is not None
        else None
    )
    metrics = {
        "lane": lane,
        "run_count": len(runs),
        "evidence_status": evidence_status,
        "source_types": sorted(
            {article.source for article in articles}
            | {run.source_type for run in runs}
        ),
        "raw_rows": raw_rows,
        "unique_rows": unique_rows,
        "new_rows": new_rows,
        "duplicate_rows": duplicate_rows,
        "save_failures": save_failures,
        "unclassified_not_saved_rows": unclassified_not_saved_rows,
        "unique_rows_basis": "distinct persisted source_id values in the observation window",
        "source_failures": sum(1 for run in runs if run.status != "ok"),
        "last_success_at": _iso(latest_success),
        "freshness_age_seconds": round(freshness_age, 3) if freshness_age is not None else None,
        "latency": _latency_summary(articles),
    }
    metrics.update(_timestamp_metrics(articles, runs))
    metrics["failures"] = metrics["source_failures"]
    metrics["missing_or_invalid_timestamps"] = (
        metrics["missing_timestamps"] + metrics["invalid_timestamps"]
    )
    return metrics


def build_dual_run_receipt(
    session: Session,
    *,
    window_start: datetime,
    window_end: datetime,
) -> dict[str, Any]:
    """Build a deterministic receipt from persisted observations and runs."""
    start = _utc_naive(window_start)
    end = _utc_naive(window_end)
    if end <= start:
        raise ValueError("window_end must be after window_start")

    # Include inactive rows so an explicitly disabled realtime source is
    # visible in the receipt as disabled/no-evidence rather than disappearing.
    sources = session.query(SourceRegistry).all()
    registry_by_key = {source.source_key: source for source in sources}
    realtime_types = set(REALTIME_SOURCE_TYPES) | {
        source.source_type for source in sources if getattr(source, "lane", "hourly") == "realtime"
    }
    runs = session.query(CollectorRun).filter(
        CollectorRun.completed_at >= start,
        CollectorRun.completed_at <= end,
    ).all()
    articles = session.query(Article).filter(
        Article.collected_at >= start,
        Article.collected_at <= end,
    ).all()

    runs_by_lane: dict[str, list[CollectorRun]] = {"hourly": [], "realtime": []}
    for run in runs:
        lane = _lane_for_source(run.source_type, run.source_key, registry_by_key, realtime_types)
        runs_by_lane.setdefault(lane, []).append(run)
    articles_by_lane: dict[str, list[Article]] = {"hourly": [], "realtime": []}
    for article in articles:
        lane = getattr(article, "collection_lane", "hourly")
        articles_by_lane.setdefault(lane, []).append(article)

    health = _source_health(sources, runs, articles, end, realtime_types)
    return {
        "schema_version": "dual_run_receipt.v1",
        "state": "dual_run",
        "window": {
            "start": _iso(start),
            "end": _iso(end),
            "duration_seconds": round((end - start).total_seconds(), 3),
        },
        "lanes": {
            lane: _lane_metrics(
                lane,
                articles_by_lane.get(lane, []),
                runs_by_lane.get(lane, []),
                end,
            )
            for lane in ("hourly", "realtime")
        },
        "comparison": _comparison(articles),
        "source_health": health,
        "convergence": {
            "eligible": False,
            "status": "not_ready",
            "reason": (
                "This receipt measures dual-run evidence; it never enables "
                "canonical-lane switching."
            ),
            "required_evidence": [
                "multiple bounded trial windows",
                "real-time latency and persistence completeness",
                "duplicate and cross-source evidence behavior",
                "source health without unresolved failures",
                "hourly comparison and digest usefulness",
                "explicit human approval for canonical_realtime",
            ],
        },
    }


def _default_smoke_fetchers() -> dict[str, Callable[[], list[dict[str, Any]]]]:
    from collectors.realtime_news import fetch_cls_telegraph, fetch_eastmoney_global_news
    from collectors.sec_edgar import fetch_sec_edgar_filings
    from config import REALTIME_SOURCE_BOOTSTRAP

    sec_config = next(
        entry.get("config", {})
        for entry in REALTIME_SOURCE_BOOTSTRAP
        if entry["source"] == "sec_edgar"
    )

    return {
        "cls_telegraph": fetch_cls_telegraph,
        "eastmoney_global_news": fetch_eastmoney_global_news,
        "sec_edgar": lambda: fetch_sec_edgar_filings(
            tickers=[str(value) for value in sec_config.get("tickers", [])],
            forms=[str(value) for value in sec_config.get("forms", [])],
            cik_map=sec_config.get("cik_map"),
        ),
    }


def run_live_smoke(
    fetchers: dict[str, Callable[[], list[dict[str, Any]]]] | None = None,
) -> dict[str, Any]:
    """Call each realtime provider once without persisting full responses."""
    fetchers = fetchers or _default_smoke_fetchers()
    results: dict[str, Any] = {}
    for source_type, fetcher in fetchers.items():
        started = time.monotonic()
        try:
            rows = fetcher()
            collected_at = datetime.now(timezone.utc).isoformat()
            if not isinstance(rows, list):
                raise TypeError("normalized result is not a list")
            if not rows:
                results[source_type] = {
                    "status": "empty",
                    "rows": 0,
                    "schema_valid": False,
                    "collected_at": collected_at,
                    "latency_ms": round((time.monotonic() - started) * 1000, 3),
                    "error_type": "EmptyResponse",
                }
                continue
            schema_valid = all(
                isinstance(row, dict) and all(field in row for field in _REQUIRED_SMOKE_FIELDS)
                for row in rows
            )
            if not schema_valid:
                raise ValueError("normalized row is missing a required field")
            timestamped = sum(1 for row in rows if row.get("published_at") is not None)
            results[source_type] = {
                "status": "ok",
                "rows": len(rows),
                "timestamped_rows": timestamped,
                "timestamp_completeness": round(timestamped / len(rows), 4) if rows else None,
                "schema_valid": True,
                "collected_at": collected_at,
                "latency_ms": round((time.monotonic() - started) * 1000, 3),
            }
        except Exception as exc:
            collected_at = datetime.now(timezone.utc).isoformat()
            logger.warning("Live smoke failed for %s (%s)", source_type, type(exc).__name__)
            results[source_type] = {
                "status": "failed",
                "rows": 0,
                "schema_valid": False,
                "collected_at": collected_at,
                "latency_ms": round((time.monotonic() - started) * 1000, 3),
                "error_type": type(exc).__name__,
            }
    statuses = {item["status"] for item in results.values()}
    status = "ok" if statuses == {"ok"} else ("partial_failure" if "ok" in statuses else "failed")
    return {
        "status": status,
        "sources": results,
        "contains_full_responses": False,
    }
