"""API routes for park-intel."""

import json
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

import config
from fastapi import APIRouter, Query
from sqlalchemy import func

from db.database import get_session
from db.models import Article

router = APIRouter(prefix="/api")


def _parse_tags(raw: str | None) -> list[str]:
    """Parse JSON tags string to list."""
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(t).lower().strip() for t in parsed if t]
        except (json.JSONDecodeError, TypeError):
            pass
    return []


@router.get("/health")
def health() -> dict[str, Any]:
    """Healthcheck endpoint for active sources only (driven by config.ACTIVE_SOURCES)."""
    from scheduler import get_last_results

    session = get_session()
    try:
        now = datetime.utcnow()
        last_results = get_last_results()

        active_names = [e["source"] for e in config.ACTIVE_SOURCES]

        # Fetch DB freshness only for active sources
        db_rows = (
            session.query(
                Article.source,
                func.count(Article.id),
                func.max(Article.collected_at),
            )
            .filter(Article.source.in_(active_names))
            .group_by(Article.source)
            .all()
        )
        db_map = {row[0]: (row[1], row[2]) for row in db_rows}

        sources_info: dict[str, Any] = {}
        for entry in config.ACTIVE_SOURCES:
            src = entry["source"]
            count, last_collected = db_map.get(src, (0, None))
            age_hours = (
                round((now - last_collected).total_seconds() / 3600, 1)
                if last_collected
                else None
            )

            if last_collected is None:
                status = "no_data"
            elif age_hours is not None and age_hours < 24:
                status = "ok"
            else:
                status = "stale"

            sources_info[src] = {
                "status": status,
                "count": count,
                "last_collected": last_collected.isoformat() if last_collected else None,
                "age_hours": age_hours,
            }

            result = last_results.get(src)
            if result:
                sources_info[src]["last_run"] = result.timestamp
                sources_info[src]["last_run_error"] = result.error
                if result.error:
                    sources_info[src]["status"] = "degraded"

        any_stale = any(s.get("status") == "stale" for s in sources_info.values())
        any_error = any(s.get("last_run_error") for s in sources_info.values())
        overall = "degraded" if (any_stale or any_error) else "ok"

        return {
            "status": overall,
            "service": "park-intel",
            "scheduler": "running",
            "sources": sources_info,
            "timestamp": now.isoformat(),
        }
    finally:
        session.close()


@router.get("/articles/latest")
def get_latest_articles(
    limit: int = Query(default=20, ge=1, le=200),
    source: str | None = Query(default=None),
    min_relevance: int | None = Query(default=None, ge=1, le=5),
) -> list[dict[str, Any]]:
    """Get latest articles, optionally filtered by source and min relevance."""
    session = get_session()
    try:
        query = session.query(Article).order_by(Article.collected_at.desc())
        if source:
            query = query.filter(Article.source == source)
        if min_relevance is not None:
            query = query.filter(Article.relevance_score >= min_relevance)
        articles = query.limit(limit).all()
        return [_serialize(a) for a in articles]
    finally:
        session.close()


