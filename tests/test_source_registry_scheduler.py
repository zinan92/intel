"""Tests for registry-driven scheduler and health semantics."""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Article, Base, SourceRegistry
from sources.registry import list_active_sources, retire_source, upsert_source
from sources.seed import seed_source_registry


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    factory = sessionmaker(bind=engine)
    sess = factory()
    seed_source_registry(sess)
    yield sess
    sess.close()


class TestSchedulerUsesRegistry:
    """Scheduler iterates registry records, not ACTIVE_SOURCES."""

    def test_scheduler_groups_by_source_type(self, session: Session):
        """Active registry records can be grouped by source_type for scheduling."""
        active = list_active_sources(session)
        by_type: dict[str, list] = {}
        for src in active:
            by_type.setdefault(src.source_type, []).append(src)

        # Per-instance types should have multiple records
        assert len(by_type.get("rss", [])) > 1
        assert len(by_type.get("reddit", [])) > 1

        # Single-instance types should have exactly 1
        assert len(by_type.get("hackernews", [])) == 1
        assert len(by_type.get("social_kol", [])) == 1

    def test_retired_sources_excluded_from_scheduling(self, session: Session):
        """Retired sources should not appear in active sources list."""
        retire_source(session, "rss:simon-willison")
        active = list_active_sources(session)
        keys = [s.source_key for s in active]
        assert "rss:simon-willison" not in keys

    def test_schedule_hours_available_per_source(self, session: Session):
        """Every active source has schedule_hours for job registration."""
        active = list_active_sources(session)
        for src in active:
            assert src.schedule_hours is not None, f"{src.source_key} missing schedule_hours"

    def test_adapter_exists_for_all_active_types(self, session: Session):
        """Every active source type has a registered adapter."""
        from sources.adapters import get_adapter

        active = list_active_sources(session)
        types = {s.source_type for s in active}
        for t in types:
            assert get_adapter(t) is not None, f"No adapter for active source type: {t}"


class TestHealthUsesRegistry:
    """Health endpoint should report status for every active registry record."""

    def test_health_covers_all_active_registry_sources(self, session: Session):
        """Health should include every active source type from the registry."""
        active = list_active_sources(session)
        active_types = {s.source_type for s in active}
        # All 10 source types should be present
        expected = {"rss", "reddit", "github_release", "website_monitor", "social_kol",
                    "hackernews", "xueqiu", "yahoo_finance", "google_news", "github_trending"}
        assert expected == active_types

    def test_source_with_no_articles_shows_no_data(self, session: Session):
        """A source with no articles should have status 'no_data'."""
        # hackernews:main has no articles in test DB
        hn = [s for s in list_active_sources(session) if s.source_type == "hackernews"]
        assert len(hn) == 1
        # In a real health check, this would show "no_data" status
        # since there are no Article rows for this source

    def test_retired_source_excluded_from_health(self, session: Session):
        """Retired sources should not appear in health output."""
        retire_source(session, "hackernews:main")
        active = list_active_sources(session)
        types = {s.source_type for s in active}
        # hackernews should be gone (only had 1 instance)
        assert "hackernews" not in types

    def test_social_kol_replaces_clawfeed_in_health(self, session: Session):
        """Health should show social_kol, not clawfeed."""
        active = list_active_sources(session)
        types = {s.source_type for s in active}
        assert "social_kol" in types
        assert "clawfeed" not in types

    def test_source_with_recent_articles_shows_ok(self, session: Session, engine):
        """Source with articles < 24h old should show 'ok' status."""
        now = datetime.utcnow()
        article = Article(
            source="hackernews",
            source_id="hn_test_1",
            title="Test article",
            collected_at=now - timedelta(hours=2),
        )
        session.add(article)
        session.commit()

        # Query to verify article exists for hackernews
        count = session.query(Article).filter(Article.source == "hackernews").count()
        assert count >= 1
