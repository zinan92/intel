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
        ("events", "narrative_summary", "TEXT"),
        ("events", "prev_signal_score", "REAL"),
        ("events", "trading_play", "TEXT"),
        ("events", "outcome_data", "TEXT"),
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

    # Briefs table
    if not _table_exists(engine, "briefs"):
        logger.info("Creating briefs table via migration")
        from briefs.models import Brief
        Brief.__table__.create(engine)
        logger.info("briefs table created")

    # Collector run log table (Phase 1: reliability instrumentation)
    if not _table_exists(engine, "collector_runs"):
        logger.info("Creating collector_runs table via migration")
        from db.models import CollectorRun
        CollectorRun.__table__.create(engine)
        logger.info("collector_runs table created")

    # expected_freshness_hours column on source_registry (Phase 2: health visibility)
    if _table_exists(engine, "source_registry"):
        if not _column_exists(engine, "source_registry", "expected_freshness_hours"):
            logger.info("Adding column source_registry.expected_freshness_hours (REAL)")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE source_registry ADD COLUMN expected_freshness_hours REAL"))
                conn.commit()

        # Seed defaults for rows where expected_freshness_hours is NULL (idempotent)
        _freshness_defaults = {
            "rss": 2.0,
            "hackernews": 2.0,
            "reddit": 2.0,
            "github_release": 12.0,
            "github_trending": 12.0,
            "yahoo_finance": 6.0,
        }
        with engine.connect() as conn:
            for source_type, hours in _freshness_defaults.items():
                conn.execute(
                    text(
                        "UPDATE source_registry "
                        "SET expected_freshness_hours = :hours "
                        "WHERE source_type = :st AND expected_freshness_hours IS NULL"
                    ),
                    {"hours": hours, "st": source_type},
                )
            # All others default to 4.0
            conn.execute(
                text(
                    "UPDATE source_registry "
                    "SET expected_freshness_hours = 4.0 "
                    "WHERE expected_freshness_hours IS NULL"
                )
            )
            conn.commit()
        logger.info("Seeded expected_freshness_hours defaults for source_registry")

    # Partial unique index: prevent duplicate active events for same tag
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_events_tag_active "
            "ON events (narrative_tag) WHERE status = 'active'"
        ))
        conn.commit()
