"""Tests for event narrator module."""
from unittest.mock import patch
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, Article
from events.models import Event, EventArticle


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed_event_with_articles(session, narrative_tag="test-event", num_articles=3):
    now = datetime.utcnow()
    event = Event(
        narrative_tag=narrative_tag,
        window_start=now - timedelta(hours=2),
        window_end=now + timedelta(hours=46),
        source_count=2, article_count=num_articles, signal_score=8.0, status="active",
    )
    session.add(event)
    session.flush()
    for i in range(num_articles):
        article = Article(
            source=["hackernews", "reddit", "rss"][i % 3],
            source_id=f"test_{narrative_tag}_{i}",
            title=f"Article {i} about {narrative_tag}",
            content=f"Content about {narrative_tag}. " * 20,
            relevance_score=5 - i,
            collected_at=now - timedelta(hours=i),
        )
        session.add(article)
        session.flush()
        session.add(EventArticle(event_id=event.id, article_id=article.id))
    session.commit()
    return event


def test_generate_narrative_skips_when_already_set(db_session):
    from events.narrator import generate_narratives
    event = _seed_event_with_articles(db_session)
    event.narrative_summary = "Already set"
    db_session.commit()
    with patch("events.narrator._call_claude") as mock:
        generate_narratives(db_session)
        mock.assert_not_called()


def test_generate_narrative_skips_single_source(db_session):
    from events.narrator import generate_narratives
    event = _seed_event_with_articles(db_session)
    event.source_count = 1
    db_session.commit()
    with patch("events.narrator._call_claude") as mock:
        generate_narratives(db_session)
        mock.assert_not_called()


def test_generate_narrative_calls_claude(db_session):
    from events.narrator import generate_narratives
    event = _seed_event_with_articles(db_session)
    with patch("events.narrator._call_claude") as mock:
        mock.return_value = "BTC ETFs saw record inflows."
        generate_narratives(db_session)
    refreshed = db_session.query(Event).filter_by(id=event.id).first()
    assert refreshed.narrative_summary == "BTC ETFs saw record inflows."


def test_generate_narrative_handles_cli_failure(db_session):
    from events.narrator import generate_narratives
    event = _seed_event_with_articles(db_session)
    with patch("events.narrator._call_claude") as mock:
        mock.return_value = None
        generate_narratives(db_session)
    refreshed = db_session.query(Event).filter_by(id=event.id).first()
    assert refreshed.narrative_summary is None
