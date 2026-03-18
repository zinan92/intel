"""Tests for Event and EventArticle models."""
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


def test_create_event(db_session: Session):
    now = datetime.utcnow()
    event = Event(
        narrative_tag="nvidia-earnings-beat",
        window_start=now,
        window_end=now + timedelta(hours=48),
        source_count=3,
        article_count=10,
        signal_score=12.0,
        avg_relevance=4.0,
        status="active",
    )
    db_session.add(event)
    db_session.commit()

    loaded = db_session.query(Event).first()
    assert loaded is not None
    assert loaded.narrative_tag == "nvidia-earnings-beat"
    assert loaded.signal_score == 12.0
    assert loaded.status == "active"


def test_event_article_link(db_session: Session):
    now = datetime.utcnow()
    article = Article(
        source="hackernews",
        source_id="hn_test_1",
        title="NVIDIA earnings",
        collected_at=now,
    )
    db_session.add(article)
    db_session.commit()

    event = Event(
        narrative_tag="nvidia-earnings-beat",
        window_start=now,
        window_end=now + timedelta(hours=48),
    )
    db_session.add(event)
    db_session.commit()

    link = EventArticle(event_id=event.id, article_id=article.id)
    db_session.add(link)
    db_session.commit()

    links = db_session.query(EventArticle).all()
    assert len(links) == 1
    assert links[0].event_id == event.id
    assert links[0].article_id == article.id


def test_event_article_unique_constraint(db_session: Session):
    """Duplicate event-article links should raise IntegrityError."""
    from sqlalchemy.exc import IntegrityError

    now = datetime.utcnow()
    article = Article(source="rss", source_id="rss_1", collected_at=now)
    db_session.add(article)
    db_session.commit()

    event = Event(
        narrative_tag="test-tag",
        window_start=now,
        window_end=now + timedelta(hours=48),
    )
    db_session.add(event)
    db_session.commit()

    db_session.add(EventArticle(event_id=event.id, article_id=article.id))
    db_session.commit()

    db_session.add(EventArticle(event_id=event.id, article_id=article.id))
    with pytest.raises(IntegrityError):
        db_session.commit()
