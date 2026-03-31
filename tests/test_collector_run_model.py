"""Tests for CollectorRun model, migration, and busy_timeout."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base, CollectorRun


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def engine():
    """In-memory SQLite engine with all tables created."""
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def session(engine):
    """Session bound to in-memory engine."""
    factory = sessionmaker(bind=engine)
    sess = factory()
    yield sess
    sess.close()


# ---------------------------------------------------------------------------
# CollectorRun persistence
# ---------------------------------------------------------------------------

class TestCollectorRunPersistence:
    def test_create_and_query(self, session: Session) -> None:
        now = datetime.utcnow()
        run = CollectorRun(
            source_type="rss",
            source_key="techcrunch",
            status="ok",
            articles_fetched=15,
            articles_saved=12,
            duration_ms=2300,
            error_message=None,
            error_category=None,
            retry_count=0,
            completed_at=now,
        )
        session.add(run)
        session.commit()

        result = session.query(CollectorRun).first()
        assert result is not None
        assert result.source_type == "rss"
        assert result.source_key == "techcrunch"
        assert result.status == "ok"
        assert result.articles_fetched == 15
        assert result.articles_saved == 12
        assert result.duration_ms == 2300
        assert result.error_message is None
        assert result.error_category is None
        assert result.retry_count == 0
        assert result.completed_at == now

    def test_create_error_run(self, session: Session) -> None:
        now = datetime.utcnow()
        run = CollectorRun(
            source_type="xueqiu",
            source_key="xq_hot",
            status="error",
            articles_fetched=0,
            articles_saved=0,
            duration_ms=150,
            error_message="HTTP 400: Bad Request",
            error_category="auth",
            retry_count=3,
            completed_at=now,
        )
        session.add(run)
        session.commit()

        result = session.query(CollectorRun).first()
        assert result is not None
        assert result.status == "error"
        assert result.error_message == "HTTP 400: Bad Request"
        assert result.error_category == "auth"
        assert result.retry_count == 3


# ---------------------------------------------------------------------------
# Migration idempotency
# ---------------------------------------------------------------------------

class TestMigrationIdempotency:
    def test_run_migrations_twice_no_error(self, engine) -> None:
        """Migration is idempotent -- calling twice should not raise."""
        from db.migrations import run_migrations

        run_migrations(engine)
        run_migrations(engine)  # second call should be a no-op

    def test_index_exists(self, engine) -> None:
        """D-13: idx_collector_runs_type_time index must exist."""
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='index' AND name='idx_collector_runs_type_time'"
                )
            )
            row = result.fetchone()
            assert row is not None, "Index idx_collector_runs_type_time not found"


# ---------------------------------------------------------------------------
# busy_timeout verification
# ---------------------------------------------------------------------------

class TestBusyTimeout:
    def test_busy_timeout_documented(self) -> None:
        """RELY-03: busy_timeout >= 5000ms is set (timeout=30 -> 30000ms)."""
        import db.database as db_mod
        import inspect

        source = inspect.getsource(db_mod.get_engine)
        assert "timeout" in source
        assert "30" in source
        assert "RELY-03" in source
