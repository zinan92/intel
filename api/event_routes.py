"""API routes for event aggregation."""

import json
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import distinct

from db.database import get_session
from db.models import Article
from events.models import Event, EventArticle

event_router = APIRouter(prefix="/api")


@event_router.get("/events/active")
def get_active_events() -> dict[str, Any]:
    """List active events ordered by signal_score descending.

    Each event includes a list of distinct sources from its linked articles.
    """
    session = get_session()
    try:
        events = (
            session.query(Event)
            .filter(Event.status == "active")
            .order_by(Event.signal_score.desc())
            .all()
        )

        result = []
        for evt in events:
            # Get distinct sources via EventArticle -> Article join
            sources = (
                session.query(distinct(Article.source))
                .join(EventArticle, EventArticle.article_id == Article.id)
                .filter(EventArticle.event_id == evt.id)
                .all()
            )
            source_list = sorted(row[0] for row in sources)

            result.append({
                "id": evt.id,
                "narrative_tag": evt.narrative_tag,
                "window_start": evt.window_start.isoformat(),
                "window_end": evt.window_end.isoformat(),
                "source_count": evt.source_count,
                "article_count": evt.article_count,
                "signal_score": evt.signal_score,
                "avg_relevance": evt.avg_relevance,
                "status": evt.status,
                "sources": source_list,
                "created_at": evt.created_at.isoformat(),
                "updated_at": evt.updated_at.isoformat(),
            })

        return {"events": result}
    finally:
        session.close()


