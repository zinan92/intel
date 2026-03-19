"""Tests for event history API endpoint."""
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from db.models import Base
from events.models import Event


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
    for i in range(3):
        session.add(Event(
            narrative_tag=f"closed-event-{i}",
            window_start=now - timedelta(days=i + 1),
            window_end=now - timedelta(days=i + 1) + timedelta(hours=48),
            source_count=2, article_count=3, signal_score=8.0 - i,
            status="closed", narrative_summary=f"Summary {i}",
        ))
    session.commit()
    session.close()
    with TestClient(app) as c:
        yield c


def test_get_event_history(client):
    resp = client.get("/api/events/history")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["events"]) == 3
    assert data["events"][0]["narrative_tag"] == "closed-event-0"


def test_get_event_history_with_tag_filter(client):
    resp = client.get("/api/events/history?tag=event-1")
    assert resp.status_code == 200
    assert len(resp.json()["events"]) == 1


def test_get_event_history_empty(client):
    resp = client.get("/api/events/history?tag=nonexistent")
    assert resp.status_code == 200
    assert len(resp.json()["events"]) == 0
