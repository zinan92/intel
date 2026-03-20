"""Tests for scorecard endpoint."""
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
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
    for i in range(4):
        outcome = json.dumps({
            "tickers": {"NVDA": {"price_at_event": 140, "change_1d": 1.5+i, "change_3d": 2.0+i, "change_5d": 3.0+i}},
            "captured_at": now.isoformat(),
        })
        session.add(Event(
            narrative_tag=f"test-event-{i}",
            window_start=now - timedelta(days=i+1),
            window_end=now - timedelta(days=i+1) + timedelta(hours=48),
            source_count=2, article_count=3, signal_score=8.0+i*0.5,
            status="closed", outcome_data=outcome,
        ))
    session.commit()
    session.close()
    with TestClient(app) as c:
        yield c


def test_scorecard_returns_buckets(client):
    resp = client.get("/api/events/scorecard?min_events=1")
    assert resp.status_code == 200
    data = resp.json()
    assert "buckets" in data
    assert data["total_events_with_data"] > 0


def test_scorecard_empty_when_min_events_high(client):
    resp = client.get("/api/events/scorecard?min_events=50")
    assert resp.status_code == 200
    assert len(resp.json()["buckets"]) == 0