@event_router.get("/events/history")
def get_event_history(
    days: int = Query(default=30, ge=1, le=365),
    tag: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """List closed events within a time window, optionally filtered by narrative tag."""
    session = get_session()
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        q = session.query(Event).filter(Event.status == "closed", Event.window_start >= cutoff)
        if tag:
            q = q.filter(Event.narrative_tag.ilike(f"%{tag}%"))
        events = q.order_by(Event.window_start.desc()).limit(limit).all()

        # Batch fetch tickers
        event_ids = [e.id for e in events]
        tickers_map: dict[int, list[str]] = {}
        if event_ids:
            rows = (
                session.query(EventArticle.event_id, Article.tickers)
                .join(Article, EventArticle.article_id == Article.id)
                .filter(EventArticle.event_id.in_(event_ids))
                .all()
            )
            from collections import defaultdict
            tickers_map = defaultdict(list)
            for eid, tickers_json in rows:
                if tickers_json:
                    try:
                        import json as _json
                        for t in _json.loads(tickers_json):
                            if t and t not in tickers_map[eid]:
                                tickers_map[eid].append(t)
                    except (json.JSONDecodeError, TypeError):
                        pass

        return {
            "events": [
                {
                    "id": e.id,
                    "narrative_tag": e.narrative_tag,
                    "signal_score": e.signal_score,
                    "source_count": e.source_count,
                    "article_count": e.article_count,
                    "narrative_summary": e.narrative_summary,
                    "window_start": e.window_start.isoformat() if e.window_start else None,
                    "window_end": e.window_end.isoformat() if e.window_end else None,
                    "status": e.status,
                    "tickers": tickers_map.get(e.id, [])[:5],
                }
                for e in events
            ]
        }
    finally:
        session.close()


@event_router.get("/events/scorecard")
def get_scorecard(
    days: int = Query(default=30, ge=1, le=365),
    min_events: int = Query(default=2, ge=1, le=50),
) -> dict[str, Any]:
    """Aggregate historical signal accuracy by score buckets."""
    session = get_session()
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        events = (
            session.query(Event)
            .filter(
                Event.status == "closed",
                Event.outcome_data.isnot(None),
                Event.window_start >= cutoff,
            )
            .all()
        )

        buckets_config = [
            {"label": "Signal ≥ 8.0", "min": 8.0, "max": 999},
            {"label": "Signal 6.0–7.9", "min": 6.0, "max": 8.0},
            {"label": "Signal 4.0–5.9", "min": 4.0, "max": 6.0},
            {"label": "Signal < 4.0", "min": 0, "max": 4.0},
        ]

        bucket_data: dict[str, list[dict]] = {b["label"]: [] for b in buckets_config}

        for event in events:
            try:
                outcome = json.loads(event.outcome_data)
                tickers = outcome.get("tickers", {})
                if not tickers:
                    continue
                changes_1d = [v.get("change_1d", 0) for v in tickers.values() if v.get("change_1d") is not None]
                changes_3d = [v.get("change_3d", 0) for v in tickers.values() if v.get("change_3d") is not None]
                changes_5d = [v.get("change_5d", 0) for v in tickers.values() if v.get("change_5d") is not None]
                if not changes_1d:
                    continue
                avg = {
                    "change_1d": sum(changes_1d) / len(changes_1d),
                    "change_3d": sum(changes_3d) / len(changes_3d) if changes_3d else None,
                    "change_5d": sum(changes_5d) / len(changes_5d) if changes_5d else None,
                }
                for b in buckets_config:
                    if b["min"] <= event.signal_score < b["max"]:
                        bucket_data[b["label"]].append(avg)
                        break
            except (json.JSONDecodeError, TypeError):
                continue

        result_buckets = []
        total = 0
        for b in buckets_config:
            items = bucket_data[b["label"]]
            if len(items) < min_events:
                continue
            total += len(items)
            c1 = [i["change_1d"] for i in items]
            c3 = [i["change_3d"] for i in items if i["change_3d"] is not None]
            c5 = [i["change_5d"] for i in items if i["change_5d"] is not None]
            result_buckets.append({
                "label": b["label"],
                "min_score": b["min"],
                "event_count": len(items),
                "avg_change_1d": round(sum(c1) / len(c1), 2),
                "avg_change_3d": round(sum(c3) / len(c3), 2) if c3 else 0,
                "avg_change_5d": round(sum(c5) / len(c5), 2) if c5 else 0,
            })

        return {
            "buckets": result_buckets,
            "total_events_with_data": total,
            "period_days": days,
        }
    finally:
        session.close()


@event_router.get("/events/{event_id}")
async def get_event_detail(event_id: int) -> dict[str, Any]:
    """Get event detail with linked articles and price impacts."""
    session = get_session()
    try:
        evt = session.query(Event).filter(Event.id == event_id).first()
        if evt is None:
            raise HTTPException(status_code=404, detail="Event not found")

        # Fetch linked articles via EventArticle join
        linked = (
            session.query(Article)
            .join(EventArticle, EventArticle.article_id == Article.id)
            .filter(EventArticle.event_id == event_id)
            .order_by(Article.collected_at.desc())
            .all()
        )

        articles = [
            {
                "id": a.id,
                "source": a.source,
                "title": a.title,
                "url": a.url,
                "author": a.author,
                "summary": (a.content or "")[:150],
                "relevance_score": a.relevance_score,
                "published_at": a.published_at.isoformat() if a.published_at else None,
                "collected_at": a.collected_at.isoformat() if a.collected_at else None,
            }
            for a in linked
        ]

        # Aggregate tickers from all articles
        all_tickers: list[str] = []
        seen_tickers: set[str] = set()
        for a in linked:
            if a.tickers:
                try:
                    article_tickers = json.loads(a.tickers)
                    for t in article_tickers:
                        if t not in seen_tickers:
                            seen_tickers.add(t)
                            all_tickers.append(t)
                except (json.JSONDecodeError, TypeError):
                    pass

        # Fetch price impacts (parallel, async)
        price_impacts: list[dict[str, Any]] = []
        if all_tickers and evt.window_start:
            from bridge.quant import get_price_impacts
            price_impacts = await get_price_impacts(all_tickers, evt.window_start)

        return {
            "event": {
                "id": evt.id,
                "narrative_tag": evt.narrative_tag,
                "window_start": evt.window_start.isoformat(),
                "window_end": evt.window_end.isoformat(),
                "source_count": evt.source_count,
                "article_count": evt.article_count,
                "signal_score": evt.signal_score,
                "avg_relevance": evt.avg_relevance,
                "narrative_summary": evt.narrative_summary,
                "prev_signal_score": evt.prev_signal_score,
                "trading_play": evt.trading_play,
                "status": evt.status,
                "created_at": evt.created_at.isoformat(),
                "updated_at": evt.updated_at.isoformat(),
            },
            "articles": articles,
            "price_impacts": price_impacts,
        }
    finally:
        session.close()
