"""Tests for seeding the source registry from legacy config."""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base, SourceRegistry
from sources.registry import get_source_by_key, list_active_sources, list_all_sources
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
    yield sess
    sess.close()


class TestSeedCreatesInstances:
    """Seeding populates registry from current config arrays."""

    def test_rss_instances_created(self, session: Session):
        seed_source_registry(session)
        rss_sources = [
            s for s in list_all_sources(session)
            if s.source_type == "rss"
        ]
        # config.RSS_FEEDS has 47 entries
        assert len(rss_sources) >= 40  # allow some tolerance for config changes

    def test_reddit_instances_created(self, session: Session):
        seed_source_registry(session)
        reddit_sources = [
            s for s in list_all_sources(session)
            if s.source_type == "reddit"
        ]
        # config.REDDIT_SUBREDDITS has 13 entries
        assert len(reddit_sources) >= 10

    def test_github_release_instances_created(self, session: Session):
        seed_source_registry(session)
        gh_sources = [
            s for s in list_all_sources(session)
            if s.source_type == "github_release"
        ]
        # config.GITHUB_RELEASE_REPOS has 4 entries
        assert len(gh_sources) >= 3

    def test_website_monitor_instances_created(self, session: Session):
        seed_source_registry(session)
        wm_sources = [
            s for s in list_all_sources(session)
            if s.source_type == "website_monitor"
        ]
        # config.WEBPAGE_MONITORS has 2 entries
        assert len(wm_sources) >= 2

    def test_social_kol_instances_created(self, session: Session):
        seed_source_registry(session)
        kol_sources = [
            s for s in list_all_sources(session)
            if s.source_type == "social_kol"
        ]
        # config.CLAWFEED_KOL_LIST has 22 entries
        assert len(kol_sources) >= 20

    def test_single_instance_sources_created(self, session: Session):
        """hackernews, xueqiu, yahoo_finance, google_news, github_trending each get one."""
        seed_source_registry(session)
        all_sources = list_all_sources(session)
        types = {s.source_type for s in all_sources}
        for expected_type in ["hackernews", "xueqiu", "yahoo_finance", "google_news", "github_trending"]:
            assert expected_type in types, f"Missing source type: {expected_type}"


class TestSeedNormalization:
    """Legacy names are normalized during seeding."""

    def test_no_clawfeed_source_type(self, session: Session):
        seed_source_registry(session)
        clawfeed = [s for s in list_all_sources(session) if s.source_type == "clawfeed"]
        assert clawfeed == [], "clawfeed should be normalized to social_kol"

    def test_social_kol_exists(self, session: Session):
        seed_source_registry(session)
        kol = [s for s in list_all_sources(session) if s.source_type == "social_kol"]
        assert len(kol) > 0, "social_kol sources should exist"

    def test_no_github_as_source_type(self, session: Session):
        """'github' should be normalized to 'github_trending'."""
        seed_source_registry(session)
        github_bare = [s for s in list_all_sources(session) if s.source_type == "github"]
        assert github_bare == [], "github should be normalized to github_trending"

    def test_github_trending_exists(self, session: Session):
        seed_source_registry(session)
        gt = [s for s in list_all_sources(session) if s.source_type == "github_trending"]
        assert len(gt) > 0

    def test_no_webpage_monitor_source_type(self, session: Session):
        """'webpage_monitor' should be normalized to 'website_monitor'."""
        seed_source_registry(session)
        wm = [s for s in list_all_sources(session) if s.source_type == "webpage_monitor"]
        assert wm == [], "webpage_monitor should be normalized to website_monitor"

    def test_website_monitor_exists(self, session: Session):
        seed_source_registry(session)
        wm = [s for s in list_all_sources(session) if s.source_type == "website_monitor"]
        assert len(wm) > 0