@router.get("/articles/search")
def search_articles(
    q: str = Query(..., min_length=1),
    source: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    """Search articles by keyword in title/content."""
    session = get_session()
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = session.query(Article).filter(
            Article.collected_at >= cutoff,
            (Article.title.ilike(f"%{q}%")) | (Article.content.ilike(f"%{q}%")),
        )
        if source:
            query = query.filter(Article.source == source)
        articles = query.order_by(Article.collected_at.desc()).limit(limit).all()
        return [_serialize(a) for a in articles]
    finally:
        session.close()


@router.get("/articles/digest")
def get_digest(
    hours: int = Query(default=24, ge=1, le=168),
    limit_per_source: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    """Get a digest of articles grouped by source, sorted by score/recency.
    Designed for Morning analyst consumption."""
    session = get_session()
    try:
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        articles = (
            session.query(Article)
            .filter(Article.collected_at >= cutoff)
            .all()
        )

        # Group by source
        by_source: dict[str, list[Article]] = {}
        for a in articles:
            by_source.setdefault(a.source, []).append(a)

        sources_out: dict[str, Any] = {}
        all_tags: list[str] = []

        for source, source_articles in by_source.items():
            # Sort: hackernews by score desc, others by published_at desc
            if source == "hackernews":
                source_articles.sort(key=lambda a: a.score or 0, reverse=True)
            else:
                source_articles.sort(
                    key=lambda a: a.published_at or datetime.min, reverse=True
                )

            limited = source_articles[:limit_per_source]
            serialized = [_serialize(a) for a in limited]
            sources_out[source] = {
                "count": len(serialized),
                "articles": serialized,
            }

            # Collect tags from ALL articles in the period (not just limited)
            for a in source_articles:
                all_tags.extend(_parse_tags(a.tags))

        # Count tag frequency
        tag_counts = Counter(all_tags)
        top_tags = [
            {"tag": tag, "count": count}
            for tag, count in tag_counts.most_common(30)
        ]

        return {
            "period": f"last {hours}h",
            "generated_at": datetime.utcnow().isoformat(),
            "sources": sources_out,
            "top_tags": top_tags,
        }
    finally:
        session.close()


@router.get("/articles/signals")
def get_signals(
    hours: int = Query(default=24, ge=1, le=168),
    compare_hours: int = Query(default=24, ge=1, le=168),
    min_relevance: int = Query(default=1, ge=1, le=5),
    source: str | None = Query(default=None),
) -> dict[str, Any]:
    """Aggregated signal dashboard: topic heat, narrative momentum, relevance distribution.

    Compares current period (last `hours` h) vs previous period (preceding `compare_hours` h).
    """
    session = get_session()
    try:
        now = datetime.utcnow()
        current_start = now - timedelta(hours=hours)
        prev_start = current_start - timedelta(hours=compare_hours)

        # Query current period articles
        q = session.query(Article).filter(Article.collected_at >= current_start)
        if source:
            q = q.filter(Article.source == source)
        current_articles = q.all()

        # Query previous period articles
        q_prev = session.query(Article).filter(
            Article.collected_at >= prev_start,
            Article.collected_at < current_start,
        )
        if source:
            q_prev = q_prev.filter(Article.source == source)
        prev_articles = q_prev.all()

        # --- Topic Heat ---
        current_tag_counts = Counter[str]()
        for a in current_articles:
            current_tag_counts.update(_parse_tags(a.tags))

        prev_tag_counts = Counter[str]()
        for a in prev_articles:
            prev_tag_counts.update(_parse_tags(a.tags))

        all_tags = set(current_tag_counts) | set(prev_tag_counts)
        topic_heat = []
        for tag in all_tags:
            cur = current_tag_counts.get(tag, 0)
            prev = prev_tag_counts.get(tag, 0)
            if prev > 0:
                momentum = round((cur - prev) / prev, 2)
            elif cur > 0:
                momentum = 1.0  # new topic
            else:
                momentum = 0.0

            if momentum > 0.2:
                label = "accelerating"
            elif momentum < -0.2:
                label = "decelerating"
            else:
                label = "stable"

            topic_heat.append({
                "tag": tag,
                "current_count": cur,
                "previous_count": prev,
                "momentum": momentum,
                "momentum_label": label,
            })

        topic_heat.sort(key=lambda x: x["current_count"], reverse=True)

        # --- Narrative Momentum ---
        narrative_data: dict[str, dict[str, Any]] = {}
        for a in current_articles:
            ntags = _parse_tags(a.narrative_tags)
            for nt in ntags:
                if nt not in narrative_data:
                    narrative_data[nt] = {
                        "count": 0,
                        "total_relevance": 0,
                        "scored_count": 0,
                        "sources": set(),
                    }
                narrative_data[nt]["count"] += 1
                narrative_data[nt]["sources"].add(a.source)
                if a.relevance_score is not None:
                    narrative_data[nt]["total_relevance"] += a.relevance_score
                    narrative_data[nt]["scored_count"] += 1

        narrative_momentum = []
        for nt, data in narrative_data.items():
            avg_rel = round(data["total_relevance"] / data["scored_count"], 1) if data["scored_count"] > 0 else None
            narrative_momentum.append({
                "narrative_tag": nt,
                "count": data["count"],
                "avg_relevance": avg_rel,
                "sources": sorted(data["sources"]),
            })
        narrative_momentum.sort(key=lambda x: x["count"], reverse=True)

        # --- Relevance Distribution ---
        rel_dist: dict[str, int] = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "unscored": 0}
        for a in current_articles:
            if a.relevance_score is not None and 1 <= a.relevance_score <= 5:
                rel_dist[str(a.relevance_score)] += 1
            else:
                rel_dist["unscored"] += 1

        # --- Source Activity ---
        source_data: dict[str, dict[str, Any]] = {}
        for a in current_articles:
            if a.source not in source_data:
                source_data[a.source] = {"count": 0, "total_relevance": 0, "scored_count": 0}
            source_data[a.source]["count"] += 1
            if a.relevance_score is not None:
                source_data[a.source]["total_relevance"] += a.relevance_score
                source_data[a.source]["scored_count"] += 1

        source_activity = []
        for src, data in source_data.items():
            avg_rel = round(data["total_relevance"] / data["scored_count"], 1) if data["scored_count"] > 0 else None
            source_activity.append({
                "source": src,
                "count": data["count"],
                "avg_relevance": avg_rel,
            })
        source_activity.sort(key=lambda x: x["count"], reverse=True)

        # --- High relevance count ---
        high_relevance_count = sum(
            1 for a in current_articles
            if a.relevance_score is not None and a.relevance_score >= 4
        )

        # --- Top Articles ---
        relevant_articles = [
            a for a in current_articles
            if a.relevance_score is not None and a.relevance_score >= min_relevance
        ]
        relevant_articles.sort(key=lambda a: a.relevance_score or 0, reverse=True)
        top_articles = [_serialize(a) for a in relevant_articles[:20]]

        return {
            "period": f"last {hours}h",
            "article_count": len(current_articles),
            "high_relevance_count": high_relevance_count,
            "topic_heat": topic_heat[:20],
            "narrative_momentum": narrative_momentum[:20],
            "relevance_distribution": rel_dist,
            "source_activity": source_activity,
            "top_articles": top_articles,
        }
    finally:
        session.close()


@router.get("/articles/sources")
def get_sources() -> list[dict[str, Any]]:
    """List all sources with article counts and freshness info."""
    session = get_session()
    try:
        now = datetime.utcnow()
        cutoff_24h = now - timedelta(hours=24)

        results = (
            session.query(
                Article.source,
                func.count(Article.id),
                func.max(Article.collected_at),
                func.max(Article.published_at),
            )
            .group_by(Article.source)
            .all()
        )

        sources = []
        for source, count, last_collected, last_published in results:
            count_24h = (
                session.query(func.count(Article.id))
                .filter(Article.source == source, Article.collected_at >= cutoff_24h)
                .scalar()
            )
            sources.append({
                "source": source,
                "count": count,
                "last_collected_at": last_collected.isoformat() if last_collected else None,
                "latest_published_at": last_published.isoformat() if last_published else None,
                "articles_last_24h": count_24h or 0,
            })

        return sources
    finally:
        session.close()


def _serialize(article: Article) -> dict[str, Any]:
    """Serialize an Article to a dict."""
    tags = _parse_tags(article.tags)
    narrative_tags = _parse_tags(article.narrative_tags)

    return {
        "id": article.id,
        "source": article.source,
        "source_id": article.source_id,
        "author": article.author,
        "title": article.title,
        "content": article.content[:500] if article.content else None,
        "url": article.url,
        "tags": tags,
        "score": article.score,
        "relevance_score": article.relevance_score,
        "narrative_tags": narrative_tags,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "collected_at": article.collected_at.isoformat() if article.collected_at else None,
    }
