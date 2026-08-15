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
    event.trading_play = "SCENARIO A: ..."
    db_session.commit()
    with patch("events.narrator._call_deepseek") as mock:
        generate_narratives(db_session)
        mock.assert_not_called()


def test_generate_narrative_skips_single_source(db_session):
    from events.narrator import generate_narratives
    event = _seed_event_with_articles(db_session)
    event.source_count = 1
    db_session.commit()
    with patch("events.narrator._call_deepseek") as mock:
        generate_narratives(db_session)
        mock.assert_not_called()


def test_generate_narrative_calls_deepseek(db_session):
    from events.narrator import generate_narratives
    event = _seed_event_with_articles(db_session)
    with patch("events.narrator._call_deepseek") as mock:
        mock.return_value = "BTC ETFs saw record inflows."
        generate_narratives(db_session)
    refreshed = db_session.query(Event).filter_by(id=event.id).first()
    assert refreshed.narrative_summary == "BTC ETFs saw record inflows."


def test_generate_narrative_ignores_articles_outside_event_window(db_session):
    from events.narrator import generate_narratives

    now = datetime.utcnow()
    event = Event(
        narrative_tag="gold-price-rally",
        window_start=now - timedelta(hours=2),
        window_end=now + timedelta(hours=2),
        source_count=2,
        article_count=2,
        signal_score=8.0,
        status="active",
    )
    db_session.add(event)
    db_session.flush()

    stale = Article(
        source="rss",
        source_id="stale_gold",
        title="Gold hit record highs above $5,000",
        content="Old stale gold narrative.",
        relevance_score=5,
        published_at=now - timedelta(days=30),
        collected_at=now - timedelta(days=30),
    )
    fresh = Article(
        source="google_news",
        source_id="fresh_gold",
        title="Gold trades around $4,000",
        content="Fresh gold narrative.",
        relevance_score=4,
        published_at=now - timedelta(hours=1),
        collected_at=now - timedelta(hours=1),
    )
    db_session.add_all([stale, fresh])
    db_session.flush()
    db_session.add(EventArticle(event_id=event.id, article_id=stale.id))
    db_session.add(EventArticle(event_id=event.id, article_id=fresh.id))
    db_session.commit()

    with patch("events.narrator._call_deepseek") as mock:
        mock.return_value = "Fresh gold summary"
        generate_narratives(db_session)

    prompt = mock.call_args[0][0]
    assert "Gold trades around $4,000" in prompt
    assert "record highs above $5,000" not in prompt


def test_generate_narrative_handles_api_failure(db_session):
    from events.narrator import generate_narratives
    event = _seed_event_with_articles(db_session)
    with patch("events.narrator._call_deepseek") as mock:
        mock.return_value = None
        generate_narratives(db_session)
    refreshed = db_session.query(Event).filter_by(id=event.id).first()
    assert refreshed.narrative_summary is None
