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
    # Table-level migrations first. Some older DBs only have articles, and
    # column migrations below must not ALTER a table that does not exist yet.
    if not _table_exists(engine, "source_registry"):
        logger.info("Creating source_registry table via migration")
        from db.models import SourceRegistry
        SourceRegistry.__table__.create(engine)
        logger.info("source_registry table created")

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

    if not _table_exists(engine, "user_profiles"):
        logger.info("Creating user_profiles table via migration")
        from users.models import UserProfile
        UserProfile.__table__.create(engine)
        logger.info("user_profiles table created")

    if not _table_exists(engine, "briefs"):
        logger.info("Creating briefs table via migration")
        from briefs.models import Brief
        Brief.__table__.create(engine)
        logger.info("briefs table created")

    if not _table_exists(engine, "collector_runs"):
        logger.info("Creating collector_runs table via migration")
        from db.models import CollectorRun
        CollectorRun.__table__.create(engine)
        logger.info("collector_runs table created")

    # Column-add migrations for existing tables
    migrations = [
        ("articles", "relevance_score", "INTEGER"),
        ("articles", "narrative_tags", "TEXT"),
        ("articles", "tickers", "TEXT"),
        ("articles", "collection_lane", "TEXT"),
        ("articles", "triage_bucket", "TEXT"),
        ("articles", "triage_status", "TEXT"),
        ("articles", "triage_direction", "TEXT"),
        ("articles", "triage_rationale", "TEXT"),
        ("articles", "triage_assets", "TEXT"),
        ("articles", "triage_watch_for", "TEXT"),
        ("articles", "triage_scenario_bull", "TEXT"),
        ("articles", "triage_scenario_bear", "TEXT"),
        ("articles", "triage_model", "TEXT"),
        ("articles", "triage_error", "TEXT"),
        ("articles", "triage_attempts", "INTEGER"),
        ("articles", "triaged_at", "DATETIME"),
        ("source_registry", "lane", "TEXT"),
        ("source_registry", "schedule_seconds", "INTEGER"),
        ("collector_runs", "articles_duplicate", "INTEGER"),
        ("collector_runs", "articles_failed", "INTEGER"),
        ("collector_runs", "articles_missing_timestamp", "INTEGER"),
        ("collector_runs", "articles_invalid_timestamp", "INTEGER"),
        ("events", "narrative_summary", "TEXT"),
        ("events", "prev_signal_score", "REAL"),
        ("events", "trading_play", "TEXT"),
        ("events", "outcome_data", "TEXT"),
        ("briefs", "provider", "TEXT"),
    ]

    with engine.connect() as conn:
        for table, column, col_type in migrations:
            if not _column_exists(engine, table, column):
                logger.info("Adding column %s.%s (%s)", table, column, col_type)
                defaulted_columns = {
                    ("articles", "collection_lane"): "TEXT NOT NULL DEFAULT 'hourly'",
                    ("articles", "triage_attempts"): "INTEGER NOT NULL DEFAULT 0",
                    ("source_registry", "lane"): "TEXT NOT NULL DEFAULT 'hourly'",
                    ("collector_runs", "articles_duplicate"): "INTEGER NOT NULL DEFAULT 0",
                    ("collector_runs", "articles_failed"): "INTEGER NOT NULL DEFAULT 0",
                    ("collector_runs", "articles_missing_timestamp"): "INTEGER NOT NULL DEFAULT 0",
                    ("collector_runs", "articles_invalid_timestamp"): "INTEGER NOT NULL DEFAULT 0",
                }
                definition = defaulted_columns.get((table, column), col_type)
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
                conn.commit()
            else:
                logger.debug("Column %s.%s already exists, skipping", table, column)

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

    # Keep the backfill for databases upgraded by an earlier revision that
    # added the lane columns as nullable. New upgrades use NOT NULL defaults
    # above, while this remains harmless and idempotent.
    with engine.connect() as conn:
        if _table_exists(engine, "articles") and _column_exists(engine, "articles", "collection_lane"):
            conn.execute(text(
                "UPDATE articles SET collection_lane = 'hourly' "
                "WHERE collection_lane IS NULL"
            ))
            if _column_exists(engine, "articles", "triage_attempts"):
                conn.execute(text(
                    "UPDATE articles SET triage_attempts = 0 "
                    "WHERE triage_attempts IS NULL"
                ))
        if _table_exists(engine, "source_registry") and _column_exists(engine, "source_registry", "lane"):
            conn.execute(text(
                "UPDATE source_registry SET lane = 'hourly' WHERE lane IS NULL"
            ))
        conn.commit()

    # Partial unique index: prevent duplicate active events for same tag
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_events_tag_active "
            "ON events (narrative_tag) WHERE status = 'active'"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_collector_runs_completed_at "
            "ON collector_runs (completed_at)"
        ))
        conn.commit()
