"""Event aggregation — clusters articles by narrative_tag within 48h windows."""
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from db.models import Article
from events.models import Event, EventArticle

logger = logging.getLogger(__name__)

_WINDOW_HOURS = 48


def _parse_narrative_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(t).strip().lower() for t in parsed if t]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _article_timestamp(article: Article) -> datetime:
    """Return best available timestamp, falling back to collected_at."""
    return article.published_at or article.collected_at


def run_aggregation(session: Session) -> None:
    """Run one aggregation cycle: cluster recent articles into events."""
    now = datetime.utcnow()
    cutoff = now - timedelta(hours=_WINDOW_HOURS)

    # 1. Fetch recent articles with narrative tags
    articles = (
        session.query(Article)
        .filter(
            Article.collected_at >= cutoff,
            Article.narrative_tags.isnot(None),
            Article.narrative_tags != "",
            Article.narrative_tags != "[]",
        )
        .all()
    )

    # 2. Group articles by tag
    tag_articles: dict[str, list[Article]] = defaultdict(list)
    for article in articles:
        for tag in _parse_narrative_tags(article.narrative_tags):
            tag_articles[tag].append(article)

    # 3. For each tag, create or update event
    for tag, tag_arts in tag_articles.items():
        active_event = (
            session.query(Event)
            .filter(
                Event.narrative_tag == tag,
                Event.status == "active",
                Event.window_end > now,
            )
            .first()
        )

        if active_event is None:
            timestamps = [_article_timestamp(a) for a in tag_arts]
            earliest = min(timestamps)
            active_event = Event(
                narrative_tag=tag,
                window_start=earliest,
                window_end=earliest + timedelta(hours=_WINDOW_HOURS),
                status="active",
            )
            session.add(active_event)
            session.flush()

        # Link articles (check-then-insert to avoid IntegrityError rollback issues)
        for article in tag_arts:
            existing = (
                session.query(EventArticle)
                .filter_by(event_id=active_event.id, article_id=article.id)
                .first()
            )
            if existing is None:
                link = EventArticle(
                    event_id=active_event.id,
                    article_id=article.id,
                )
                session.add(link)
                session.flush()

        # Recalculate stats
        linked_article_ids = [
            ea.article_id
            for ea in session.query(EventArticle)
            .filter(EventArticle.event_id == active_event.id)
            .all()
        ]
        linked_articles = (
            session.query(Article)
            .filter(Article.id.in_(linked_article_ids))
            .all()
        )

        sources = {a.source for a in linked_articles}
        relevances = [
            a.relevance_score for a in linked_articles
            if a.relevance_score is not None
        ]
        avg_rel = sum(relevances) / len(relevances) if relevances else 0.0

        # Save current score for velocity tracking
        active_event.prev_signal_score = active_event.signal_score

        active_event.source_count = len(sources)
        active_event.article_count = len(linked_articles)
        active_event.avg_relevance = round(avg_rel, 2)
        active_event.signal_score = round(len(sources) * avg_rel, 2)
        active_event.updated_at = now

    # 4. Close expired events
    expired = (
        session.query(Event)
        .filter(Event.status == "active", Event.window_end < now)
        .all()
    )
    for event in expired:
        event.status = "closed"
        event.updated_at = now

    session.commit()

    # Generate narratives for cross-source events
    try:
        from events.narrator import generate_narratives
        generate_narratives(session)
    except Exception:
        logger.exception("Narrative generation failed (non-fatal)")

    logger.info(
        "Aggregation complete: %d tags processed, %d events closed",
        len(tag_articles),
        len(expired),
    )
