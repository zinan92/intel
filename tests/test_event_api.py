"""Tests for event API endpoints."""
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from db.models import Base, Article
from events.models import Event, EventArticle


@pytest.fixture
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("config.DB_PATH", db_path)
    monkeypatch.setattr("config.DATA_DIR", tmp_path)
    monkeypatch.setattr("db.database.DB_PATH", db_path)
    monkeypatch.setattr("db.database.DATA_DIR", tmp_path)

    import db.database as db_mod
    db_mod._engine = None
    db_mod._SessionFactory = None

    from db.database import get_session, init_db
    from main import app
    init_db()

    session = get_session()
    now = datetime.utcnow()
    event = Event(
        narrative_tag="test-event",
        window_start=now - timedelta(hours=2),
        window_end=now + timedelta(hours=46),
        source_count=2,
        article_count=3,
        signal_score=8.0,
        avg_relevance=4.0,
        status="active",
    )
    session.add(event)
    session.commit()

    article = Article(
        source="hackernews",
        source_id="hn_test_evt",
        title="Test article for event",
        narrative_tags=json.dumps(["test-event"]),
        relevance_score=4,
        collected_at=now,
    )
    session.add(article)
    session.commit()

    link = EventArticle(event_id=event.id, article_id=article.id)
    session.add(link)
    session.commit()
    session.close()

    with TestClient(app) as c:
        yield c

    db_mod._engine = None
    db_mod._SessionFactory = None


def test_get_active_events(client):
    resp = client.get("/api/events/active")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert len(data["events"]) >= 1
    event = data["events"][0]
    assert event["narrative_tag"] == "test-event"
    assert "sources" in event


def test_get_event_detail(client):
    events = client.get("/api/events/active").json()["events"]
    event_id = events[0]["id"]
    resp = client.get(f"/api/events/{event_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["event"]["narrative_tag"] == "test-event"
    assert len(data["articles"]) >= 1
    assert "price_impacts" in data
    assert isinstance(data["price_impacts"], list)


def test_get_event_not_found(client):
    resp = client.get("/api/events/99999")
    assert resp.status_code == 404
