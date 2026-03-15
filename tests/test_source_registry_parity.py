"""Parity tests: registry-driven runtime matches legacy source coverage.

Verifies that the source registry contains all sources that were
previously defined in config.ACTIVE_SOURCES, and that runtime
paths (health, feed, scheduler) work without config.ACTIVE_SOURCES.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base
from sources.registry import list_active_sources
from sources.seed import seed_source_registry


@pytest.fixture
def seeded_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    seed_source_registry(session)
    yield session
    session.close()


@pytest.fixture
def client():
    with patch("main.CollectorScheduler.start"), \
         patch("main.CollectorScheduler.shutdown"):
        from main import app
        with TestClient(app) as c:
            yield c


class TestRegistryCoversPreviousConfig:
    """Every source type from legacy ACTIVE_SOURCES is in the registry."""

    LEGACY_TYPES = {
        "hackernews", "xueqiu", "rss", "yahoo_finance",
        "google_news", "reddit", "github_release",
    }
    # These were renamed in V2
    V2_RENAMED = {
        "clawfeed": "social_kol",
        "github": "github_trending",
        "webpage_monitor": "website_monitor",
    }

    def test_all_legacy_types_covered(self, seeded_session):
        active = list_active_sources(seeded_session)
        active_types = {s.source_type for s in active}

        for legacy_type in self.LEGACY_TYPES:
            assert legacy_type in active_types, f"Missing legacy type: {legacy_type}"

        for legacy, v2 in self.V2_RENAMED.items():
            assert v2 in active_types, f"Missing V2 type {v2} (was {legacy})"
            assert legacy not in active_types, f"Legacy name {legacy} still in registry"

    def test_registry_has_10_source_types(self, seeded_session):
        """Should have exactly 10 active source types."""
        active = list_active_sources(seeded_session)
        types = {s.source_type for s in active}
        assert len(types) == 10

    def test_all_per_instance_sources_seeded(self, seeded_session):
        """RSS feeds, subreddits, etc. should all be present."""
        import config as cfg

        active = list_active_sources(seeded_session)

        rss_count = len([s for s in active if s.source_type == "rss"])
        assert rss_count == len(cfg.RSS_FEEDS)

        reddit_count = len([s for s in active if s.source_type == "reddit"])
        assert reddit_count == len(cfg.REDDIT_SUBREDDITS)

        gh_release_count = len([s for s in active if s.source_type == "github_release"])
        assert gh_release_count == len(cfg.GITHUB_RELEASE_REPOS)

        wm_count = len([s for s in active if s.source_type == "website_monitor"])
        assert wm_count == len(cfg.WEBPAGE_MONITORS)


class TestRuntimeWorksWithoutActiveSourcesList:
    """Health, feed, and source endpoints work via registry, not config list."""

    def test_health_works(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "sources" in data
        assert len(data["sources"]) == 10

    def test_feed_works(self, client):
        resp = client.get("/api/ui/feed?min_relevance=1")
        assert resp.status_code == 200
        assert "items" in resp.json()

    def test_sources_list_works(self, client):
        resp = client.get("/api/ui/sources")
        assert resp.status_code == 200
        names = {s["name"] for s in resp.json()}
        assert len(names) == 10

    def test_search_works(self, client):
        resp = client.get("/api/ui/search?q=test")
        assert resp.status_code == 200

    def test_topics_works(self, client):
        resp = client.get("/api/ui/topics")
        assert resp.status_code == 200


class TestConfigNoLongerDrivesRuntime:
    """config.ACTIVE_SOURCES should only be used for seed bootstrap data."""

    def test_scheduler_does_not_import_active_sources(self):
        """scheduler.py should not reference config.ACTIVE_SOURCES."""
        import inspect
        import scheduler
        source = inspect.getsource(scheduler)
        assert "ACTIVE_SOURCES" not in source

    def test_health_does_not_import_active_sources(self):
        """api/routes.py health should not reference config.ACTIVE_SOURCES."""
        import inspect
        from api.routes import health
        source = inspect.getsource(health)
        assert "ACTIVE_SOURCES" not in source

    def test_ui_routes_does_not_import_active_sources(self):
        """api/ui_routes.py should not reference config.ACTIVE_SOURCES."""
        import inspect
        import api.ui_routes as ui
        source = inspect.getsource(ui)
        assert "ACTIVE_SOURCES" not in source
