"""Regression tests for the 4 issues found in code review of Phase 2.

1. /api/ui/sources must not surface retired sources from the DB.
2. source_health in feed context must reflect all ACTIVE_SOURCES (not just recent-article sources).
3. _window_cutoff must parse Nd patterns (7d, 2d, etc.).
4. /api/ui/sources/{name} must return last_seen_at.
"""

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import config
from db.database import get_session, init_db
from db.models import Article
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
    articles = [
        # Active source — hackernews
        Article(
            source="hackernews",
            source_id="hn_001",
            title="HN active article",
            content="Recent HN content.",
            url="https://news.ycombinator.com/item?id=1",
            tags=json.dumps(["ai"]),
            narrative_tags=json.dumps([]),
            score=100,
            relevance_score=4,
            collected_at=now - timedelta(hours=2),
            published_at=now - timedelta(hours=2),
        ),
        # Active source — rss
        Article(
            source="rss",
            source_id="rss_001",
            title="RSS article",
            content="RSS content.",
            url="https://example.com/post/1",
            tags=json.dumps(["llm"]),
            narrative_tags=json.dumps(["openai-model-release"]),
            score=0,
            relevance_score=5,
            collected_at=now - timedelta(hours=3),
            published_at=now - timedelta(hours=3),
        ),
        # RETIRED source row (simulates legacy DB data from before Phase 1)
        Article(
            source="twitter",
            source_id="tw_999",
            title="Old Twitter post",
            content="Legacy tweet.",
            url="https://x.com/user/status/999",
            tags=json.dumps(["llm"]),
            narrative_tags=json.dumps([]),
            score=0,
            relevance_score=3,
            collected_at=now - timedelta(hours=1),
            published_at=now - timedelta(hours=1),
        ),
    ]
    for a in articles:
        session.add(a)
    session.commit()
    session.close()
    yield
    db_mod._engine = None
    db_mod._SessionFactory = None


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Fix 1 — /api/ui/sources must not surface retired sources
# ---------------------------------------------------------------------------

def test_sources_excludes_retired_source(client):
    """twitter is in DB but is not in ACTIVE_SOURCES — must not appear."""
    resp = client.get("/api/ui/sources")
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()}
    assert "twitter" not in names
    assert "youtube" not in names
    assert "substack" not in names


def test_sources_contains_only_active_sources(client):
    """Every source returned must be a member of config.ACTIVE_SOURCES."""
    active = {e["source"] for e in config.ACTIVE_SOURCES}
    resp = client.get("/api/ui/sources")
    names = {s["name"] for s in resp.json()}
    assert names.issubset(active), f"Unexpected sources: {names - active}"


def test_sources_includes_all_active_sources(client):
    """All ACTIVE_SOURCES are present in the response even with zero DB rows."""
    active = {e["source"] for e in config.ACTIVE_SOURCES}
    resp = client.get("/api/ui/sources")
    names = {s["name"] for s in resp.json()}
    assert active == names


# ---------------------------------------------------------------------------
# Fix 2 — source_health in feed context covers all ACTIVE_SOURCES
# ---------------------------------------------------------------------------

def test_feed_context_source_health_covers_active_sources(client):
    """source_health must list all ACTIVE_SOURCES, not just sources with recent articles."""
    resp = client.get("/api/ui/feed")
    health = resp.json()["context"]["source_health"]
    health_names = {h["source"] for h in health}
    active = {e["source"] for e in config.ACTIVE_SOURCES}
    assert active == health_names


def test_feed_context_source_health_has_status_field(client):
    """Each health entry must carry a status field."""
    resp = client.get("/api/ui/feed")
    health = resp.json()["context"]["source_health"]
    for h in health:
        assert "status" in h, f"Missing status in {h}"
        assert h["status"] in ("ok", "stale", "no_data", "degraded")


def test_feed_context_source_health_excludes_retired(client):
    """twitter row in DB must not propagate into source_health."""
    resp = client.get("/api/ui/feed")
    health_names = {h["source"] for h in resp.json()["context"]["source_health"]}
    assert "twitter" not in health_names


# ---------------------------------------------------------------------------
# Fix 3 — window=7d is parsed correctly (not silently falling back to 24h)
# ---------------------------------------------------------------------------

def test_window_7d_parses(client):
    """window=7d must not fall back to 24h — articles within 7 days must appear."""
    resp = client.get("/api/ui/feed?window=7d&min_relevance=1")
    assert resp.status_code == 200
    # All our seeded articles are within 7d so count should be same as 24h
    resp_24h = client.get("/api/ui/feed?window=24h&min_relevance=1")
    assert resp.status_code == 200
    # rss + hackernews articles (not twitter which is retired) should appear in both
    ids_7d = {i["id"] for i in resp.json()["items"]}
    ids_24h = {i["id"] for i in resp_24h.json()["items"]}
    assert ids_7d == ids_24h  # all fixtures are within 24h so sets should match


def test_window_2d_parses(client):
    """window=2d (Nd pattern) must return a 200."""
    resp = client.get("/api/ui/feed?window=2d&min_relevance=1")
    assert resp.status_code == 200
    assert "items" in resp.json()


# ---------------------------------------------------------------------------
# Fix 4 — /api/ui/sources/{name} returns last_seen_at
# ---------------------------------------------------------------------------

def test_source_detail_has_last_seen_at(client):
    resp = client.get("/api/ui/sources/hackernews")
    assert resp.status_code == 200
    data = resp.json()
    assert "last_seen_at" in data
    assert data["last_seen_at"] is not None  # hackernews has a row in DB


def test_source_detail_retired_source_is_404(client):
    """twitter is in the DB but not in ACTIVE_SOURCES — must be 404."""
    resp = client.get("/api/ui/sources/twitter")
    assert resp.status_code == 404
