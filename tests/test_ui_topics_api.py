"""Tests for /api/ui/topics, /api/ui/sources, and /api/ui/search endpoints."""

import json
from datetime import datetime, timedelta

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
        # Duplicate narrative tag to test count
        Article(
            source="rss",
            source_id="rss_007",
            title="OpenAI model update follow-up",
            content="More details on the recent OpenAI model release.",
            url="https://example.com/post/7",
            tags=json.dumps(["llm"]),
            narrative_tags=json.dumps(["openai-model-release"]),
            score=0,
            relevance_score=4,
            collected_at=now - timedelta(hours=2),
            published_at=now - timedelta(hours=2),
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


# --- /api/ui/topics ---

def test_topics_response_shape(client):
    resp = client.get("/api/ui/topics")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_topics_item_fields(client):
    resp = client.get("/api/ui/topics")
    data = resp.json()
    assert len(data) > 0
    topic = data[0]
    for field in ("slug", "label", "count", "momentum_label"):
        assert field in topic, f"Missing field: {field}"


def test_topics_ordered_by_count_desc(client):
    resp = client.get("/api/ui/topics")
    data = resp.json()
    counts = [t["count"] for t in data]
    assert counts == sorted(counts, reverse=True)


def test_topics_openai_model_release_present(client):
    resp = client.get("/api/ui/topics")
    data = resp.json()
    slugs = [t["slug"] for t in data]
    assert "openai-model-release" in slugs
    # Should have count=2 (two articles share this narrative_tag)
    topic = next(t for t in data if t["slug"] == "openai-model-release")
    assert topic["count"] == 2


def test_topics_only_within_window(client):
    resp = client.get("/api/ui/topics?window=24h")
    data = resp.json()
    # All narrative tags from the seeded articles are within 24h
    assert len(data) > 0


# --- /api/ui/topics/{topicSlug} ---

def test_topic_detail_shape(client):
    resp = client.get("/api/ui/topics/openai-model-release")
    assert resp.status_code == 200
    data = resp.json()
    assert "slug" in data
    assert "items" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) >= 1


def test_topic_detail_items_match_slug(client):
    resp = client.get("/api/ui/topics/openai-model-release")
    data = resp.json()
    for item in data["items"]:
        assert "openai-model-release" in item["narrative_tags"]


def test_topic_detail_404(client):
    resp = client.get("/api/ui/topics/nonexistent-topic-xyz")
    assert resp.status_code == 404


# --- /api/ui/sources ---

def test_sources_response_shape(client):
    resp = client.get("/api/ui/sources")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_sources_item_fields(client):
    resp = client.get("/api/ui/sources")
    data = resp.json()
    source = data[0]
    for field in ("name", "kind", "count", "last_seen_at"):
        assert field in source, f"Missing field: {field}"


def test_sources_github_release_kind(client):
    resp = client.get("/api/ui/sources")
    data = resp.json()
    gr = next((s for s in data if s["name"] == "github_release"), None)
    assert gr is not None
    assert gr["kind"] == "release"


def test_sources_rss_kind(client):
    resp = client.get("/api/ui/sources")
    data = resp.json()
    rss = next((s for s in data if s["name"] == "rss"), None)
    assert rss is not None
    assert rss["kind"] == "blog"


# --- /api/ui/sources/{sourceName} ---

def test_source_detail_shape(client):
    resp = client.get("/api/ui/sources/hackernews")
    assert resp.status_code == 200
    data = resp.json()
    assert "name" in data
    assert "items" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) >= 1


def test_source_detail_items_all_from_source(client):
    resp = client.get("/api/ui/sources/rss")
    data = resp.json()
    for item in data["items"]:
        assert item["source"] == "rss"


def test_source_detail_404(client):
    resp = client.get("/api/ui/sources/nonexistent_source_xyz")
    assert resp.status_code == 404


# --- /api/ui/search ---

def test_search_response_shape(client):
    resp = client.get("/api/ui/search?q=OpenAI")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


def test_search_finds_matching_title(client):
    resp = client.get("/api/ui/search?q=OpenAI")
    data = resp.json()
    assert len(data["items"]) >= 1
    titles = [i["title"] for i in data["items"]]
    assert any("OpenAI" in t for t in titles)


def test_search_finds_matching_content(client):
    resp = client.get("/api/ui/search?q=agent+frameworks")
    data = resp.json()
    assert len(data["items"]) >= 1


def test_search_no_results_not_500(client):
    resp = client.get("/api/ui/search?q=xyzzy_no_match_at_all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []


def test_search_missing_q_returns_422(client):
    resp = client.get("/api/ui/search")
    assert resp.status_code == 422
