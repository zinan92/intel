"""API routes for event aggregation."""

import json
from typing import Any

from fastapi import APIRouter, HTTPException
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
                "status": evt.status,
                "created_at": evt.created_at.isoformat(),
                "updated_at": evt.updated_at.isoformat(),
            },
            "articles": articles,
            "price_impacts": price_impacts,
        }
    finally:
        session.close()
