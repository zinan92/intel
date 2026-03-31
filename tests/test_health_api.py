"""Tests for health API: compute_status, _check_source_disabled, heartbeat, migration, endpoints."""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# compute_status tests
# ---------------------------------------------------------------------------


class TestComputeStatus:
    """Test the compute_status function for all status transitions."""

    def test_ok_within_freshness(self):
        from api.health_routes import compute_status

        assert compute_status(age_hours=1.0, expected_freshness_hours=2.0, last_error_category=None) == "ok"

    def test_stale_between_1x_and_2x(self):
        from api.health_routes import compute_status

        assert compute_status(age_hours=3.0, expected_freshness_hours=2.0, last_error_category=None) == "stale"

    def test_degraded_beyond_2x(self):
        from api.health_routes import compute_status

        assert compute_status(age_hours=5.0, expected_freshness_hours=2.0, last_error_category=None) == "degraded"

    def test_error_when_error_category_set(self):
        from api.health_routes import compute_status

        assert compute_status(age_hours=1.0, expected_freshness_hours=2.0, last_error_category="auth") == "error"

    def test_no_data_when_age_is_none(self):
        from api.health_routes import compute_status

        assert compute_status(age_hours=None, expected_freshness_hours=2.0, last_error_category=None) == "no_data"

    def test_ok_fallback_when_expected_is_none(self):
        """When expected_freshness_hours is None, fallback to 4h default."""
        from api.health_routes import compute_status

        # 1h age with 4h default -> ok
        assert compute_status(age_hours=1.0, expected_freshness_hours=None, last_error_category=None) == "ok"

    def test_stale_fallback_when_expected_is_none(self):
        from api.health_routes import compute_status

        # 5h age with 4h default -> stale (between 1x and 2x)
        assert compute_status(age_hours=5.0, expected_freshness_hours=None, last_error_category=None) == "stale"


# ---------------------------------------------------------------------------
# Volume anomaly tests
# ---------------------------------------------------------------------------


class TestVolumeAnomaly:
    """Test volume anomaly computation logic."""

    def test_anomaly_when_below_50_percent(self):
        from api.health_routes import compute_volume_anomaly

        # 24h count = 5, 7-day avg = 20 per day -> 5 < 20*0.5=10 -> anomaly
        assert compute_volume_anomaly(articles_24h=5, articles_7d_avg=20.0, days_with_data=7) is True

    def test_no_anomaly_when_above_50_percent(self):
        from api.health_routes import compute_volume_anomaly

        # 24h count = 15, 7-day avg = 20 -> 15 >= 10 -> no anomaly
        assert compute_volume_anomaly(articles_24h=15, articles_7d_avg=20.0, days_with_data=7) is False

    def test_none_when_insufficient_data(self):
        from api.health_routes import compute_volume_anomaly

        # fewer than 3 days of data -> None
        assert compute_volume_anomaly(articles_24h=5, articles_7d_avg=20.0, days_with_data=2) is None


# ---------------------------------------------------------------------------
# _check_source_disabled tests
# ---------------------------------------------------------------------------


class TestCheckSourceDisabled:
    """Test disabled source detection based on env vars."""

    def test_github_release_disabled_when_no_token(self):
        from api.health_routes import _check_source_disabled

        with patch.dict(os.environ, {}, clear=False):
            # Remove GITHUB_TOKEN if present
            env = {k: v for k, v in os.environ.items() if k != "GITHUB_TOKEN"}
            with patch.dict(os.environ, env, clear=True):
                result = _check_source_disabled("github_release")
                assert result is not None
                assert "GITHUB_TOKEN" in result

    def test_rss_never_disabled(self):
        from api.health_routes import _check_source_disabled

        result = _check_source_disabled("rss")
        assert result is None

    def test_hackernews_never_disabled(self):
        from api.health_routes import _check_source_disabled

        result = _check_source_disabled("hackernews")
        assert result is None


# ---------------------------------------------------------------------------
# Heartbeat tests
# ---------------------------------------------------------------------------


class TestHeartbeat:
    """Test scheduler heartbeat functions."""

    def test_heartbeat_none_before_start(self):
        import scheduler

        # Reset heartbeat state
        scheduler._heartbeat_ts = None
        assert scheduler.get_heartbeat() is None

    def test_heartbeat_set_after_update(self):
        import scheduler

        scheduler._heartbeat_ts = None
        scheduler._update_heartbeat()
        result = scheduler.get_heartbeat()
        assert result is not None
        assert isinstance(result, datetime)
        # Should be recent (within last second)
        assert (datetime.now(timezone.utc) - result).total_seconds() < 2


