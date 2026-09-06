"""Event aggregation — clusters articles by narrative_tag within 48h windows."""
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from db.models import Article, CollectorRun
from events.models import Event, EventArticle

logger = logging.getLogger(__name__)

_WINDOW_HOURS = 48


@dataclass(frozen=True)
class AggregationResult:
    status: str
    fresh_articles: int
    usable_articles: int
    tags_processed: int
    events_updated: int
    narratives_generated: int
    narratives_failed: int
    error: str | None = None


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


def _close_expired_events(session: Session, now: datetime) -> list[Event]:
    expired = (
        session.query(Event)
        .filter(Event.status == "active", Event.window_end < now)
        .all()
    )
    for event in expired:
        event.status = "closed"
        event.updated_at = now
    return expired


def _has_valid_score(article: Article) -> bool:
    return article.relevance_score is not None and 1 <= article.relevance_score <= 5


def run_aggregation(session: Session) -> AggregationResult:
    """Run one aggregation cycle: cluster recent articles into events."""
    started = time.monotonic()
    now = datetime.utcnow()
    cutoff = now - timedelta(hours=_WINDOW_HOURS)

    expired = _close_expired_events(session, now)

    # 1. Fetch the fresh hourly lane first so missing scoring/tagging remains visible.
    fresh_articles = (
        session.query(Article)
        .filter(
            Article.collected_at >= cutoff,
            (Article.published_at.is_(None)) | (Article.published_at >= cutoff),
            # Realtime items remain readable candidates during the migration,
            # but must not become production events/signals before convergence.
            Article.collection_lane == "hourly",
        )
        .all()
    )
    usable_articles = [
        article
        for article in fresh_articles
        if _has_valid_score(article) and _parse_narrative_tags(article.narrative_tags)
    ]

    # 2. Group articles by tag
    tag_articles: dict[str, list[Article]] = defaultdict(list)
    for article in usable_articles:
        for tag in _parse_narrative_tags(article.narrative_tags):
            tag_articles[tag].append(article)

    # 3. For each tag, create or update event
    events_updated = 0
    for tag, tag_arts in tag_articles.items():
        timestamps = [_article_timestamp(a) for a in tag_arts]
        earliest = min(timestamps)

        # Only update the currently live event instance. Closed events are
        # historical artifacts and must not be reactivated; otherwise a tag like
        # "gold-price-rally" accumulates stale March summaries into June briefs.
        existing_event = (
            session.query(Event)
            .filter(
                Event.narrative_tag == tag,
                Event.status == "active",
                Event.window_end >= now,
            )
            .order_by(Event.created_at.desc())
            .first()
        )

        if existing_event is not None:
            active_event = existing_event
        else:
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
        linked_articles = [
            article for article in linked_articles
            if active_event.window_start <= _article_timestamp(article) < active_event.window_end
            and _has_valid_score(article)
            and tag in _parse_narrative_tags(article.narrative_tags)
        ]

        sources = {a.source for a in linked_articles}
        relevances = [
            a.relevance_score for a in linked_articles
            if _has_valid_score(a)
        ]
        avg_rel = sum(relevances) / len(relevances) if relevances else 0.0

        # Save current score for velocity tracking
        active_event.prev_signal_score = active_event.signal_score

        active_event.source_count = len(sources)
        active_event.article_count = len(linked_articles)
        active_event.avg_relevance = round(avg_rel, 2)
        active_event.signal_score = round(len(sources) * avg_rel, 2)
        active_event.updated_at = now
        events_updated += 1

    # Release event/link writes before any external price lookup.
    session.commit()

    # 4. Snapshot price outcomes for events closed at the start of this run.
    for event in expired:
        if event.outcome_data is not None:
            continue
        try:
            linked_ids = [
                ea.article_id
                for ea in session.query(EventArticle)
                .filter(EventArticle.event_id == event.id).all()
            ]
            tickers = set()
            for art in session.query(Article).filter(Article.id.in_(linked_ids)).all():
                if art.tickers:
                    try:
                        for t in json.loads(art.tickers):
                            if t:
                                tickers.add(t)
                    except (json.JSONDecodeError, TypeError):
                        pass
            if tickers:
                import asyncio
                from bridge.quant import get_price_impacts
                window_start = event.window_start
                session.commit()
                impacts = asyncio.run(get_price_impacts(list(tickers)[:5], window_start))
                if impacts:
                    outcome = {
                        "tickers": {
                            pi["ticker"]: {k: pi.get(k) for k in ["price_at_event", "change_1d", "change_3d", "change_5d"]}
                            for pi in impacts
                        },
                        "captured_at": now.isoformat(),
                    }
                    event.outcome_data = json.dumps(outcome)
                    session.commit()
        except Exception:
            logger.warning("[aggregator] Failed outcome for '%s'", event.narrative_tag, exc_info=True)

    session.commit()

    narrative_generated = 0
    narrative_failed = 0
    narrative_providers: tuple[str, ...] = ()
    fallback_reasons: tuple[str, ...] = ()
    try:
        from events.narrator import generate_narratives
        narrative_result = generate_narratives(session)
        narrative_generated = narrative_result.generated
        narrative_failed = narrative_result.failed
        narrative_providers = narrative_result.providers
        fallback_reasons = narrative_result.fallback_reasons
    except Exception as exc:
        narrative_failed = 1
        fallback_reasons = (type(exc).__name__,)
        logger.exception("Narrative generation failed")

    unusable_count = len(fresh_articles) - len(usable_articles)
    if not fresh_articles:
        status = "no_data"
        error = None
    elif not usable_articles:
        status = "degraded"
        error = "fresh articles present but zero usable scored/tagged articles"
    elif unusable_count or narrative_failed:
        status = "degraded"
        error = (
            f"unusable_articles={unusable_count}; "
            f"narrative_failures={narrative_failed}"
        )
    else:
        status = "ok"
        error = None

    session.add(CollectorRun(
        source_type="event_aggregation",
        source_key="event_aggregation:hourly",
        status=status,
        articles_fetched=len(fresh_articles),
        articles_saved=len(usable_articles),
        articles_duplicate=events_updated,
        articles_failed=unusable_count + narrative_failed,
        duration_ms=int((time.monotonic() - started) * 1000),
        error_message=error,
        error_category="processing" if status == "degraded" else None,
        provider=",".join(narrative_providers) or None,
        fallback_reason=",".join(fallback_reasons) or None,
        completed_at=now,
    ))
    session.commit()

    result = AggregationResult(
        status=status,
        fresh_articles=len(fresh_articles),
        usable_articles=len(usable_articles),
        tags_processed=len(tag_articles),
        events_updated=events_updated,
        narratives_generated=narrative_generated,
        narratives_failed=narrative_failed,
        error=error,
    )

    logger.info(
        "Aggregation %s: %d/%d usable articles, %d tags, %d events updated, %d events closed",
        status,
        len(usable_articles),
        len(fresh_articles),
        len(tag_articles),
        events_updated,
        len(expired),
    )
    return result
