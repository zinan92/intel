"""Tests for /api/ui/feed and /api/ui/items/{id} endpoints."""

import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

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
        Article(
            source="rss",
            source_id="rss_001",
            title="OpenAI releases new model",
            content="A landmark release from OpenAI with improved reasoning.",
            url="https://example.com/post/1",
            tags=json.dumps(["llm"]),
            narrative_tags=json.dumps(["openai-model-release"]),
            score=0,
            relevance_score=5,
            collected_at=now - timedelta(hours=1),
            published_at=now - timedelta(hours=1),
        ),
        Article(
            source="hackernews",
            source_id="hn_002",
            title="Ask HN: Best tools for LLM agents",
            content="Discussion about agent frameworks and tooling.",
            url="https://news.ycombinator.com/item?id=42",
            tags=json.dumps(["ai", "agents"]),
            narrative_tags=json.dumps([]),
            score=250,
            relevance_score=4,
            collected_at=now - timedelta(hours=3),
            published_at=now - timedelta(hours=3),
        ),
        Article(
            source="social_kol",
            source_id="cf_003",
            title="Sam Altman on AGI",
            content="Tweet about near-term AGI timeline expectations.",
            url="https://x.com/sama/status/999",
            tags=json.dumps(["llm"]),
            narrative_tags=json.dumps(["agi-timeline"]),
            score=0,
            relevance_score=3,
            collected_at=now - timedelta(hours=5),
            published_at=now - timedelta(hours=5),
        ),
        Article(
            source="github_release",
            source_id="gr_004",
            title="claude-code v1.5.0",
            content="New release with parallel agents and improved hooks.",
            url="https://github.com/anthropics/claude-code/releases/tag/v1.5.0",
            tags=json.dumps(["ai-agent"]),
            narrative_tags=json.dumps(["claude-code-release"]),
            score=0,
            relevance_score=5,
            collected_at=now - timedelta(hours=2),
            published_at=now - timedelta(hours=2),
        ),
        # Low relevance — below default floor
        Article(
            source="rss",
            source_id="rss_005",
            title="Low signal post",
            content="Not very relevant.",
            url="https://example.com/post/5",
            tags=json.dumps(["misc"]),
            narrative_tags=json.dumps([]),
            score=0,
            relevance_score=1,
            collected_at=now - timedelta(hours=4),
            published_at=now - timedelta(hours=4),
        ),
        # Old article (outside 24h window)
        Article(
            source="rss",
            source_id="rss_006",
            title="Old post from 2 days ago",
            content="Outside the default window.",
            url="https://example.com/post/6",
            tags=json.dumps(["llm"]),
            narrative_tags=json.dumps([]),
            score=0,
            relevance_score=4,
            collected_at=now - timedelta(hours=50),
            published_at=now - timedelta(hours=50),
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


# --- /api/ui/feed ---

def test_feed_response_shape(client):
    resp = client.get("/api/ui/feed")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "context" in data
    assert "page" in data
    assert "rising_topics" in data["context"]
    assert "source_health" in data["context"]
    assert "next_cursor" in data["page"]


def test_feed_item_required_fields(client):
    resp = client.get("/api/ui/feed")
    data = resp.json()
    assert len(data["items"]) > 0
    item = data["items"][0]
    for field in ("id", "title", "source", "source_kind", "url", "summary",
                  "relevance_score", "priority_score", "momentum_label",
                  "tags", "narrative_tags", "published_at", "collected_at",
                  "in_event"):
        assert field in item, f"Missing field: {field}"


def test_feed_ordered_by_priority_score_desc(client):
    resp = client.get("/api/ui/feed")
    items = resp.json()["items"]
    scores = [i["priority_score"] for i in items]
    assert scores == sorted(scores, reverse=True)


def test_feed_source_filter(client):
    resp = client.get("/api/ui/feed?source=hackernews")
    items = resp.json()["items"]
    assert all(i["source"] == "hackernews" for i in items)
    assert len(items) == 1


def test_feed_topic_filter(client):
    resp = client.get("/api/ui/feed?topic=openai-model-release")
    items = resp.json()["items"]
    assert len(items) >= 1
    assert all(
        "openai-model-release" in i["narrative_tags"] or "openai-model-release" in i["tags"]
        for i in items
    )


def test_feed_default_window_excludes_old_articles(client):
    resp = client.get("/api/ui/feed?window=24h")
    items = resp.json()["items"]
    # rss_006 is 50h old — must not appear
    ids_present = {i["id"] for i in items}
    # We can verify by checking no article is labeled as "old post from 2 days ago"
    titles = {i["title"] for i in items}
    assert "Old post from 2 days ago" not in titles


def test_feed_empty_result_not_500(client):
    resp = client.get("/api/ui/feed?source=nonexistent_source_xyz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["page"]["next_cursor"] is None


def test_feed_events_only_filter(client):
    """events_only=true returns empty when no events exist."""
    resp = client.get("/api/ui/feed?events_only=true")
    items = resp.json()["items"]
    # No events seeded, so no articles should match
    assert items == []


def test_feed_source_kind_github_release(client):
    resp = client.get("/api/ui/feed?source=github_release")
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["source_kind"] == "release"


def test_feed_source_kind_rss(client):
    resp = client.get("/api/ui/feed?source=rss")
    items = resp.json()["items"]
    for item in items:
        assert item["source_kind"] == "blog"


def test_feed_priority_score_is_numeric(client):
    resp = client.get("/api/ui/feed")
    items = resp.json()["items"]
    for item in items:
        assert isinstance(item["priority_score"], (int, float))
        assert item["priority_score"] >= 0


def test_feed_cursor_pagination(client):
    # Get first page with limit=2
    resp1 = client.get("/api/ui/feed?limit=2")
    data1 = resp1.json()
    assert len(data1["items"]) == 2
    cursor = data1["page"]["next_cursor"]
    assert cursor is not None

    # Get next page
    resp2 = client.get(f"/api/ui/feed?limit=2&cursor={cursor}")
    data2 = resp2.json()
    # No overlap
    ids1 = {i["id"] for i in data1["items"]}
    ids2 = {i["id"] for i in data2["items"]}
    assert ids1.isdisjoint(ids2)


def test_feed_context_rising_topics(client):
    resp = client.get("/api/ui/feed")
    rising = resp.json()["context"]["rising_topics"]
    assert isinstance(rising, list)
    if rising:
        assert "topic" in rising[0]
        assert "count" in rising[0]
        assert "momentum_label" in rising[0]


def test_feed_context_source_health(client):
    resp = client.get("/api/ui/feed")
    health = resp.json()["context"]["source_health"]
    assert isinstance(health, list)
    sources_in_health = {h["source"] for h in health}
    # Active sources should appear
    assert "rss" in sources_in_health or "hackernews" in sources_in_health


# --- /api/ui/items/{id} ---

def test_item_detail_shape(client):
    # Get an id from feed first
    items = client.get("/api/ui/feed").json()["items"]
    item_id = items[0]["id"]

    resp = client.get(f"/api/ui/items/{item_id}")
    assert resp.status_code == 200
    data = resp.json()
    for field in ("id", "title", "source", "source_kind", "url", "author",
                  "content", "tags", "narrative_tags", "relevance_score",
                  "published_at", "collected_at", "related"):
        assert field in data, f"Missing field: {field}"


def test_item_detail_content_untruncated(client):
    items = client.get("/api/ui/feed").json()["items"]
    item_id = items[0]["id"]
    detail = client.get(f"/api/ui/items/{item_id}").json()
    feed_item = items[0]
    # Detail content should be >= feed summary length
    assert len(detail["content"]) >= len(feed_item["summary"])


def test_item_detail_404(client):
    resp = client.get("/api/ui/items/999999")
    assert resp.status_code == 404
