"""APScheduler-based collector scheduler for park-intel.

Registry-driven: loads active source records from the source registry,
groups by source_type, and dispatches through the adapter layer.
Integrates with FastAPI lifespan for clean startup/shutdown.
"""
from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollectorResult:
    """Immutable result of a single collector run."""

    source: str
    articles_fetched: int
    articles_saved: int
    duration_seconds: float
    error: str | None
    timestamp: str


@dataclass(frozen=True)
class SchedulerConfig:
    """Immutable scheduler configuration.

    Per-source intervals are defined in the source registry (single source of truth).
    Only non-source parameters live here.
    """

    llm_tagger_interval_hours: int = 4
    timezone: str = "Asia/Shanghai"


# Module-level storage for last run results (read by health endpoint)
_last_results: dict[str, CollectorResult] = {}

# Provider blocks are intentionally process-local and short-lived. The
# realtime lane is opt-in, and an explicit 403/429/451 pauses only that source
# type instead of retrying unattended on every minute tick.
_realtime_blocked_until: dict[str, datetime] = {}
_REALTIME_BLOCK_COOLDOWN_SECONDS = 15 * 60

# Heartbeat: updated every 5 minutes, checked by health endpoints
_heartbeat_ts: datetime | None = None

# Process start time: detects restart loops (if uptime < 10 min, something is wrong)
_process_start_ts: datetime = datetime.now(timezone.utc)


def get_heartbeat() -> datetime | None:
    """Return the last heartbeat timestamp, or None if never set."""
    return _heartbeat_ts


def get_process_start() -> datetime:
    """Return when this process started (UTC)."""
    return _process_start_ts


def get_uptime_seconds() -> float:
    """Return seconds since process start."""
    return (datetime.now(timezone.utc) - _process_start_ts).total_seconds()


def _update_heartbeat() -> None:
    """Update the heartbeat timestamp to now (UTC)."""
    global _heartbeat_ts
    _heartbeat_ts = datetime.now(timezone.utc)


def get_last_results() -> dict[str, CollectorResult]:
    """Get the last run result for each collector."""
    return dict(_last_results)


def _record_collector_run(
    result,
    *,
    saved_count: int,
    duplicate_count: int = 0,
    failed_count: int = 0,
    missing_timestamp_count: int = 0,
    invalid_timestamp_count: int = 0,
) -> None:
    """Write a CollectorRun row to the database (RELY-07)."""
    from db.database import get_session
    from db.models import CollectorRun

    session = get_session()
    try:
        run = CollectorRun(
            source_type=result.source_type,
            source_key=result.source_key,
            status=result.status,
            articles_fetched=result.articles_fetched,
            articles_saved=saved_count,
            articles_duplicate=duplicate_count,
            articles_failed=failed_count,
            articles_missing_timestamp=missing_timestamp_count,
            articles_invalid_timestamp=invalid_timestamp_count,
            duration_ms=result.duration_ms,
            error_message=result.error_message,
            error_category=result.error_category,
            retry_count=result.retry_count,
            completed_at=datetime.now(timezone.utc),
        )
        session.add(run)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to record CollectorRun for %s", result.source_key)
    finally:
        session.close()


def _realtime_lane_enabled() -> bool:
    from config import realtime_lane_enabled

    return realtime_lane_enabled()


def _is_realtime_blocked(source_type: str) -> bool:
    blocked_until = _realtime_blocked_until.get(source_type)
    if blocked_until is None:
        return False
    if datetime.now(timezone.utc) >= blocked_until:
        _realtime_blocked_until.pop(source_type, None)
        return False
    return True


def _mark_realtime_blocked(source_type: str) -> None:
    _realtime_blocked_until[source_type] = datetime.now(timezone.utc) + timedelta(
        seconds=_REALTIME_BLOCK_COOLDOWN_SECONDS
    )
    logger.error(
        "[%s] realtime lane paused for %ds after provider block; manual/operator retry required",
        source_type,
        _REALTIME_BLOCK_COOLDOWN_SECONDS,
    )


def reset_realtime_block(source_type: str | None = None) -> None:
    """Clear a process-local realtime provider pause after operator review."""
    if source_type is None:
        _realtime_blocked_until.clear()
    else:
        _realtime_blocked_until.pop(source_type, None)


