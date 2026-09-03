"""Tests for event aggregation logic."""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base, Article, CollectorRun
from events.models import Event, EventArticle


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _isolate_narrator():
    result = SimpleNamespace(generated=0, failed=0, providers=(), fallback_reasons=())
    with patch("events.narrator.generate_narratives", return_value=result):
        yield


def _make_article(
    session: Session,
    source: str,
    narrative_tags: list[str],
    relevance: int = 3,
    hours_ago: float = 1.0,
) -> Article:
    now = datetime.utcnow()
    article = Article(
        source=source,
        source_id=f"{source}_{id(narrative_tags)}_{hours_ago}",
        title=f"Test {source}",
        narrative_tags=json.dumps(narrative_tags),
        relevance_score=relevance,
        published_at=now - timedelta(hours=hours_ago),
        collected_at=now - timedelta(hours=hours_ago),
    )
    session.add(article)
    session.commit()
    return article


def test_aggregate_creates_event(db_session: Session):
    from events.aggregator import run_aggregation

    _make_article(db_session, "hackernews", ["nvidia-earnings"], relevance=4, hours_ago=2)
    _make_article(db_session, "reddit", ["nvidia-earnings"], relevance=5, hours_ago=1)

    result = run_aggregation(db_session)

    events = db_session.query(Event).all()
    assert len(events) == 1
    event = events[0]
    assert event.narrative_tag == "nvidia-earnings"
    assert event.source_count == 2
    assert event.article_count == 2
    assert event.avg_relevance == 4.5
    assert event.signal_score == 9.0  # 2 sources * 4.5 avg
    assert result.status == "ok"
    assert result.fresh_articles == 2
    assert result.usable_articles == 2
    assert result.events_updated == 1


def test_aggregate_updates_existing_event(db_session: Session):
    from events.aggregator import run_aggregation

    _make_article(db_session, "hackernews", ["test-tag"], relevance=4, hours_ago=2)
    run_aggregation(db_session)

    events = db_session.query(Event).all()
    assert len(events) == 1
    assert events[0].source_count == 1

    # Add another article from different source
    _make_article(db_session, "rss", ["test-tag"], relevance=2, hours_ago=0.5)
    run_aggregation(db_session)

    events = db_session.query(Event).all()
    assert len(events) == 1
    assert events[0].source_count == 2
    assert events[0].article_count == 2


def test_aggregate_does_not_reactivate_closed_event(db_session: Session):
    from events.aggregator import run_aggregation

    now = datetime.utcnow()
    old_event = Event(
        narrative_tag="gold-price-rally",
        window_start=now - timedelta(days=30),
        window_end=now - timedelta(days=28),
        status="closed",
        narrative_summary="Gold hit record highs above $5,000/oz.",
    )
    db_session.add(old_event)
    db_session.commit()

    _make_article(db_session, "rss", ["gold-price-rally"], relevance=4, hours_ago=1)
    run_aggregation(db_session)

    events = db_session.query(Event).order_by(Event.id).all()
    assert len(events) == 2
    assert events[0].id == old_event.id
    assert events[0].status == "closed"
    assert events[1].status == "active"
    assert events[1].narrative_summary is None


def test_aggregate_closes_expired_event_before_linking_fresh_articles(db_session: Session):
    from events.aggregator import run_aggregation

    now = datetime.utcnow()
    old_event = Event(
        narrative_tag="btc-breakdown",
        window_start=now - timedelta(hours=72),
        window_end=now - timedelta(hours=24),
        status="active",
    )
    db_session.add(old_event)
    db_session.commit()

    fresh = _make_article(db_session, "rss", ["btc-breakdown"], relevance=5, hours_ago=1)
    run_aggregation(db_session)

    old_refreshed = db_session.query(Event).filter(Event.id == old_event.id).first()
    new_event = (
        db_session.query(Event)
        .filter(Event.narrative_tag == "btc-breakdown", Event.status == "active")
        .one()
    )
    assert old_refreshed.status == "closed"
    assert new_event.id != old_event.id

    links = db_session.query(EventArticle).filter(EventArticle.article_id == fresh.id).all()
    assert len(links) == 1
    assert links[0].event_id == new_event.id


def test_aggregate_closes_expired_events(db_session: Session):
    from events.aggregator import run_aggregation

    now = datetime.utcnow()
    old_event = Event(
        narrative_tag="old-event",
        window_start=now - timedelta(hours=72),
        window_end=now - timedelta(hours=24),
        status="active",
    )
    db_session.add(old_event)
    db_session.commit()

    run_aggregation(db_session)

    refreshed = db_session.query(Event).filter(Event.id == old_event.id).first()
    assert refreshed.status == "closed"


def test_aggregate_uses_collected_at_when_published_at_null(db_session: Session):
    from events.aggregator import run_aggregation

    now = datetime.utcnow()
    article = Article(
        source="social_kol",
        source_id="kol_no_pub",
        title="No publish date",
        narrative_tags=json.dumps(["test-null-pub"]),
        relevance_score=3,
        published_at=None,
        collected_at=now - timedelta(hours=1),
    )
    db_session.add(article)
    db_session.commit()

    run_aggregation(db_session)

    events = db_session.query(Event).all()
    assert len(events) == 1
    assert events[0].window_start is not None


def test_aggregate_ignores_stale_rediscovered_article(db_session: Session):
    from events.aggregator import run_aggregation

    now = datetime.utcnow()
    article = Article(
        source="google_news",
        source_id="stale_google_news",
        title="Old article rediscovered today",
        narrative_tags=json.dumps(["stale-topic"]),
        relevance_score=4,
        published_at=now - timedelta(days=30),
        collected_at=now - timedelta(hours=1),
    )
    db_session.add(article)
    db_session.commit()

    run_aggregation(db_session)

    events = db_session.query(Event).all()
    assert len(events) == 0


def test_aggregate_ignores_articles_without_narrative_tags(db_session: Session):
    from events.aggregator import run_aggregation

    now = datetime.utcnow()
    article = Article(
        source="rss",
        source_id="rss_no_tags",
        title="No tags",
        narrative_tags=None,
        collected_at=now - timedelta(hours=1),
    )
    db_session.add(article)
    db_session.commit()

    result = run_aggregation(db_session)

    events = db_session.query(Event).all()
    assert len(events) == 0
    assert result.status == "degraded"
    run = db_session.query(CollectorRun).filter_by(source_type="event_aggregation").one()
    assert run.status == "degraded"
    assert run.articles_fetched == 1
    assert run.articles_saved == 0
    assert "zero usable scored/tagged articles" in run.error_message


def test_aggregate_rejects_invalid_scores_from_event_math(db_session: Session):
    from events.aggregator import run_aggregation

    _make_article(db_session, "rss", ["invalid-score"], relevance=0)
    _make_article(db_session, "reddit", ["invalid-score"], relevance=9)

    result = run_aggregation(db_session)

    assert result.status == "degraded"
    assert result.usable_articles == 0
    assert db_session.query(Event).count() == 0


def test_scheduler_propagates_degraded_aggregation():
    import scheduler

    session = SimpleNamespace(close=lambda: None)
    result = SimpleNamespace(status="degraded", error="zero usable tags")
    with patch("db.database.get_session", return_value=session), \
         patch("events.aggregator.run_aggregation", return_value=result):
        with pytest.raises(RuntimeError, match="zero usable tags"):
            scheduler._run_event_aggregation()