# ---------------------------------------------------------------------------
# Migration tests
# ---------------------------------------------------------------------------


class TestExpectedFreshnessHoursMigration:
    """Test expected_freshness_hours column migration and seeding."""

    def test_column_exists_after_migration(self):
        from sqlalchemy import create_engine, text

        from db.migrations import run_migrations
        from db.models import Base, SourceRegistry

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        run_migrations(engine)

        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA table_info(source_registry)"))
            columns = [row[1] for row in result]
            assert "expected_freshness_hours" in columns

    def test_migration_seeds_defaults(self):
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker

        from db.migrations import run_migrations
        from db.models import Base, SourceRegistry

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)

        Session = sessionmaker(bind=engine)
        session = Session()

        # Insert source registry rows with NULL expected_freshness_hours
        for source_type in ["rss", "hackernews", "reddit", "github_release", "yahoo_finance", "website_monitor"]:
            session.add(SourceRegistry(
                source_key=f"test_{source_type}",
                source_type=source_type,
                display_name=f"Test {source_type}",
                config_json="{}",
            ))
        session.commit()

        run_migrations(engine)

        # Verify defaults were seeded
        rss = session.query(SourceRegistry).filter_by(source_key="test_rss").one()
        assert rss.expected_freshness_hours == 2.0

        hn = session.query(SourceRegistry).filter_by(source_key="test_hackernews").one()
        assert hn.expected_freshness_hours == 2.0

        reddit = session.query(SourceRegistry).filter_by(source_key="test_reddit").one()
        assert reddit.expected_freshness_hours == 2.0

        gh = session.query(SourceRegistry).filter_by(source_key="test_github_release").one()
        assert gh.expected_freshness_hours == 12.0

        yahoo = session.query(SourceRegistry).filter_by(source_key="test_yahoo_finance").one()
        assert yahoo.expected_freshness_hours == 6.0

        # website_monitor falls into "others" category -> 4.0
        wm = session.query(SourceRegistry).filter_by(source_key="test_website_monitor").one()
        assert wm.expected_freshness_hours == 4.0

        session.close()


# ---------------------------------------------------------------------------
# Endpoint integration tests
# ---------------------------------------------------------------------------


