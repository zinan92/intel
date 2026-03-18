"""UI read-model endpoints for the park-intel feed workbench.

GET /api/ui/feed            — priority-scored feed with cursor pagination
GET /api/ui/items/{id}      — full article detail with related items
GET /api/ui/topics          — narrative topic list (sorted by count)
GET /api/ui/topics/{slug}   — topic drill-down with items
GET /api/ui/sources         — active source list
GET /api/ui/sources/{name}  — source drill-down with items
GET /api/ui/search          — keyword search across title/content
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func

from db.database import get_session
from db.models import Article

ui_router = APIRouter(prefix="/api/ui")


# ---------------------------------------------------------------------------
# Source-kind mapping
# ---------------------------------------------------------------------------
_SOURCE_KIND: dict[str, str] = {
    "github_release": "release",
    "rss": "blog",
    "website_monitor": "blog",
    "hackernews": "discussion",
    "reddit": "discussion",
    "github_trending": "trend",
    "social_kol": "post",
    "xueqiu": "post",
    "yahoo_finance": "news",
    "google_news": "news",
}


def _source_kind(source: str) -> str:
    return _SOURCE_KIND.get(source, "post")


# ---------------------------------------------------------------------------
# Priority score
# ---------------------------------------------------------------------------
_SOURCE_WEIGHT: dict[str, float] = {
    "github_release": 0.3,
    "hackernews": 0.5,
    "social_kol": 0.4,
    "rss": 0.2,
    "reddit": 0.2,
    "xueqiu": 0.3,
    "github_trending": 0.2,
    "website_monitor": 0.1,
    "yahoo_finance": 0.2,
    "google_news": 0.2,
}

_KIND_WEIGHT: dict[str, float] = {
    "release": 0.3,
    "discussion": 0.2,
    "post": 0.1,
    "blog": 0.1,
    "trend": 0.15,
    "news": 0.15,
}


def _priority_score(article: Article, now: datetime) -> float:
    """Deterministic priority score combining relevance, freshness, momentum, and source weight."""
    rel = article.relevance_score or 0
    relevance_component = (rel / 5.0) * 5.0

    age_hours = (
        (now - article.collected_at).total_seconds() / 3600
        if article.collected_at
        else 48.0
    )
    if age_hours < 3:
        freshness_component = 2.0
    elif age_hours < 12:
        freshness_component = 1.0
    elif age_hours < 24:
        freshness_component = 0.5
    else:
        freshness_component = 0.0

    score = article.score or 0
    momentum_component = min(score / 1000.0, 1.0)

    kind = _source_kind(article.source)
    source_w = _SOURCE_WEIGHT.get(article.source, 0.1)
    kind_w = _KIND_WEIGHT.get(kind, 0.1)

    return round(relevance_component + freshness_component + momentum_component + source_w + kind_w, 4)


def _momentum_label(article: Article, now: datetime) -> str:
    age_hours = (
        (now - article.collected_at).total_seconds() / 3600
        if article.collected_at
        else 48.0
    )
    if age_hours < 2:
        return "trending"
    if age_hours < 6:
        return "rising"
    if age_hours < 24:
        return "stable"
    return "fading"


# ---------------------------------------------------------------------------
# Tag helpers
# ---------------------------------------------------------------------------
def _parse_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(t).lower().strip() for t in parsed if t]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _slug(text: str) -> str:
    """Normalize a topic string to a URL slug."""
    s = text.lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-")


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------
def _encode_cursor(priority_score: float, article_id: int) -> str:
    return f"{priority_score:.4f}:{article_id}"


def _decode_cursor(cursor: str) -> tuple[float, int] | None:
    try:
        parts = cursor.split(":", 1)
        return float(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Window parser
# ---------------------------------------------------------------------------
def _window_cutoff(window: str, now: datetime) -> datetime:
    s = window.strip()
    m_h = re.fullmatch(r"(\d+)h", s)
    if m_h:
        return now - timedelta(hours=int(m_h.group(1)))
    m_d = re.fullmatch(r"(\d+)d", s)
    if m_d:
        return now - timedelta(days=int(m_d.group(1)))
    # default to 24h
    return now - timedelta(hours=24)


# ---------------------------------------------------------------------------
# Feed item serializer
# ---------------------------------------------------------------------------
def _feed_item(article: Article, priority: float, now: datetime) -> dict[str, Any]:
    content = article.content or ""
    summary = content[:300] if len(content) > 300 else content
    return {
        "id": article.id,
        "title": article.title,
        "source": article.source,
        "source_kind": _source_kind(article.source),
        "url": article.url,
        "summary": summary,
        "relevance_score": article.relevance_score,
        "priority_score": priority,
        "momentum_label": _momentum_label(article, now),
        "tags": _parse_tags(article.tags),
        "narrative_tags": _parse_tags(article.narrative_tags),
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "collected_at": article.collected_at.isoformat() if article.collected_at else None,
    }


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------
def _build_rising_topics(articles: list[Article], now: datetime) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for a in articles:
        for nt in _parse_tags(a.narrative_tags):
            counts[_slug(nt)] += 1
    result = []
    for slug, count in counts.most_common(10):
        result.append({
            "topic": slug,
            "count": count,
            "momentum_label": "rising" if count > 1 else "stable",
        })
    return result


def _build_source_health(session: Any) -> list[dict[str, Any]]:
    """Build source health from the source registry + scheduler last-run data + DB freshness.

    Mirrors /api/health semantics: iterates active registry source types so
    retired sources never appear and stale/no_data sources are always shown.
    """
    from scheduler import get_last_results
    from sources.registry import list_active_sources

    now = datetime.utcnow()
    last_results = get_last_results()

    active = list_active_sources(session)
    active_types = sorted({s.source_type for s in active})

    db_rows = (
        session.query(
            Article.source,
            func.count(Article.id),
            func.max(Article.collected_at),
        )
        .filter(Article.source.in_(active_types))
        .group_by(Article.source)
        .all()
    )
    db_map = {row[0]: (row[1], row[2]) for row in db_rows}

    result = []
    for source_type in active_types:
        count, last_collected = db_map.get(source_type, (0, None))
        age_hours = (
            (now - last_collected).total_seconds() / 3600
            if last_collected
            else None
        )

        if last_collected is None:
            status = "no_data"
        elif age_hours is not None and age_hours < 24:
            status = "ok"
        else:
            status = "stale"

        run = last_results.get(source_type)
        if run and run.error:
            status = "degraded"

        result.append({
            "source": source_type,
            "count": count,
            "last_seen_at": last_collected.isoformat() if last_collected else None,
            "status": status,
        })

    return result


def _build_top_events(session: Any) -> list[dict[str, Any]]:
    """Fetch top active events by signal score."""
    from events.models import Event

    events = (
        session.query(Event)
        .filter(Event.status == "active")
        .order_by(Event.signal_score.desc())
        .limit(5)
        .all()
    )
    return [
        {
            "id": e.id,
            "narrative_tag": e.narrative_tag,
            "signal_score": e.signal_score,
            "source_count": e.source_count,
            "article_count": e.article_count,
        }
        for e in events
    ]


# ---------------------------------------------------------------------------
# /api/ui/feed
# ---------------------------------------------------------------------------
@ui_router.get("/feed")
def get_feed(
    source: str | None = Query(default=None),
    topic: str | None = Query(default=None),
    min_relevance: int | None = Query(default=2, ge=1, le=5),
    window: str = Query(default="24h"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> dict[str, Any]:
    session = get_session()
    try:
        now = datetime.utcnow()
        cutoff = _window_cutoff(window, now)

        q = session.query(Article).filter(Article.collected_at >= cutoff)
        if source:
            q = q.filter(Article.source == source)
        if min_relevance is not None:
            q = q.filter(Article.relevance_score >= min_relevance)

        articles: list[Article] = q.all()

        # Topic filter (post-load, narrative_tags is JSON string)
        if topic:
            topic_slug = _slug(topic)
            articles = [
                a for a in articles
                if topic_slug in [_slug(t) for t in _parse_tags(a.narrative_tags)]
                or topic_slug in [_slug(t) for t in _parse_tags(a.tags)]
            ]

        # Score and sort
        scored = [(a, _priority_score(a, now)) for a in articles]
        scored.sort(key=lambda x: (-x[1], -x[0].id))

        # Cursor pagination
        if cursor:
            decoded = _decode_cursor(cursor)
            if decoded:
                cursor_score, cursor_id = decoded
                scored = [
                    (a, s) for a, s in scored
                    if s < cursor_score or (s == cursor_score and a.id < cursor_id)
                ]

        page_items = scored[:limit]
        next_cursor = None
        if len(scored) > limit:
            last_a, last_s = page_items[-1]
            next_cursor = _encode_cursor(last_s, last_a.id)

        # rising_topics: derived from recent articles in current window
        context_articles: list[Article] = (
            session.query(Article)
            .filter(Article.collected_at >= cutoff)
            .all()
        )

        return {
            "items": [_feed_item(a, s, now) for a, s in page_items],
            "context": {
                "rising_topics": _build_rising_topics(context_articles, now),
                "source_health": _build_source_health(session),
                "top_events": _build_top_events(session),
            },
            "page": {
                "next_cursor": next_cursor,
            },
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# /api/ui/items/{id}
# ---------------------------------------------------------------------------
@ui_router.get("/items/{item_id}")
def get_item(item_id: int) -> dict[str, Any]:
    session = get_session()
    try:
        article = session.query(Article).filter(Article.id == item_id).first()
        if not article:
            raise HTTPException(status_code=404, detail="Item not found")

        # Related: same source or overlapping narrative_tags, last 24h, not self
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=24)
        candidate_q = (
            session.query(Article)
            .filter(Article.collected_at >= cutoff, Article.id != item_id)
        )
        candidates = candidate_q.all()

        my_ntags = set(_parse_tags(article.narrative_tags))
        my_tags = set(_parse_tags(article.tags))

        def _related_score(a: Article) -> int:
            ntags = set(_parse_tags(a.narrative_tags))
            tags = set(_parse_tags(a.tags))
            score = 0
            if a.source == article.source:
                score += 1
            score += len(my_ntags & ntags) * 3
            score += len(my_tags & tags)
            return score

        related_scored = [(a, _related_score(a)) for a in candidates]
        related_scored = [(a, s) for a, s in related_scored if s > 0]
        related_scored.sort(key=lambda x: -x[1])
        related = related_scored[:5]

        return {
            "id": article.id,
            "title": article.title,
            "source": article.source,
            "source_kind": _source_kind(article.source),
            "url": article.url,
            "author": article.author,
            "content": article.content,
            "tags": _parse_tags(article.tags),
            "narrative_tags": _parse_tags(article.narrative_tags),
            "relevance_score": article.relevance_score,
            "published_at": article.published_at.isoformat() if article.published_at else None,
            "collected_at": article.collected_at.isoformat() if article.collected_at else None,
            "related": [
                {
                    "id": a.id,
                    "title": a.title,
                    "source": a.source,
                    "url": a.url,
                }
                for a, _ in related
            ],
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# /api/ui/topics
# ---------------------------------------------------------------------------
@ui_router.get("/topics")
def get_topics(
    window: str = Query(default="24h"),
) -> list[dict[str, Any]]:
    session = get_session()
    try:
        now = datetime.utcnow()
        cutoff = _window_cutoff(window, now)
        articles = (
            session.query(Article)
            .filter(Article.collected_at >= cutoff)
            .all()
        )

        counts: Counter[str] = Counter()
        for a in articles:
            for nt in _parse_tags(a.narrative_tags):
                counts[_slug(nt)] += 1

        result = []
        for slug, count in counts.most_common():
            result.append({
                "slug": slug,
                "label": slug.replace("-", " ").title(),
                "count": count,
                "momentum_label": "rising" if count > 1 else "stable",
            })
        return result
    finally:
        session.close()


# ---------------------------------------------------------------------------
# /api/ui/topics/{topicSlug}
# ---------------------------------------------------------------------------
@ui_router.get("/topics/{topic_slug}")
def get_topic_detail(topic_slug: str) -> dict[str, Any]:
    session = get_session()
    try:
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=24)
        articles = (
            session.query(Article)
            .filter(Article.collected_at >= cutoff)
            .all()
        )

        slug = _slug(topic_slug)
        matched = [
            a for a in articles
            if slug in [_slug(t) for t in _parse_tags(a.narrative_tags)]
        ]
        if not matched:
            raise HTTPException(status_code=404, detail="Topic not found")

        scored = [(a, _priority_score(a, now)) for a in matched]
        scored.sort(key=lambda x: (-x[1], -x[0].id))

        return {
            "slug": slug,
            "label": slug.replace("-", " ").title(),
            "count": len(matched),
            "items": [_feed_item(a, s, now) for a, s in scored],
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# /api/ui/sources
# ---------------------------------------------------------------------------
@ui_router.get("/sources")
def get_sources() -> list[dict[str, Any]]:
    """List active sources only (driven by source registry).

    Retired sources are excluded, so the UI navigation never
    surfaces twitter/youtube/substack even if historical rows exist.
    """
    from sources.registry import list_active_sources

    session = get_session()
    try:
        active = list_active_sources(session)
        active_types = sorted({s.source_type for s in active})

        rows = (
            session.query(
                Article.source,
                func.count(Article.id),
                func.max(Article.collected_at),
            )
            .filter(Article.source.in_(active_types))
            .group_by(Article.source)
            .all()
        )
        db_map = {row[0]: (row[1], row[2]) for row in rows}

        result = []
        for source_type in active_types:
            count, last_seen = db_map.get(source_type, (0, None))
            result.append({
                "name": source_type,
                "kind": _source_kind(source_type),
                "count": count,
                "last_seen_at": last_seen.isoformat() if last_seen else None,
            })
        result.sort(key=lambda x: -x["count"])
        return result
    finally:
        session.close()


# ---------------------------------------------------------------------------
# /api/ui/sources/{sourceName}
# ---------------------------------------------------------------------------
@ui_router.get("/sources/{source_name}")
def get_source_detail(source_name: str) -> dict[str, Any]:
    from sources.registry import list_active_sources

    session_check = get_session()
    try:
        active = list_active_sources(session_check)
        active_types = {s.source_type for s in active}
    finally:
        session_check.close()

    if source_name not in active_types:
        raise HTTPException(status_code=404, detail="Source not found")

    session = get_session()
    try:
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=24)
        articles = (
            session.query(Article)
            .filter(Article.source == source_name, Article.collected_at >= cutoff)
            .all()
        )

        last_seen_row = (
            session.query(func.max(Article.collected_at))
            .filter(Article.source == source_name)
            .scalar()
        )

        scored = [(a, _priority_score(a, now)) for a in articles]
        scored.sort(key=lambda x: (-x[1], -x[0].id))

        return {
            "name": source_name,
            "kind": _source_kind(source_name),
            "count": len(articles),
            "last_seen_at": last_seen_row.isoformat() if last_seen_row else None,
            "items": [_feed_item(a, s, now) for a, s in scored],
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# /api/ui/search
# ---------------------------------------------------------------------------
@ui_router.get("/search")
def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    session = get_session()
    try:
        now = datetime.utcnow()
        cutoff = now - timedelta(days=7)
        articles = (
            session.query(Article)
            .filter(
                Article.collected_at >= cutoff,
                (Article.title.ilike(f"%{q}%")) | (Article.content.ilike(f"%{q}%")),
            )
            .all()
        )

        scored = [(a, _priority_score(a, now)) for a in articles]
        scored.sort(key=lambda x: (-x[1], -x[0].id))
        scored = scored[:limit]

        return {
            "items": [_feed_item(a, s, now) for a, s in scored],
        }
    finally:
        session.close()
