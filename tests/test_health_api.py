"""Tests for health API: compute_status, _check_source_disabled, heartbeat, migration."""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


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
