"""Tests for CollectorRun DB recording from scheduler.

Uses in-memory SQLite to verify _record_collector_run persists all fields
and _cleanup_old_runs deletes rows older than 30 days.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base, CollectorRun
from sources.errors import CollectorResult


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database with CollectorRun table."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    yield session
    session.close()


class TestRecordCollectorRun:
    """_record_collector_run writes CollectorRun rows to the database."""

    def test_success_result_persisted(self, db_session):
        """Successful collection writes all fields correctly."""
        from scheduler import _record_collector_run

        result = CollectorResult(
            source_type="hackernews",
            source_key="hackernews:top",
            status="ok",
            articles_fetched=42,
            articles_saved=0,
            duration_ms=1500,
            error_message=None,
            error_category=None,
            retry_count=0,
        )

        with patch("db.database.get_session", return_value=db_session):
            _record_collector_run(result, saved_count=35)

        runs = db_session.query(CollectorRun).all()
        assert len(runs) == 1
        run = runs[0]
        assert run.source_type == "hackernews"
        assert run.source_key == "hackernews:top"
        assert run.status == "ok"
        assert run.articles_fetched == 42
        assert run.articles_saved == 35  # saved_count override
        assert run.duration_ms == 1500
        assert run.error_message is None
        assert run.error_category is None
        assert run.retry_count == 0
        assert run.completed_at is not None

    def test_error_result_persisted(self, db_session):
        """Failed collection writes error details."""
        from scheduler import _record_collector_run

        result = CollectorResult(
            source_type="rss",
            source_key="rss:techcrunch",
            status="error",
            articles_fetched=0,
            articles_saved=0,
            duration_ms=3200,
            error_message="Connection refused",
            error_category="transient",
            retry_count=2,
        )

        with patch("db.database.get_session", return_value=db_session):
            _record_collector_run(result, saved_count=0)

        runs = db_session.query(CollectorRun).all()
        assert len(runs) == 1
        run = runs[0]
        assert run.status == "error"
        assert run.error_message == "Connection refused"
        assert run.error_category == "transient"
        assert run.retry_count == 2


class TestCleanupOldRuns:
    """_cleanup_old_runs deletes rows older than 30 days."""

    def test_old_rows_deleted_recent_kept(self, db_session):
        """Only rows older than 30 days are deleted."""
        from scheduler import _cleanup_old_runs

        now = datetime.now(timezone.utc)

        # Old row (40 days ago)
        old_run = CollectorRun(
            source_type="rss",
            source_key="rss:old",
            status="ok",
            articles_fetched=10,
            articles_saved=8,
            duration_ms=500,
            retry_count=0,
            completed_at=now - timedelta(days=40),
        )

        # Recent row (5 days ago)
        recent_run = CollectorRun(
            source_type="rss",
            source_key="rss:recent",
            status="ok",
            articles_fetched=20,
            articles_saved=15,
            duration_ms=800,
            retry_count=0,
            completed_at=now - timedelta(days=5),
        )

        db_session.add(old_run)
        db_session.add(recent_run)
        db_session.commit()

        assert db_session.query(CollectorRun).count() == 2

        with patch("db.database.get_session", return_value=db_session):
            _cleanup_old_runs()

        remaining = db_session.query(CollectorRun).all()
        assert len(remaining) == 1
        assert remaining[0].source_key == "rss:recent"
