"""Database connection and initialization."""

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config import DATA_DIR, DB_PATH
from db.models import Base

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
    """Create all tables if they don't exist, then run migrations."""
    from db.migrations import run_migrations

    engine = get_engine()
    Base.metadata.create_all(engine)
    run_migrations(engine)
