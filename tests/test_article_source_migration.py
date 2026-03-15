"""Tests for the article source name migration.

Verifies that the migration rewrites legacy Article.source values
to canonical V2 names, is idempotent, and leaves unrelated rows untouched.
"""

import pytest
from datetime import datetime

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from db.models import Base, Article
from db.migrations import run_migrations, migrate_article_sources


@pytest.fixture
def engine(tmp_path):
    db_path = tmp_path / "test_migration.db"
    eng = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    factory = sessionmaker(bind=engine)
    s = factory()
    yield s
    s.close()


def _insert_article(session, source: str, source_id: str) -> int:
    article = Article(
        source=source,
        source_id=source_id,
        title=f"Test article from {source}",
        content="Test content",
        collected_at=datetime.utcnow(),
    )
    session.add(article)
    session.commit()
    return article.id


class TestMigrateArticleSources:
    """Migration rewrites legacy Article.source values in place."""

    def test_clawfeed_becomes_social_kol(self, session):
        aid = _insert_article(session, "clawfeed", "cf:1")
        counts = migrate_article_sources(session)
        article = session.query(Article).get(aid)
        assert article.source == "social_kol"
        assert counts["clawfeed"] > 0

    def test_github_becomes_github_trending(self, session):
        aid = _insert_article(session, "github", "gh:1")
        counts = migrate_article_sources(session)
        article = session.query(Article).get(aid)
        assert article.source == "github_trending"
        assert counts["github"] > 0

    def test_webpage_monitor_becomes_website_monitor(self, session):
        aid = _insert_article(session, "webpage_monitor", "wm:1")
        counts = migrate_article_sources(session)
        article = session.query(Article).get(aid)
        assert article.source == "website_monitor"
        assert counts["webpage_monitor"] > 0

    def test_unrelated_rows_untouched(self, session):
        aid_hn = _insert_article(session, "hackernews", "hn:1")
        aid_rss = _insert_article(session, "rss", "rss:1")
        _insert_article(session, "clawfeed", "cf:2")

        migrate_article_sources(session)

        assert session.query(Article).get(aid_hn).source == "hackernews"
        assert session.query(Article).get(aid_rss).source == "rss"

    def test_migration_is_idempotent(self, session):
        aid = _insert_article(session, "clawfeed", "cf:3")

        counts1 = migrate_article_sources(session)
        assert counts1["clawfeed"] == 1

        counts2 = migrate_article_sources(session)
        assert counts2["clawfeed"] == 0

        article = session.query(Article).get(aid)
        assert article.source == "social_kol"

    def test_migration_does_not_delete_articles(self, session):
        _insert_article(session, "clawfeed", "cf:4")
        _insert_article(session, "github", "gh:2")
        _insert_article(session, "webpage_monitor", "wm:2")
        _insert_article(session, "hackernews", "hn:2")

        before_count = session.query(Article).count()
        migrate_article_sources(session)
        after_count = session.query(Article).count()

        assert after_count == before_count

    def test_migration_does_not_alter_source_id(self, session):
        aid = _insert_article(session, "clawfeed", "cf:5")
        migrate_article_sources(session)
        article = session.query(Article).get(aid)
        assert article.source_id == "cf:5"

    def test_migration_does_not_alter_content(self, session):
        aid = _insert_article(session, "github", "gh:3")
        original = session.query(Article).get(aid)
        original_title = original.title
        original_content = original.content

        migrate_article_sources(session)

        refreshed = session.query(Article).get(aid)
        assert refreshed.title == original_title
        assert refreshed.content == original_content

    def test_all_legacy_names_rewritten(self, session):
        _insert_article(session, "clawfeed", "cf:6")
        _insert_article(session, "github", "gh:4")
        _insert_article(session, "webpage_monitor", "wm:3")

        migrate_article_sources(session)

        legacy_count = (
            session.query(Article)
            .filter(Article.source.in_(["clawfeed", "github", "webpage_monitor"]))
            .count()
        )
        assert legacy_count == 0


class TestMigrationWiredToStartup:
    """migrate_article_sources runs during init_db, not just as dead code."""

    def test_init_db_canonicalizes_legacy_articles(self, tmp_path):
        """Legacy articles inserted before init_db should be canonicalized after it runs."""
        from unittest.mock import patch
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        db_path = tmp_path / "startup_test.db"
        eng = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(eng)
        factory = sessionmaker(bind=eng)

        # Insert legacy articles directly (simulating pre-V2.1 state)
        session = factory()
        _insert_article(session, "clawfeed", "startup:cf:1")
        _insert_article(session, "github", "startup:gh:1")
        _insert_article(session, "webpage_monitor", "startup:wm:1")
        _insert_article(session, "hackernews", "startup:hn:1")
        session.close()

        # Patch database module to use our test engine/session
        with patch("db.database.get_engine", return_value=eng), \
             patch("db.database.get_session", side_effect=lambda: factory()), \
             patch("db.database._SessionFactory", factory):
            from db.database import init_db
            init_db()

        # Verify: legacy names should be gone
        session = factory()
        legacy_count = (
            session.query(Article)
            .filter(Article.source.in_(["clawfeed", "github", "webpage_monitor"]))
            .count()
        )
        assert legacy_count == 0, "init_db should have canonicalized legacy article sources"

        # Verify: canonical names present
        canonical_sources = {
            row[0] for row in session.query(Article.source).distinct().all()
        }
        assert "social_kol" in canonical_sources
        assert "github_trending" in canonical_sources
        assert "website_monitor" in canonical_sources
        assert "hackernews" in canonical_sources  # untouched
        session.close()

    def test_init_db_fails_fast_if_canonicalization_errors(self, tmp_path):
        """If migrate_article_sources raises, init_db must propagate — not swallow."""
        from unittest.mock import patch

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        db_path = tmp_path / "failfast_test.db"
        eng = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(eng)
        factory = sessionmaker(bind=eng)

        def _exploding_migration(session):
            raise RuntimeError("simulated migration failure")

        with patch("db.database.get_engine", return_value=eng), \
             patch("db.database.get_session", side_effect=lambda: factory()), \
             patch("db.database._SessionFactory", factory), \
             patch("db.migrations.migrate_article_sources", _exploding_migration):
            from db.database import init_db
            with pytest.raises(RuntimeError, match="simulated migration failure"):
                init_db()
