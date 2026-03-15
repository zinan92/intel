"""Tests for registry-driven /api/health semantics."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, SourceRegistry
from sources.registry import upsert_source


@pytest.fixture
def _seed_test_registry():
    """Seed a minimal in-memory registry for health tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    upsert_source(session, {
        "source_key": "hackernews:main",
        "source_type": "hackernews",
        "display_name": "Hacker News",
        "config": {},
        "schedule_hours": 4,
        "is_active": 1,
    })
    upsert_source(session, {
        "source_key": "rss:test-feed",
        "source_type": "rss",
        "display_name": "Test Feed",
        "config": {"url": "http://example.com/feed"},
        "schedule_hours": 6,
        "is_active": 1,
    })
    session.close()
    return engine, factory


@pytest.fixture
def client(_seed_test_registry):
    engine, factory = _seed_test_registry
    with patch("main.CollectorScheduler.start"), \
         patch("main.CollectorScheduler.shutdown"), \
         patch("db.database.get_engine", return_value=engine), \
         patch("db.database.get_session", side_effect=lambda: factory()):
        from main import app
        with TestClient(app) as test_client:
            yield test_client


def test_health_includes_registry_sources(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    sources = resp.json()["sources"]
    assert "hackernews" in sources
    assert "rss" in sources


def test_health_excludes_retired_sources(client):
    """Sources not in the registry should not appear."""
    resp = client.get("/api/health")
    sources = resp.json()["sources"]
    for retired in ["twitter", "youtube", "substack"]:
        assert retired not in sources


def test_health_no_data_status_for_fresh_source(client):
    """A source with no articles should show no_data."""
    resp = client.get("/api/health")
    sources = resp.json()["sources"]
    # Both test sources have no articles in the test DB
    assert sources["hackernews"]["status"] == "no_data"
    assert sources["rss"]["status"] == "no_data"


def test_health_uses_v2_source_types(client):
    """Health should use v2 source type names, not legacy names."""
    resp = client.get("/api/health")
    sources = resp.json()["sources"]
    # Should NOT contain legacy names
    assert "clawfeed" not in sources
    assert "webpage_monitor" not in sources
    assert "github" not in sources  # should be github_trending
