"""Database connection and initialization."""

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config import DATA_DIR, DB_PATH
from db.models import Base
import events.models  # noqa: F401 — register Event/EventArticle with Base.metadata
import users.models  # noqa: F401 — register UserProfile with Base.metadata

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable WAL journal mode for better concurrent write performance."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def get_engine() -> Engine:
    """Get or create the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{DB_PATH}",
            echo=False,
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        event.listen(_engine, "connect", _set_sqlite_pragma)
    return _engine


def get_session() -> Session:
    """Create a new database session."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine())
    return _SessionFactory()


def init_db() -> None:
    """Create all tables if they don't exist, then run migrations and seed."""
    from db.migrations import run_migrations

    engine = get_engine()
    Base.metadata.create_all(engine)
    run_migrations(engine)
    _seed_registry_if_needed()
    _canonicalize_article_sources()


def _canonicalize_article_sources() -> None:
    """Rewrite any legacy Article.source values to canonical V2 names.

    Fail-fast: runtime queries use canonical names only (no read-time shims),
    so if this migration fails, historical data becomes invisible. Letting
    the app start in that state would be silently broken.
    """
    from db.migrations import migrate_article_sources

    session = get_session()
    try:
        migrate_article_sources(session)
    finally:
        session.close()


def _seed_registry_if_needed() -> None:
    """Ensure default source registry rows exist. Insert-only; runs every init but is idempotent."""
    from sources.seed import seed_source_registry

    session = get_session()
    try:
        seed_source_registry(session)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Failed to seed source registry")
    finally:
        session.close()
