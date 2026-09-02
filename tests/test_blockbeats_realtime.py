"""Behavioral contract for the official BlockBeats Pro realtime source."""

from datetime import datetime
import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base, SourceRegistry
from sources.errors import SourceBlockedError, SourceConfigurationError


def _response(payload, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_blockbeats_normalizes_newsflash_and_preserves_both_links(monkeypatch):
    from collectors.blockbeats import fetch_blockbeats_newsflash

    monkeypatch.setenv("BLOCKBEATS_API_KEY", "unit-test-key")
    payload = {
        "status": 0,
        "message": "",
        "data": {
            "page": 1,
            "data": [{
                "id": 20260902001,
                "title": "Fed official comments on rates",
                "content": "<p>Rates may remain <strong>higher</strong>.</p>",
                "link": "https://www.theblockbeats.info/flash/20260902001",
                "url": "https://www.federalreserve.gov/example.htm",
                "source": "Federal Reserve",
                "create_time": "2026-09-02 16:02:03",
            }],
        },
    }

    with patch(
        "collectors.blockbeats.requests.get",
        return_value=_response(payload),
    ) as request:
        rows = fetch_blockbeats_newsflash(page_size=25, lang="cn")

    assert rows == [{
        "source": "blockbeats_newsflash",
        "source_id": "blockbeats_newsflash:20260902001",
        "author": "BlockBeats",
        "title": "Fed official comments on rates",
        "content": "Rates may remain higher.",
        "url": "https://www.theblockbeats.info/flash/20260902001",
        "upstream_url": "https://www.federalreserve.gov/example.htm",
        "upstream_attribution": "Federal Reserve",
        "tags": ["crypto-news", "blockbeats"],
        "score": 0,
        "published_at": datetime(2026, 9, 2, 8, 2, 3),
        "collection_lane": "realtime",
        "source_authority": "secondary",
        "corroboration_state": "unconfirmed",
        "pin_eligibility": "requires_independent_confirmation",
        "review_state": "needs_review",
        "_timestamp_status": "valid",
        "_provider_cursor": "20260902001",
    }]
    request.assert_called_once_with(
        "https://api-pro.theblockbeats.info/v1/newsflash",
        params={"page": 1, "size": 25, "lang": "cn"},
        headers={"api-key": "unit-test-key"},
        timeout=10,
    )


def test_blockbeats_html_sanitizer_preserves_boundaries_and_drops_scripts():
    from collectors.blockbeats import _plain_text

    assert _plain_text(
        "<p>first</p><p>second<br>line</p>"
        "<script>alert(1)</script><style>.bad{}</style>"
    ) == "first second line"


def test_blockbeats_rejects_unsafe_provider_urls(monkeypatch):
    from collectors.blockbeats import fetch_blockbeats_newsflash

    monkeypatch.setenv("BLOCKBEATS_API_KEY", "unit-test-key")
    with patch(
        "collectors.blockbeats.requests.get",
        return_value=_response({
            "status": 0,
            "message": "",
            "data": [{
                "id": 8,
                "title": "URL fixture",
                "content": "fixture",
                "link": "javascript:alert(1)",
                "url": "file:///etc/passwd",
                "create_time": "2026-09-02 16:02:03",
            }],
        }),
    ):
        row = fetch_blockbeats_newsflash()[0]

    assert row["url"] == "https://m.theblockbeats.info/flash/8"
    assert row["upstream_url"] is None


def test_blockbeats_accepts_unix_timestamp_and_fallback_id(monkeypatch):
    from collectors.blockbeats import fetch_blockbeats_newsflash

    monkeypatch.setenv("BLOCKBEATS_API_KEY", "unit-test-key")
    payload = {
        "status": 0,
        "message": "",
        "data": [{
            "title": "BTC moves",
            "content": "BTC moves",
            "link": "https://www.theblockbeats.info/flash/example",
            "create_time": "1788336123",
        }],
    }
    with patch(
        "collectors.blockbeats.requests.get",
        return_value=_response(payload),
    ):
        row = fetch_blockbeats_newsflash()[0]

    assert row["published_at"] == datetime(2026, 9, 2, 8, 2, 3)
    assert row["source_id"].startswith("blockbeats_newsflash:sha256:")


def test_blockbeats_empty_success_is_valid(monkeypatch):
    from collectors.blockbeats import fetch_blockbeats_newsflash

    monkeypatch.setenv("BLOCKBEATS_API_KEY", "unit-test-key")
    with patch(
        "collectors.blockbeats.requests.get",
        return_value=_response({"status": 0, "message": "", "data": []}),
    ):
        assert fetch_blockbeats_newsflash() == []


@pytest.mark.parametrize("payload", [
    {"status": 0, "data": None},
    {"status": 0, "data": {"data": "not-a-list"}},
    {"data": []},
])
def test_blockbeats_malformed_success_fails_visibly(monkeypatch, payload):
    from collectors.blockbeats import fetch_blockbeats_newsflash

    monkeypatch.setenv("BLOCKBEATS_API_KEY", "unit-test-key")
    with patch(
        "collectors.blockbeats.requests.get",
        return_value=_response(payload),
    ), pytest.raises((KeyError, TypeError)):
        fetch_blockbeats_newsflash()


@pytest.mark.parametrize("row", ["not-an-object", {"id": 9, "content": "missing title"}])
def test_blockbeats_nonempty_malformed_rows_cannot_be_empty_success(monkeypatch, row):
    from collectors.blockbeats import fetch_blockbeats_newsflash

    monkeypatch.setenv("BLOCKBEATS_API_KEY", "unit-test-key")
    with patch(
        "collectors.blockbeats.requests.get",
        return_value=_response({"status": 0, "message": "", "data": [row]}),
    ), pytest.raises(TypeError, match="no valid newsflash rows"):
        fetch_blockbeats_newsflash()


def test_blockbeats_missing_key_is_config_failure(monkeypatch):
    from sources.adapters import collect_from_source

    monkeypatch.delenv("BLOCKBEATS_API_KEY", raising=False)
    rows, result = collect_from_source({
        "source_key": "blockbeats_newsflash:main",
        "source_type": "blockbeats_newsflash",
        "config": {},
    })

    assert rows == []
    assert result.status == "error"
    assert result.error_category == "config"
    assert "BLOCKBEATS_API_KEY" in result.error_message


def test_blockbeats_reads_key_from_private_file(monkeypatch, tmp_path):
    from collectors.blockbeats import _api_key

    key_file = tmp_path / "blockbeats-key"
    key_file.write_text("unit-test-key\n", encoding="utf-8")
    monkeypatch.delenv("BLOCKBEATS_API_KEY", raising=False)
    monkeypatch.setenv("BLOCKBEATS_API_KEY_FILE", str(key_file))

    assert _api_key() == "unit-test-key"


@pytest.mark.parametrize("status", [101, 102])
def test_blockbeats_provider_auth_failure_does_not_retry(monkeypatch, status):
    from sources.adapters import collect_from_source

    monkeypatch.setenv("BLOCKBEATS_API_KEY", "unit-test-key")
    with patch(
        "collectors.blockbeats.requests.get",
        return_value=_response({
            "status": status,
            "message": "Invalid or expired API key",
            "data": None,
        }),
    ) as request:
        rows, result = collect_from_source({
            "source_key": "blockbeats_newsflash:main",
            "source_type": "blockbeats_newsflash",
            "config": {},
        })

    assert rows == []
    assert result.error_category == "auth"
    assert result.retry_count == 0
    assert request.call_count == 1


def test_blockbeats_rate_limit_is_provider_block(monkeypatch):
    from collectors.blockbeats import fetch_blockbeats_newsflash

    monkeypatch.setenv("BLOCKBEATS_API_KEY", "unit-test-key")
    with patch(
        "collectors.blockbeats.requests.get",
        return_value=_response({}, status_code=429),
    ), pytest.raises(SourceBlockedError, match="HTTP 429"):
        fetch_blockbeats_newsflash()


def test_blockbeats_status_100_is_visible_config_failure(monkeypatch):
    from collectors.blockbeats import fetch_blockbeats_newsflash

    monkeypatch.setenv("BLOCKBEATS_API_KEY", "unit-test-key")
    with patch(
        "collectors.blockbeats.requests.get",
        return_value=_response({
            "status": 100,
            "message": "Missing API key",
            "data": None,
        }),
    ), pytest.raises(SourceConfigurationError, match="Missing API key"):
        fetch_blockbeats_newsflash()


def test_blockbeats_invalid_timestamp_is_retained_and_flagged(monkeypatch):
    from collectors.blockbeats import fetch_blockbeats_newsflash

    monkeypatch.setenv("BLOCKBEATS_API_KEY", "unit-test-key")
    with patch(
        "collectors.blockbeats.requests.get",
        return_value=_response({
            "status": 0,
            "message": "",
            "data": [{
                "id": 7,
                "title": "Timestamp fixture",
                "content": "fixture",
                "create_time": "not-a-time",
            }],
        }),
    ):
        row = fetch_blockbeats_newsflash()[0]

    assert row["published_at"] is None
    assert row["_timestamp_status"] == "invalid"


def test_blockbeats_source_seeds_inactive_at_300_seconds(monkeypatch):
    from sources.registry import get_source_by_key
    from sources.seed import seed_source_registry

    monkeypatch.setenv("REALTIME_LANE_ENABLED", "1")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_source_registry(session)
        source = get_source_by_key(session, "blockbeats_newsflash:main")

    assert source is not None
    assert source.source_type == "blockbeats_newsflash"
    assert source.lane == "realtime"
    assert source.schedule_seconds == 300
    assert source.expected_freshness_hours == pytest.approx(0.1)
    assert source.is_active == 0


def test_blockbeats_activation_requires_key(monkeypatch):
    from scripts.activate_realtime_lane import _activation_blocker

    source = type("Source", (), {"source_type": "blockbeats_newsflash"})()
    monkeypatch.delenv("BLOCKBEATS_API_KEY", raising=False)
    monkeypatch.delenv("BLOCKBEATS_API_KEY_FILE", raising=False)
    assert _activation_blocker(source) == "BLOCKBEATS_API_KEY missing"
    monkeypatch.setenv("BLOCKBEATS_API_KEY", "unit-test-key")
    assert _activation_blocker(source) is None


def test_blockbeats_legacy_60_second_row_migrates_to_free_tier_baseline():
    from db.migrations import run_migrations
    from sources.registry import get_source_by_key

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(SourceRegistry(
            source_key="blockbeats_newsflash:main",
            source_type="blockbeats_newsflash",
            display_name="BlockBeats Newsflash",
            config_json=json.dumps({"page_size": 25, "lang": "en"}),
            is_active=1,
            lane="realtime",
            schedule_seconds=60,
        ))
        session.commit()

    run_migrations(engine)

    with Session(engine) as session:
        source = get_source_by_key(session, "blockbeats_newsflash:main")
        assert source.schedule_seconds == 300
        assert source.is_active == 1
        assert json.loads(source.config_json) == {"page_size": 25, "lang": "en"}


def test_blockbeats_provider_auth_failure_triggers_scheduler_cooldown(monkeypatch):
    import scheduler
    from sources.errors import CollectorResult

    source = type("Source", (), {
        "source_key": "blockbeats_newsflash:main",
        "source_type": "blockbeats_newsflash",
        "display_name": "BlockBeats Newsflash",
        "category": "crypto-news",
        "config_json": "{}",
        "lane": "realtime",
    })()
    session = MagicMock()
    monkeypatch.setenv("REALTIME_LANE_ENABLED", "1")
    monkeypatch.setattr("db.database.get_session", lambda: session)
    monkeypatch.setattr("sources.registry.list_active_sources", lambda _: [source])
    monkeypatch.setattr("sources.adapters.collect_from_source", lambda _: ([], CollectorResult(
        source_type="blockbeats_newsflash",
        source_key="blockbeats_newsflash:main",
        status="error",
        articles_fetched=0,
        articles_saved=0,
        duration_ms=1,
        error_message="invalid key",
        error_category="auth",
        retry_count=0,
        provider_blocked=True,
    )))
    monkeypatch.setattr(scheduler, "_record_collector_run", lambda *args, **kwargs: None)
    scheduler.reset_realtime_block("blockbeats_newsflash")

    scheduler._run_source_type("blockbeats_newsflash")

    assert scheduler._is_realtime_blocked("blockbeats_newsflash") is True
    scheduler.reset_realtime_block("blockbeats_newsflash")


def test_blockbeats_persists_provenance_and_reaches_realtime_api(monkeypatch):
    import api.ui_routes as ui
    import collectors.base as base_module
    from collectors.base import BaseCollector

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    class Saver(BaseCollector):
        source = "blockbeats_newsflash"

        def collect(self):
            return []

    monkeypatch.setattr(base_module, "init_db", lambda: None)
    monkeypatch.setattr(base_module, "get_session", factory)
    saver = Saver()
    item = {
        "source": "blockbeats_newsflash",
        "source_id": "blockbeats_newsflash:42",
        "author": "BlockBeats",
        "title": "Crypto policy update",
        "content": "Policy update",
        "url": "https://www.theblockbeats.info/flash/42",
        "upstream_url": "https://agency.example/release",
        "upstream_attribution": "Example Agency",
        "tags": ["crypto-news", "blockbeats"],
        "published_at": datetime.utcnow(),
        "collection_lane": "realtime",
        "source_authority": "secondary",
        "corroboration_state": "unconfirmed",
        "pin_eligibility": "requires_independent_confirmation",
        "review_state": "needs_review",
    }
    assert saver.save([item]) == 1
    assert saver.save([item]) == 0

    session = factory()
    session.add(SourceRegistry(
        source_key="blockbeats_newsflash:main",
        source_type="blockbeats_newsflash",
        display_name="BlockBeats Newsflash",
        config_json=json.dumps({"page_size": 50, "lang": "cn"}),
        is_active=1,
        lane="realtime",
        schedule_seconds=60,
        expected_freshness_hours=0.1,
    ))
    session.commit()
    monkeypatch.setattr(ui, "get_session", lambda: session)

    response = ui.get_realtime_feed(window="24h", limit=20)
    saved = response["items"][0]
    assert saved["source"] == "blockbeats_newsflash"
    assert saved["upstream_url"] == "https://agency.example/release"
    assert saved["upstream_attribution"] == "Example Agency"
    assert saved["review_state"] == "needs_review"
    assert saved["pin_eligibility"] == "requires_independent_confirmation"
    assert response["source_health"][0]["source"] == "blockbeats_newsflash"
    session.close()