def _cleanup_old_runs() -> None:
    """Delete collector_runs older than 30 days (D-14)."""
    from db.database import get_session
    from db.models import CollectorRun

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    session = get_session()
    try:
        deleted = session.query(CollectorRun).filter(
            CollectorRun.completed_at < cutoff
        ).delete()
        session.commit()
        if deleted:
            logger.info("Cleaned up %d old collector_runs rows", deleted)
    except Exception:
        session.rollback()
        logger.exception("Failed to clean up old collector_runs")
    finally:
        session.close()


def _cleanup_old_articles() -> None:
    """Delete articles older than 6 months to keep database size manageable."""
    from db.database import get_session
    from db.models import Article

    cutoff = datetime.now(timezone.utc) - timedelta(days=180)
    session = get_session()
    try:
        deleted = session.query(Article).filter(
            Article.collected_at < cutoff
        ).delete()
        session.commit()
        if deleted:
            logger.info("Cleaned up %d articles older than 6 months", deleted)
    except Exception:
        session.rollback()
        logger.exception("Failed to clean up old articles")
    finally:
        session.close()


def _run_source_type(source_type: str) -> None:
    """Run all active source instances of a given type through the adapter layer.

    Groups per-instance sources (rss, reddit, etc.) into a single scheduler job.
    Each instance is collected individually via the adapter, then articles are
    saved via BaseCollector.save().
    """
    from collectors.base import BaseCollector
    from db.database import get_session
    from sources.adapters import collect_from_source
    from sources.registry import list_active_sources

    start = time.time()
    session = get_session()
    try:
        active = list_active_sources(session)
        instances = [s for s in active if s.source_type == source_type]
    finally:
        session.close()

    if not instances:
        logger.warning("[%s] No active instances in registry — skipping", source_type)
        return

    from config import REALTIME_SOURCE_TYPES

    if any(getattr(instance, "lane", "hourly") == "realtime" for instance in instances):
        if not _realtime_lane_enabled():
            logger.warning(
                "[%s] realtime lane disabled; set REALTIME_LANE_ENABLED=1 "
                "after operator review",
                source_type,
            )
            return
        if _is_realtime_blocked(source_type):
            logger.warning("[%s] realtime lane remains paused after provider block", source_type)
            return

    total_fetched = 0
    total_saved = 0
    errors: list[str] = []

    for instance in instances:
        record = {
            "source_key": instance.source_key,
            "source_type": instance.source_type,
            "display_name": instance.display_name,
            "category": instance.category,
            "config_json": instance.config_json,
        }
        inst_start = time.time()
        try:
            articles, adapter_result = collect_from_source(record)
            fetched = len(articles)
            total_fetched += fetched
            saved = 0
            if articles:
                # Use a minimal collector to save (reuses BaseCollector.save dedup)
                saver = _ArticleSaver(source_type)
                saved = saver.save(articles)
                total_saved += saved
                save_stats = saver.last_save_stats
            else:
                save_stats = {
                    "duplicates": 0,
                    "errors": 0,
                    "missing_timestamps": 0,
                    "invalid_timestamps": 0,
                }
            if adapter_result.status != "ok":
                errors.append(
                    f"{instance.source_key}: "
                    f"{adapter_result.error_message or adapter_result.status}"
                )
            if save_stats["errors"]:
                errors.append(
                    f"{instance.source_key}: {save_stats['errors']} article save errors"
                )
            # Record to DB (RELY-07)
            _record_collector_run(
                adapter_result,
                saved_count=saved,
                duplicate_count=save_stats["duplicates"],
                failed_count=save_stats["errors"],
                missing_timestamp_count=save_stats["missing_timestamps"],
                invalid_timestamp_count=save_stats["invalid_timestamps"],
            )
            if adapter_result.error_category == "auth" and source_type in REALTIME_SOURCE_TYPES:
                if "provider blocked" in (adapter_result.error_message or ""):
                    _mark_realtime_blocked(source_type)
            elif adapter_result.status == "ok":
                _realtime_blocked_until.pop(source_type, None)
        except Exception as e:
            logger.exception("[%s] Instance %s failed", source_type, instance.source_key)
            errors.append(f"{instance.source_key}: {e}")
            # Record failure to DB even if something unexpected happened
            from sources.errors import CollectorResult as AdapterResult, categorize_error
            duration_ms = int((time.time() - inst_start) * 1000)
            category = categorize_error(e)
            fallback_result = AdapterResult(
                source_type=source_type,
                source_key=instance.source_key,
                status="error",
                articles_fetched=0,
                articles_saved=0,
                duration_ms=duration_ms,
                error_message=str(e)[:500],
                error_category=category.value,
                retry_count=0,
            )
            _record_collector_run(fallback_result, saved_count=0, failed_count=0)

    duration = round(time.time() - start, 1)
    error_msg = "; ".join(errors) if errors else None

    result = CollectorResult(
        source=source_type,
        articles_fetched=total_fetched,
        articles_saved=total_saved,
        duration_seconds=duration,
        error=error_msg,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    _last_results[source_type] = result

    if result.error:
        logger.error("[%s] PARTIAL FAILURE (%.1fs): %s", source_type, duration, error_msg[:200])
    elif total_fetched == 0:
        logger.warning("[%s] No articles fetched (%.1fs)", source_type, duration)
    else:
        logger.info(
            "[%s] OK — fetched=%d, saved=%d, instances=%d (%.1fs)",
            source_type, total_fetched, total_saved, len(instances), duration,
        )


class _ArticleSaver:
    """Minimal wrapper to reuse BaseCollector.save() without needing a full collector."""

    def __init__(self, source_type: str) -> None:
        from db.database import init_db
        init_db()
        self._source_type = source_type
        self.last_save_stats: dict[str, int] = {
            "duplicates": 0,
            "errors": 0,
            "missing_timestamps": 0,
            "invalid_timestamps": 0,
        }

    def save(self, articles: list[dict[str, Any]]) -> int:
        from collectors.base import BaseCollector

        class _Saver(BaseCollector):
            source = self._source_type

            def collect(self):
                return []

        saver = _Saver()
        saved = saver.save(articles)
        self.last_save_stats = {
            "duplicates": saver.last_save_stats.get("duplicates", 0),
            "errors": saver.last_save_stats.get("errors", 0),
            "missing_timestamps": saver.last_save_stats.get("missing_timestamps", 0),
            "invalid_timestamps": saver.last_save_stats.get("invalid_timestamps", 0),
        }
        return saved


def _run_llm_tagger() -> None:
    """Run the LLM tagger on the most recent unscored articles (scheduled mode: limit=500)."""
    try:
        from scripts.run_llm_tagger import run_tagger
        run_tagger(limit=500)
    except ImportError:
        logger.warning("LLM tagger script not found, skipping")
    except Exception as e:
        logger.exception("LLM tagger failed: %s", e)


def _run_realtime_triage() -> None:
    """Classify pending realtime items without entering hourly consumers."""
    if not _realtime_lane_enabled():
        return

    import json
    from db.database import get_session
    from db.models import Article
    from triage.realtime import RealtimeTriage
    from sqlalchemy import or_

    session = get_session()
    try:
        candidates = (
            session.query(Article)
            .filter(
                Article.collection_lane == "realtime",
                or_(
                    Article.triage_status.is_(None),
                    Article.triage_status.in_(["failed", "processing"]),
                ),
                Article.triage_attempts < 3,
            )
            .order_by(Article.collected_at.asc())
            .limit(10)
            .all()
        )
        if not candidates:
            return

        for article in candidates:
            article.triage_status = "processing"
            article.triage_attempts = (article.triage_attempts or 0) + 1
        session.commit()

        triage = RealtimeTriage(batch_size=len(candidates))
        results = triage.triage_batch([
            {
                "id": article.id,
                "source": article.source,
                "title": article.title,
                "content": article.content,
            }
            for article in candidates
        ])
        by_id = {result["id"]: result for result in results}
        if len(by_id) != len(candidates):
            raise ValueError("triage result count does not match candidate count")

        now = datetime.utcnow()
        for article in candidates:
            result = by_id[article.id]
            bucket = result["bucket"]
            if (
                article.source == "telegram_mtproto"
                and article.review_state == "needs_review"
            ):
                bucket = "watch"
            article.triage_bucket = bucket
            article.triage_status = "complete"
            article.triage_direction = result["direction"]
            article.triage_rationale = result["rationale"]
            article.triage_assets = json.dumps(result["affected_assets"], ensure_ascii=False)
            article.triage_watch_for = json.dumps(result["watch_for"], ensure_ascii=False)
            article.triage_scenario_bull = result["scenario_bull"]
            article.triage_scenario_bear = result["scenario_bear"]
            article.triage_model = triage.model_name
            article.triage_error = None
            article.triaged_at = now
        session.commit()
        logger.info(
            "[realtime-triage] completed=%d model=%s",
            len(candidates),
            triage.model_name,
        )
    except Exception as exc:
        session.rollback()
        now = datetime.utcnow()
        for article in candidates if "candidates" in locals() else []:
            article.triage_bucket = "unknown"
            article.triage_status = "failed"
            article.triage_direction = "unclear"
            article.triage_error = type(exc).__name__
            article.triaged_at = now
        if "candidates" in locals() and candidates:
            session.commit()
        logger.warning("[realtime-triage] failed (%s)", type(exc).__name__)
    finally:
        session.close()


def _run_event_aggregation() -> None:
    """Run event aggregation on recent articles."""
    from db.database import get_session
    from events.aggregator import run_aggregation

    session = get_session()
    try:
        run_aggregation(session)
    except Exception:
        logger.exception("Event aggregation failed")
    finally:
        session.close()


class CollectorScheduler:
    """Manages scheduled collector runs via registry-driven dispatch."""

    def __init__(self, config: SchedulerConfig | None = None) -> None:
        self._config = config or SchedulerConfig()
        self._scheduler = BackgroundScheduler(timezone=self._config.timezone)

    def start(self) -> None:
        """Register all jobs and start the scheduler."""
        self._check_dependencies()
        self._register_jobs()
        _update_heartbeat()
        self._log_boot_status()
        self._scheduler.start()
        logger.info("CollectorScheduler started with %d jobs", len(self._scheduler.get_jobs()))

    def _log_boot_status(self) -> None:
        """Log active/skipped sources and summary at boot time."""
        from api.health_routes import _REQUIRED_RESOURCES
        from db.database import get_session
        from db.models import SourceRegistry

        session = get_session()
        try:
            sources = session.query(SourceRegistry).all()
            active_count = 0
            skipped_count = 0

            for src in sources:
                if src.is_active:
                    # Check for missing env vars on active sources
                    resource = _REQUIRED_RESOURCES.get(src.source_type)
                    if resource is not None:
                        env_key, _ = resource
                        import os
                        if not os.environ.get(env_key, "").strip():
                            logger.warning(
                                "Source active but missing %s: %s (%s)",
                                env_key, src.display_name, src.source_type,
                            )
                    logger.info("Source active: %s (%s)", src.display_name, src.source_type)
                    active_count += 1
                else:
                    logger.warning(
                        "Source skipped: %s (%s) — inactive",
                        src.display_name,
                        src.source_type,
                    )
                    skipped_count += 1

            time_str = datetime.now(timezone.utc).isoformat()
            logger.info(
                "%d active sources, %d skipped, scheduler started at %s",
                active_count, skipped_count, time_str,
            )
        finally:
            session.close()

    def shutdown(self) -> None:
        """Gracefully stop the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("CollectorScheduler stopped")

    def _check_dependencies(self) -> None:
        """Log warnings for missing optional dependencies."""
        try:
            import playwright  # noqa: F401
            logger.info("Playwright available — Xueqiu KOL feeds enabled")
        except ImportError:
            logger.warning("Playwright not installed — Xueqiu KOL feeds DISABLED")

        clawfeed_path = shutil.which("clawfeed") or shutil.which(
            "clawfeed", path="/opt/homebrew/bin:/usr/local/bin"
        )
        if clawfeed_path:
            logger.info("clawfeed CLI found at %s — social_kol collector enabled", clawfeed_path)
        else:
            logger.warning(
                "clawfeed CLI not found — social_kol collector will return empty results"
            )

    def _register_jobs(self) -> None:
        """Register collector jobs from the source registry + llm_tagger.

        The source registry is the single source of truth for source types
        and intervals. One job is created per source_type (not per instance).
        """
        from db.database import get_session
        from sources.registry import list_active_sources

        session = get_session()
        try:
            active = list_active_sources(session)
        finally:
            session.close()

        # Keep realtime sources out of the legacy hourly grouping. During the
        # migration both lanes write to the same Article table, but only the
        # realtime jobs use second-level cadence.
        type_intervals: dict[str, int] = {}
        realtime_intervals: dict[str, int] = {}
        for src in active:
            lane = getattr(src, "lane", "hourly")
            if lane == "realtime":
                if not _realtime_lane_enabled():
                    logger.info(
                        "Realtime source %s is registered but disabled; set "
                        "REALTIME_LANE_ENABLED=1 to start it",
                        src.source_type,
                    )
                    continue
                seconds = getattr(src, "schedule_seconds", None)
                if seconds is not None and seconds > 0:
                    if (
                        src.source_type not in realtime_intervals
                        or seconds < realtime_intervals[src.source_type]
                    ):
                        realtime_intervals[src.source_type] = seconds
                continue
            hours = getattr(src, "schedule_hours", None)
            if hours is not None and hours > 0:
                if src.source_type not in type_intervals or hours < type_intervals[src.source_type]:
                    type_intervals[src.source_type] = hours

        jobs: list[tuple[str, int]] = []
        for source_type, hours in sorted(type_intervals.items()):
            jobs.append((source_type, hours))

        # LLM tagger is not a data source; add it separately
        base_time = datetime.now(timezone.utc)
        for idx, (source_type, hours) in enumerate(jobs):
            staggered_start = base_time + timedelta(seconds=30 * idx)
            self._scheduler.add_job(
                _run_source_type,
                args=[source_type],
                trigger=IntervalTrigger(hours=hours),
                id=f"collector-{source_type}",
                replace_existing=True,
                next_run_time=staggered_start,
            )
            logger.info("Registered collector job: %s (every %dh, first run at +%ds)",
                         source_type, hours, 30 * idx)

        realtime_start = base_time + timedelta(seconds=30 * len(jobs))
        for idx, (source_type, seconds) in enumerate(sorted(realtime_intervals.items())):
            staggered_start = realtime_start + timedelta(seconds=30 * idx)
            self._scheduler.add_job(
                _run_source_type,
                args=[source_type],
                trigger=IntervalTrigger(seconds=seconds),
                id=f"realtime-{source_type}",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=30,
                next_run_time=staggered_start,
            )
            logger.info(
                "Registered realtime collector job: %s (every %ds, first run at +%ds)",
                source_type,
                seconds,
                30 * len(jobs) + 30 * idx,
            )

        if realtime_intervals:
            self._scheduler.add_job(
                _run_realtime_triage,
                trigger=IntervalTrigger(seconds=30),
                id="realtime-triage",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=30,
                next_run_time=base_time + timedelta(seconds=15),
            )
            logger.info("Registered realtime triage job (every 30s)")

        # LLM tagger
        tagger_start = base_time + timedelta(seconds=30 * (len(jobs) + len(realtime_intervals)))
        self._scheduler.add_job(
            _run_llm_tagger,
            trigger=IntervalTrigger(hours=self._config.llm_tagger_interval_hours),
            id="collector-llm_tagger",
            replace_existing=True,
            next_run_time=tagger_start,
        )
        logger.info("Registered LLM tagger job (every %dh)", self._config.llm_tagger_interval_hours)

        # Event aggregation (every 1 hour)
        aggregation_start = base_time + timedelta(
            seconds=30 * (len(jobs) + len(realtime_intervals) + 1)
        )
        self._scheduler.add_job(
            _run_event_aggregation,
            trigger=IntervalTrigger(hours=1),
            id="event-aggregation",
            replace_existing=True,
            next_run_time=aggregation_start,
        )
        logger.info("Registered event aggregation job (every 1h)")

        # Heartbeat update (every 5 minutes)
        self._scheduler.add_job(
            _update_heartbeat,
            trigger=IntervalTrigger(minutes=5),
            id="heartbeat",
            name="Heartbeat update",
            replace_existing=True,
        )
        logger.info("Registered heartbeat job (every 5min)")

        # Cleanup old collector runs (weekly, D-14)
        self._scheduler.add_job(
            _cleanup_old_runs,
            trigger=IntervalTrigger(weeks=1, timezone=self._config.timezone),
            id="cleanup_old_runs",
            name="Cleanup old collector runs",
            replace_existing=True,
        )
        logger.info("Registered cleanup_old_runs job (weekly)")

        # Cleanup old articles (weekly, 6-month retention)
        self._scheduler.add_job(
            _cleanup_old_articles,
            trigger=IntervalTrigger(weeks=1, timezone=self._config.timezone),
            id="cleanup_old_articles",
            name="Cleanup articles older than 6 months",
            replace_existing=True,
        )
        logger.info("Registered cleanup_old_articles job (weekly, 6-month retention)")
