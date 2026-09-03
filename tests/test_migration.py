"""Tests for database migration idempotency."""

import pytest
from sqlalchemy import create_engine, text

from db.migrations import run_migrations, _column_exists
from db.models import Base


@pytest.fixture
def engine(tmp_path):
    db_path = tmp_path / "test_migration.db"
    eng = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(eng)
    return eng


def test_migration_adds_columns(engine):
    """Columns should be added if they don't exist."""
    # Drop the columns first (simulate old schema)
    # SQLite doesn't support DROP COLUMN easily, so create a fresh table without them
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS articles"))
        conn.execute(text("""
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY,
                source VARCHAR NOT NULL,
                source_id VARCHAR UNIQUE,
                title VARCHAR,
                content TEXT,
                tags VARCHAR,
                score INTEGER DEFAULT 0,
                collected_at DATETIME NOT NULL
            )
        """))
        conn.commit()

        conn.execute(text("DROP TABLE IF EXISTS briefs"))
        conn.execute(text("""
            CREATE TABLE briefs (
                id INTEGER PRIMARY KEY,
                content TEXT NOT NULL,
                article_count INTEGER DEFAULT 0,
                signal_count INTEGER DEFAULT 0,
                status VARCHAR DEFAULT 'published',
                created_at DATETIME
            )
        """))
        conn.commit()

        conn.execute(text("DROP TABLE IF EXISTS events"))
        conn.execute(text("""
            CREATE TABLE events (
                id INTEGER PRIMARY KEY,
                narrative_tag VARCHAR NOT NULL,
                window_start DATETIME NOT NULL,
                window_end DATETIME NOT NULL,
                status VARCHAR DEFAULT 'active'
            )
        """))
        conn.commit()

    assert not _column_exists(engine, "articles", "relevance_score")
    assert not _column_exists(engine, "articles", "narrative_tags")
    assert not _column_exists(engine, "articles", "relevance_provider")
    assert not _column_exists(engine, "articles", "relevance_scored_at")
    assert not _column_exists(engine, "briefs", "provider")
    assert not _column_exists(engine, "briefs", "scoring_coverage")
    assert not _column_exists(engine, "events", "narrative_provider")

    run_migrations(engine)

    assert _column_exists(engine, "articles", "relevance_score")
    assert _column_exists(engine, "articles", "narrative_tags")
    assert _column_exists(engine, "articles", "relevance_provider")
    assert _column_exists(engine, "articles", "relevance_scored_at")
    assert _column_exists(engine, "briefs", "provider")
    assert _column_exists(engine, "briefs", "candidate_article_count")
    assert _column_exists(engine, "briefs", "scored_article_count")
    assert _column_exists(engine, "briefs", "scoring_coverage")
    assert _column_exists(engine, "events", "narrative_provider")


def test_migration_idempotent(engine):
    """Running migrations twice should not fail."""
    run_migrations(engine)
    run_migrations(engine)  # Should not raise

    assert _column_exists(engine, "articles", "relevance_score")
    assert _column_exists(engine, "articles", "narrative_tags")


def test_column_exists_check(engine):
    assert _column_exists(engine, "articles", "source")
    assert _column_exists(engine, "articles", "title")
    assert not _column_exists(engine, "articles", "nonexistent_column")
