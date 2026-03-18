"""Tests for event aggregation logic."""
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base, Article
from events.models import Event, EventArticle


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


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

    run_aggregation(db_session)

    events = db_session.query(Event).all()
    assert len(events) == 1
    event = events[0]
    assert event.narrative_tag == "nvidia-earnings"
    assert event.source_count == 2
    assert event.article_count == 2
    assert event.avg_relevance == 4.5
    assert event.signal_score == 9.0  # 2 sources * 4.5 avg


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

    run_aggregation(db_session)

    events = db_session.query(Event).all()
    assert len(events) == 0