def _make_test_db():
    """Create an in-memory test database with seeded data.

    Uses StaticPool to ensure all connections share the same in-memory database.
    """
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from db.models import Base, CollectorRun, SourceRegistry

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    # Run migrations to seed expected_freshness_hours
    from db.migrations import run_migrations
    run_migrations(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    now = datetime.now(timezone.utc)

    # Insert sources
    session.add(SourceRegistry(
        source_key="test_rss_feed",
        source_type="rss",
        display_name="Test RSS",
        config_json="{}",
        is_active=1,
        expected_freshness_hours=2.0,
    ))
    session.add(SourceRegistry(
        source_key="test_github",
        source_type="github_release",
        display_name="Test GitHub",
        config_json="{}",
        is_active=1,
        expected_freshness_hours=12.0,
    ))
    session.add(SourceRegistry(
        source_key="test_hn",
        source_type="hackernews",
        display_name="Test HN",
        config_json="{}",
        is_active=1,
        expected_freshness_hours=2.0,
    ))

    # Insert collector runs (RSS: recent ok, GitHub: old error)
    session.add(CollectorRun(
        source_type="rss",
        source_key="test_rss_feed",
        status="ok",
        articles_fetched=10,
        articles_saved=5,
        duration_ms=1200,
        completed_at=now - timedelta(hours=1),
    ))
    # Add some historical runs for volume calculation
    for day_offset in range(7):
        session.add(CollectorRun(
            source_type="rss",
            source_key="test_rss_feed",
            status="ok",
            articles_fetched=10,
            articles_saved=5,
            duration_ms=1000,
            completed_at=now - timedelta(days=day_offset, hours=12),
        ))

    session.add(CollectorRun(
        source_type="github_release",
        source_key="test_github",
        status="error",
        articles_fetched=0,
        articles_saved=0,
        duration_ms=500,
        error_message="401 Unauthorized",
        error_category="auth",
        completed_at=now - timedelta(hours=2),
    ))

    # HN has no runs (no_data case)

    session.commit()
    return engine, Session


@pytest.fixture
def test_client():
    """Create a FastAPI test client with in-memory DB."""
    engine, Session = _make_test_db()

    # Patch get_session to use our test database
    def _get_test_session():
        return Session()

    import scheduler
    scheduler._heartbeat_ts = datetime.now(timezone.utc)

    # Patch all get_session entry points to use the test database.
    # routes.py imports get_session at module level, so we must patch
    # the reference in each module that uses it.
    with patch("db.database.get_session", _get_test_session), \
         patch("api.health_routes.get_session", _get_test_session), \
         patch("api.routes.get_session", _get_test_session), \
         patch("db.database.init_db", return_value=None):
        from main import app
        client = TestClient(app)
        yield client


class TestHealthSourcesEndpoint:
    """Test GET /api/health/sources endpoint."""

    def test_returns_200_with_sources(self, test_client):
        resp = test_client.get("/api/health/sources")
        assert resp.status_code == 200
        data = resp.json()
        assert "sources" in data
        assert "scheduler_alive" in data
        assert isinstance(data["sources"], list)
        assert len(data["sources"]) == 3

    def test_source_has_required_fields(self, test_client):
        resp = test_client.get("/api/health/sources")
        data = resp.json()
        source = data["sources"][0]
        required_fields = [
            "source_type", "display_name", "status", "is_active",
            "freshness_age_hours", "expected_freshness_hours",
            "articles_24h", "articles_7d_avg", "volume_anomaly",
            "last_run_at", "last_run_status", "last_error",
            "last_error_category", "disabled_reason",
        ]
        for field in required_fields:
            assert field in source, f"Missing field: {field}"

    def test_rss_source_status_ok(self, test_client):
        resp = test_client.get("/api/health/sources")
        data = resp.json()
        rss = next(s for s in data["sources"] if s["source_type"] == "rss")
        assert rss["status"] == "ok"
        assert rss["last_run_status"] == "ok"
        assert rss["articles_24h"] > 0

    def test_github_source_status_error(self, test_client):
        """When GITHUB_TOKEN is set, error category from last run should surface."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}):
            resp = test_client.get("/api/health/sources")
            data = resp.json()
            gh = next(s for s in data["sources"] if s["source_type"] == "github_release")
            assert gh["status"] == "error"
            assert gh["last_error_category"] == "auth"

    def test_hn_source_no_data(self, test_client):
        resp = test_client.get("/api/health/sources")
        data = resp.json()
        hn = next(s for s in data["sources"] if s["source_type"] == "hackernews")
        assert hn["status"] == "no_data"
        assert hn["freshness_age_hours"] is None

    def test_disabled_source_detection(self, test_client):
        """GitHub source with no token should have disabled_reason."""
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_TOKEN"}
        with patch.dict(os.environ, env, clear=True):
            resp = test_client.get("/api/health/sources")
            data = resp.json()
            gh = next(s for s in data["sources"] if s["source_type"] == "github_release")
            assert gh["disabled_reason"] is not None
            assert "GITHUB_TOKEN" in gh["disabled_reason"]

    def test_scheduler_alive(self, test_client):
        resp = test_client.get("/api/health/sources")
        data = resp.json()
        assert data["scheduler_alive"] is True

    def test_volume_anomaly_for_new_source(self, test_client):
        """HN has no runs, so volume_anomaly should be None."""
        resp = test_client.get("/api/health/sources")
        data = resp.json()
        hn = next(s for s in data["sources"] if s["source_type"] == "hackernews")
        assert hn["volume_anomaly"] is None


class TestHealthSummaryEndpoint:
    """Test GET /api/health/summary endpoint."""

    def test_returns_200_with_stats(self, test_client):
        resp = test_client.get("/api/health/summary")
        assert resp.status_code == 200
        data = resp.json()
        required_fields = [
            "total_sources", "healthy_count", "stale_count",
            "degraded_count", "error_count", "disabled_count",
            "total_articles_24h", "scheduler_alive",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    def test_summary_counts(self, test_client):
        resp = test_client.get("/api/health/summary")
        data = resp.json()
        assert data["total_sources"] == 3
        assert data["scheduler_alive"] is True
        # At least 1 healthy (RSS is ok)
        assert data["healthy_count"] >= 1
        # GitHub is disabled (no token) and HN has no_data -> both count as disabled
        assert data["disabled_count"] >= 1


class TestExistingHealthEndpoint:
    """Ensure existing /api/health endpoint still works (D-02 backward compat)."""

    def test_existing_health_returns_200(self, test_client):
        resp = test_client.get("/api/health")
        assert resp.status_code == 200