class TestSeedAttributes:
    """Seeded records have correct attributes."""

    def test_owner_type_is_system(self, session: Session):
        seed_source_registry(session)
        for s in list_all_sources(session):
            assert s.owner_type == "system"

    def test_visibility_is_internal(self, session: Session):
        seed_source_registry(session)
        for s in list_all_sources(session):
            assert s.visibility == "internal"

    def test_all_sources_active(self, session: Session):
        seed_source_registry(session)
        all_sources = list_all_sources(session)
        active_sources = list_active_sources(session)
        assert len(all_sources) == len(active_sources)

    def test_schedule_hours_from_config(self, session: Session):
        """Schedule hours should be derived from ACTIVE_SOURCES intervals."""
        seed_source_registry(session)
        # RSS is 6h in ACTIVE_SOURCES
        rss_sources = [s for s in list_all_sources(session) if s.source_type == "rss"]
        assert len(rss_sources) > 0
        assert all(s.schedule_hours == 6 for s in rss_sources)

    def test_rss_config_has_url(self, session: Session):
        seed_source_registry(session)
        rss_sources = [s for s in list_all_sources(session) if s.source_type == "rss"]
        for s in rss_sources:
            cfg = json.loads(s.config_json)
            assert "url" in cfg, f"RSS source {s.source_key} missing url in config"

    def test_reddit_config_has_subreddit(self, session: Session):
        seed_source_registry(session)
        reddit_sources = [s for s in list_all_sources(session) if s.source_type == "reddit"]
        for s in reddit_sources:
            cfg = json.loads(s.config_json)
            assert "subreddit" in cfg, f"Reddit source {s.source_key} missing subreddit"

    def test_social_kol_config_has_handle(self, session: Session):
        seed_source_registry(session)
        kol_sources = [s for s in list_all_sources(session) if s.source_type == "social_kol"]
        for s in kol_sources:
            cfg = json.loads(s.config_json)
            assert "handle" in cfg, f"social_kol source {s.source_key} missing handle"

    def test_source_keys_are_unique(self, session: Session):
        seed_source_registry(session)
        all_sources = list_all_sources(session)
        keys = [s.source_key for s in all_sources]
        assert len(keys) == len(set(keys)), f"Duplicate keys found: {[k for k in keys if keys.count(k) > 1]}"


class TestSeedIdempotent:
    """Running seed twice must not duplicate or corrupt records."""

    def test_double_seed_same_count(self, session: Session):
        seed_source_registry(session)
        count_1 = len(list_all_sources(session))
        seed_source_registry(session)
        count_2 = len(list_all_sources(session))
        assert count_1 == count_2

    def test_double_seed_preserves_data(self, session: Session):
        seed_source_registry(session)
        rss_before = get_source_by_key(session, "rss:simon-willison")
        assert rss_before is not None
        config_before = rss_before.config_json

        seed_source_registry(session)
        rss_after = get_source_by_key(session, "rss:simon-willison")
        assert rss_after is not None
        assert rss_after.config_json == config_before


class TestSeedSourceKeyPattern:
    """Source keys follow the expected naming convention."""

    def test_rss_key_pattern(self, session: Session):
        seed_source_registry(session)
        rss_sources = [s for s in list_all_sources(session) if s.source_type == "rss"]
        for s in rss_sources:
            assert s.source_key.startswith("rss:"), f"Bad key: {s.source_key}"

    def test_reddit_key_pattern(self, session: Session):
        seed_source_registry(session)
        reddit_sources = [s for s in list_all_sources(session) if s.source_type == "reddit"]
        for s in reddit_sources:
            assert s.source_key.startswith("reddit:"), f"Bad key: {s.source_key}"

    def test_social_kol_key_pattern(self, session: Session):
        seed_source_registry(session)
        kol_sources = [s for s in list_all_sources(session) if s.source_type == "social_kol"]
        for s in kol_sources:
            assert s.source_key.startswith("social_kol:"), f"Bad key: {s.source_key}"
