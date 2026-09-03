"""Bounded Unknown revisit driven by later cross-source event evidence."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from db.models import Article
from triage.event_match import EVENT_WINDOW, reports_match


def _report(article: Article) -> dict[str, Any]:
    return {
        "source": article.source,
        "title": article.title,
        "published_at": article.published_at,
        "collected_at": article.collected_at,
    }


def _event_time(article: Article) -> datetime | None:
    return article.published_at or article.collected_at


def related_evidence_map(
    session: Session,
    articles: list[Article],
    *,
    later_than_by_id: dict[int, datetime] | None = None,
    limit: int = 3,
) -> dict[int, list[dict[str, Any]]]:
    """Load one bounded evidence pool and match it for every supplied Article."""
    result = {article.id: [] for article in articles}
    anchors = [_event_time(article) for article in articles]
    anchors = [anchor for anchor in anchors if anchor is not None]
    if not anchors:
        return result

    window_start = min(anchors) - EVENT_WINDOW
    window_end = max(anchors) + EVENT_WINDOW
    query = session.query(Article).filter(
        Article.collection_lane == "realtime",
        Article.is_backfill.is_(False),
        Article.exposure_status == "matched",
        or_(
            Article.published_at.between(window_start, window_end),
            and_(
                Article.published_at.is_(None),
                Article.collected_at.between(window_start, window_end),
            ),
        ),
    )
    evidence_pool = query.order_by(Article.collected_at.asc()).limit(5000).all()

    for article in articles:
        baseline = (later_than_by_id or {}).get(article.id)
        matches: list[dict[str, Any]] = []
        for candidate in evidence_pool:
            if candidate.id == article.id:
                continue
            if baseline is not None and candidate.collected_at <= baseline:
                continue
            if not reports_match(_report(article), _report(candidate)):
                continue
            matches.append({
                "article_id": candidate.id,
                "source": candidate.source,
                "title": candidate.title,
                "content": (candidate.content or "")[:1200],
                "published_at": candidate.published_at,
                "collected_at": candidate.collected_at,
            })
            if len(matches) >= limit:
                break
        result[article.id] = matches
    return result


def related_evidence_for(
    session: Session,
    article: Article,
    *,
    later_than: datetime | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    if later_than is None and (article.triage_rescan_count or 0) > 0:
        later_than = article.triage_rescan_after
    baselines = {article.id: later_than} if later_than is not None else None
    return related_evidence_map(
        session,
        [article],
        later_than_by_id=baselines,
        limit=limit,
    )[article.id]


def claim_unknown_for_rescan(
    session: Session,
    article_id: int,
    *,
    baseline: datetime,
) -> bool:
    """Atomically claim one completed Unknown for its single permitted rescan."""
    updated = session.query(Article).filter(
        Article.id == article_id,
        Article.triage_status == "complete",
        Article.triage_bucket == "unknown",
        or_(Article.triage_rescan_count.is_(None), Article.triage_rescan_count == 0),
    ).update({
        Article.triage_status: None,
        Article.triage_bucket: None,
        Article.triage_direction: None,
        Article.triage_rationale: None,
        Article.triage_assets: None,
        Article.triage_watch_for: None,
        Article.triage_scenario_bull: None,
        Article.triage_scenario_bear: None,
        Article.triage_model: None,
        Article.triage_error: None,
        Article.triage_attempts: 0,
        Article.triaged_at: None,
        Article.triage_rescan_count: 1,
        Article.triage_rescan_after: baseline,
    }, synchronize_session=False)
    session.commit()
    return updated == 1


def requeue_unknown_with_new_evidence(
    session: Session,
    *,
    now: datetime | None = None,
    lookback_hours: int = 24,
) -> list[int]:
    now = now or datetime.utcnow()
    cutoff = now - timedelta(hours=lookback_hours)
    unknowns = session.query(Article).filter(
        Article.collection_lane == "realtime",
        Article.is_backfill.is_(False),
        Article.collected_at >= cutoff,
        Article.triage_status == "complete",
        Article.triage_bucket == "unknown",
        or_(Article.triage_rescan_count.is_(None), Article.triage_rescan_count == 0),
    ).order_by(Article.collected_at.asc()).all()
    baselines = {
        article.id: article.triaged_at or article.collected_at
        for article in unknowns
    }
    evidence = related_evidence_map(
        session,
        unknowns,
        later_than_by_id=baselines,
        limit=1,
    )

    requeued = []
    for article in unknowns:
        if not evidence.get(article.id):
            continue
        if claim_unknown_for_rescan(
            session,
            article.id,
            baseline=baselines[article.id],
        ):
            requeued.append(article.id)
    return requeued
