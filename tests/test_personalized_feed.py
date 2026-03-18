"""Tests for personalized feed ranking."""
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from db.database import get_session, init_db
from db.models import Article
from users.models import UserProfile
from main import app


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("config.DB_PATH", db_path)
    monkeypatch.setattr("config.DATA_DIR", tmp_path)
    monkeypatch.setattr("db.database.DB_PATH", db_path)
    monkeypatch.setattr("db.database.DATA_DIR", tmp_path)

    import db.database as db_mod
    db_mod._engine = None
    db_mod._SessionFactory = None
    init_db()

    session = get_session()
    now = datetime.utcnow()

    user = UserProfile(
        username="wendy",
        display_name="Wendy",
        topic_weights=json.dumps({"ai": 3.0, "crypto": 0.0}),
    )
    session.add(user)

    session.add(Article(
        source="hackernews", source_id="hn_ai",
        title="AI breakthrough", tags=json.dumps(["ai"]),
        relevance_score=3, collected_at=now - timedelta(hours=1),
    ))
    session.add(Article(
        source="reddit", source_id="reddit_crypto",
        title="BTC moon", tags=json.dumps(["crypto"]),
        relevance_score=4, collected_at=now - timedelta(hours=1),
    ))
    session.add(Article(
        source="google_news", source_id="gn_macro",
        title="Fed decision", tags=json.dumps(["macro"]),
        relevance_score=3, collected_at=now - timedelta(hours=1),
    ))

    session.commit()
    session.close()
    yield
    db_mod._engine = None
    db_mod._SessionFactory = None


@pytest.fixture
def client():
    return TestClient(app)


def test_feed_without_user_returns_all(client):
    resp = client.get("/api/ui/feed?min_relevance=1&window=24h")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 3


def test_feed_with_user_filters_zero_weight(client):
    resp = client.get("/api/ui/feed?user=wendy&min_relevance=1&window=24h")
    assert resp.status_code == 200
    items = resp.json()["items"]
    sources = [i["source"] for i in items]
    assert "reddit" not in sources
    assert len(items) == 2


def test_feed_with_user_boosts_high_weight(client):
    resp = client.get("/api/ui/feed?user=wendy&min_relevance=1&window=24h")
    items = resp.json()["items"]
    assert items[0]["tags"] == ["ai"] or "ai" in items[0]["tags"]


def test_feed_with_unknown_user_returns_normal(client):
    resp = client.get("/api/ui/feed?user=nobody&min_relevance=1&window=24h")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 3
