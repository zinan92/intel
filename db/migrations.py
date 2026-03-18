"""Idempotent database migrations for park-intel.

SQLite doesn't support full ALTER TABLE, but does support ADD COLUMN
for nullable columns. Each migration checks if the column exists first.
"""

import logging
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def _column_exists(engine: Engine, table: str, column: str) -> bool:
    """Check if a column exists in the given table."""
    with engine.connect() as conn:
        result = conn.execute(text(f"PRAGMA table_info({table})"))
        columns = [row[1] for row in result]
        return column in columns


def _table_exists(engine: Engine, table: str) -> bool:
    """Check if a table exists in the database."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": table},
        )
        return result.fetchone() is not None


_LEGACY_TO_CANONICAL: dict[str, str] = {
    "clawfeed": "social_kol",
    "github": "github_trending",
    "webpage_monitor": "website_monitor",
}


def migrate_article_sources(session) -> dict[str, int]:
    """Rewrite legacy Article.source values to canonical V2 names.

    Idempotent: only updates rows that still have legacy names.
    Returns a dict of {legacy_name: count_updated}.
    """
    from db.models import Article

    counts: dict[str, int] = {}
    for legacy, canonical in _LEGACY_TO_CANONICAL.items():
        rows = session.query(Article).filter(Article.source == legacy).all()
        count = 0
        for article in rows:
            article.source = canonical
            count += 1
        if count > 0:
            session.commit()
            logger.info("Migrated %d articles: %s → %s", count, legacy, canonical)
        counts[legacy] = count

    return counts


def run_migrations(engine: Engine) -> None:
    """Run all pending migrations idempotently."""
    # Column-add migrations for existing tables
    migrations = [
        ("articles", "relevance_score", "INTEGER"),
        ("articles", "narrative_tags", "TEXT"),
        ("articles", "tickers", "TEXT"),
    ]

    with engine.connect() as conn:
        for table, column, col_type in migrations:
            if not _column_exists(engine, table, column):
                logger.info("Adding column %s.%s (%s)", table, column, col_type)
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                conn.commit()
            else:
                logger.debug("Column %s.%s already exists, skipping", table, column)

    # Table-level migrations: create new tables if missing
    if not _table_exists(engine, "source_registry"):
        logger.info("Creating source_registry table via migration")
        from db.models import SourceRegistry
        SourceRegistry.__table__.create(engine)
        logger.info("source_registry table created")

    # Event aggregation tables
    if not _table_exists(engine, "events"):
        logger.info("Creating events table via migration")
        from events.models import Event
        Event.__table__.create(engine)
        logger.info("events table created")

    if not _table_exists(engine, "event_articles"):
        logger.info("Creating event_articles table via migration")
        from events.models import EventArticle
        EventArticle.__table__.create(engine)
        logger.info("event_articles table created")

    # User profile table
    if not _table_exists(engine, "user_profiles"):
        logger.info("Creating user_profiles table via migration")
        from users.models import UserProfile
        UserProfile.__table__.create(engine)
        logger.info("user_profiles table created")

    # Partial unique index: prevent duplicate active events for same tag
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_events_tag_active "
            "ON events (narrative_tag) WHERE status = 'active'"
        ))
        conn.commit()
