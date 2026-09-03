"""Behavioral tests for the SEC EDGAR realtime News Item vertical slice."""

from datetime import datetime
import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base, CollectorRun, SourceRegistry
from api.time_contract import utc_rfc3339


def _response(payload, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_sec_adapter_resolves_ticker_and_normalizes_approved_filing(monkeypatch):
    from sources.adapters import collect_from_source

    monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "Park Intel park@example.com")
    company_tickers = {
        "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    }
    submissions = {
        "name": "NVIDIA CORP",
        "filings": {
            "recent": {
                "accessionNumber": ["0001045810-26-000123", "0001045810-26-000122"],
                "filingDate": ["2026-09-02", "2026-09-01"],
                "acceptanceDateTime": ["2026-09-02T14:03:11.000Z", "2026-09-01T09:00:00.000Z"],
                "reportDate": ["2026-09-02", "2026-06-30"],
                "form": ["8-K", "4"],
                "primaryDocument": ["nvda-20260902.htm", "xslF345X05/form4.xml"],
                "primaryDocDescription": ["CURRENT REPORT", "FORM 4"],
                "items": ["2.02,9.01", ""],
            }
        },
    }

    with patch(
        "collectors.sec_edgar.requests.get",
        side_effect=[_response(company_tickers), _response(submissions)],
    ) as request:
        rows, result = collect_from_source({
            "source_key": "sec_edgar:watchlist",
            "source_type": "sec_edgar",
            "config": {
                "tickers": ["NVDA"],
                "forms": ["8-K", "10-Q"],
                "cik_map": {"NVDA": 1045810},
            },
        })

    assert result.status == "ok"
    assert len(rows) == 1
    assert rows[0] == {
        "source": "sec_edgar",
        "source_id": "sec_edgar:0001045810-26-000123",
        "author": "NVIDIA CORP",
        "title": "NVDA 8-K — CURRENT REPORT",
        "content": "NVIDIA CORP filed 8-K for 2026-09-02. Items: 2.02,9.01.",
        "url": "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000123/nvda-20260902.htm",
        "tags": ["sec-filing", "8-k"],
        "tickers": ["NVDA"],
        "score": 0,
        "published_at": datetime(2026, 9, 2, 14, 3, 11),
        "collection_lane": "realtime",
        "source_authority": "official",
        "corroboration_state": "primary_source",
            "pin_eligibility": "eligible_if_high_impact",
            "is_backfill": False,
            "backfill_reason": None,
            "_timestamp_status": "valid",
    }
    assert request.call_count == 2
    assert all(
        call.kwargs["headers"]["User-Agent"] == "Park Intel park@example.com"
        for call in request.call_args_list
    )


def test_sec_source_seeds_exact_approved_watchlist_and_forms(monkeypatch):
    from sources.registry import get_source_by_key
    from sources.seed import seed_source_registry

    monkeypatch.setenv("REALTIME_LANE_ENABLED", "1")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_source_registry(session)
        source = get_source_by_key(session, "sec_edgar:watchlist")

    assert source is not None
    assert source.source_type == "sec_edgar"
    assert source.lane == "realtime"
    assert source.schedule_seconds == 60
    assert source.expected_freshness_hours == pytest.approx(0.1)
    config = json.loads(source.config_json)
    assert config["tickers"] == [
        "NVDA", "MSFT", "AAPL", "AMZN", "GOOGL", "META", "TSLA",
        "AVGO", "AMD", "MU", "SNDK", "TSM", "ASML", "ORCL", "PLTR",
        "JPM", "COIN", "MSTR", "XOM", "NEM",
    ]
    assert config["forms"] == ["8-K", "10-Q", "10-K", "6-K", "20-F"]
    assert config["lookback_hours"] == 72
    assert set(config["cik_map"]) == set(config["tickers"])
    assert config["cik_map"]["SNDK"] == 2023554


def test_sec_news_item_persists_authority_separately_and_reaches_realtime_api(monkeypatch):
    import api.ui_routes as ui
    import collectors.base as base_module
    from collectors.base import BaseCollector

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    class Saver(BaseCollector):
        source = "sec_edgar"

        def collect(self):
            return []

    monkeypatch.setattr(base_module, "init_db", lambda: None)
    monkeypatch.setattr(base_module, "get_session", factory)
    saver = Saver()
    news_item = {
        "source": "sec_edgar",
        "source_id": "sec_edgar:0001045810-26-000123",
        "author": "NVIDIA CORP",
        "title": "NVDA 8-K — CURRENT REPORT",
        "content": "NVIDIA CORP filed 8-K.",
        "url": "https://www.sec.gov/Archives/example",
        "tags": ["sec-filing", "8-k"],
        "tickers": ["NVDA"],
        "published_at": datetime(2026, 9, 2, 14, 3, 11),
        "collection_lane": "realtime",
        "source_authority": "official",
        "corroboration_state": "primary_source",
        "pin_eligibility": "eligible_if_high_impact",
    }
    assert saver.save([news_item]) == 1
    assert saver.save([news_item]) == 0
    assert saver.last_save_stats["duplicates"] == 1

    session = factory()
    session.add(SourceRegistry(
        source_key="sec_edgar:watchlist",
        source_type="sec_edgar",
        display_name="SEC EDGAR Watchlist",
        config_json="{}",
        is_active=1,
        lane="realtime",
        schedule_seconds=60,
    ))
    article = session.query(base_module.Article).one()
    article.triage_status = "complete"
    article.triage_bucket = "watch"
    session.commit()
    monkeypatch.setattr(ui, "get_session", lambda: session)

    response = ui.get_realtime_feed(window="all", limit=20)

    item = response["items"][0]
    assert item["source_authority"] == "official"
    assert item["corroboration_state"] == "primary_source"
    assert item["pin_eligibility"] == "eligible_if_high_impact"
    assert item["triage"]["bucket"] == "watch"
    assert response["source_health"][0]["source"] == "sec_edgar"
    session.close()


def test_sec_missing_user_agent_is_visible_configuration_failure(monkeypatch):
    from sources.adapters import collect_from_source

    monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)
    rows, result = collect_from_source({
        "source_key": "sec_edgar:watchlist",
        "source_type": "sec_edgar",
        "config": {
            "tickers": ["NVDA"],
            "forms": ["8-K"],
            "cik_map": {"NVDA": 1045810},
        },
    })

    assert rows == []
    assert result.status == "error"
    assert result.error_category == "config"
    assert "SEC_EDGAR_USER_AGENT" in result.error_message


def test_sec_rejects_ambiguous_official_ticker_mapping(monkeypatch):
    from sources.adapters import collect_from_source

    monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "Park Intel park@example.com")
    ambiguous = {
        "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
        "1": {"cik_str": 9999999, "ticker": "NVDA", "title": "OTHER NVIDIA"},
    }
    with patch(
        "collectors.sec_edgar.requests.get",
        return_value=_response(ambiguous),
    ):
        rows, result = collect_from_source({
            "source_key": "sec_edgar:watchlist",
            "source_type": "sec_edgar",
            "config": {
                "tickers": ["NVDA"],
                "forms": ["8-K"],
                "cik_map": {"NVDA": 1045810},
            },
        })

    assert rows == []
    assert result.status == "error"
    assert result.error_category == "config"
    assert "ambiguous" in result.error_message.lower()


def test_sec_requests_respect_bounded_fair_access_gap(monkeypatch):
    from collectors.sec_edgar import fetch_sec_edgar_filings

    monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "Park Intel park@example.com")
    monkeypatch.setattr("collectors.sec_edgar._LAST_REQUEST_AT", None)
    company_tickers = {
        "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    }
    submissions = {
        "name": "NVIDIA CORP",
        "filings": {"recent": {"accessionNumber": []}},
    }
    with patch(
        "collectors.sec_edgar.requests.get",
        side_effect=[_response(company_tickers), _response(submissions)],
    ), patch(
        "collectors.sec_edgar.time.monotonic",
        side_effect=[10.0, 10.01, 10.12],
    ), patch("collectors.sec_edgar.time.sleep") as sleep:
        assert fetch_sec_edgar_filings(
            tickers=["NVDA"],
            forms=["8-K"],
            cik_map={"NVDA": 1045810},
        ) == []

    assert sleep.call_count == 1
    assert sleep.call_args.args[0] >= 0.09


def test_sec_adapter_rejects_verified_cik_pin_drift(monkeypatch):
    from sources.adapters import collect_from_source

    monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "Park Intel park@example.com")
    company_tickers = {
        "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    }
    with patch(
        "collectors.sec_edgar.requests.get",
        return_value=_response(company_tickers),
    ):
        rows, result = collect_from_source({
            "source_key": "sec_edgar:watchlist",
            "source_type": "sec_edgar",
            "config": {
                "tickers": ["NVDA"],
                "forms": ["8-K"],
                "cik_map": {"NVDA": 9999999},
            },
        })

    assert rows == []
    assert result.error_category == "config"
    assert "CIK pin mismatch" in result.error_message


def test_sec_adapter_rejects_missing_cik_pin_contract(monkeypatch):
    from sources.adapters import collect_from_source

    monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "Park Intel park@example.com")
    company_tickers = {
        "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    }
    with patch(
        "collectors.sec_edgar.requests.get",
        return_value=_response(company_tickers),
    ):
        rows, result = collect_from_source({
            "source_key": "sec_edgar:watchlist",
            "source_type": "sec_edgar",
            "config": {"tickers": ["NVDA"], "forms": ["8-K"]},
        })

    assert rows == []
    assert result.error_category == "config"
    assert "CIK pin contract is required" in result.error_message


def test_sec_ui_health_uses_successful_poll_when_filings_are_duplicates(monkeypatch):
    import api.ui_routes as ui
    import scheduler

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(SourceRegistry(
        source_key="sec_edgar:watchlist",
        source_type="sec_edgar",
        display_name="SEC EDGAR Watchlist",
        config_json="{}",
        is_active=1,
        lane="realtime",
        schedule_seconds=60,
    ))
    session.commit()
    run = scheduler.CollectorResult(
        source="sec_edgar",
        articles_fetched=12,
        articles_saved=0,
        duration_seconds=1.2,
        error=None,
        timestamp=datetime.utcnow().isoformat(),
    )
    monkeypatch.setattr(scheduler, "get_last_results", lambda: {"sec_edgar": run})
    monkeypatch.setattr(ui, "get_session", lambda: session)

    response = ui.get_realtime_feed(window="24h", limit=20)

    assert response["source_health"] == [{
        "source": "sec_edgar",
        "count": 0,
        "last_seen_at": None,
        "last_attempt_at": utc_rfc3339(run.timestamp),
        "status": "ok",
    }]
    session.close()


def test_sec_ui_health_falls_back_to_persisted_provider_failure(monkeypatch):
    import api.ui_routes as ui
    import scheduler

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    attempted_at = datetime(2026, 9, 2, 4, 33, 5)
    session.add(SourceRegistry(
        source_key="sec_edgar:watchlist",
        source_type="sec_edgar",
        display_name="SEC EDGAR Watchlist",
        config_json="{}",
        is_active=1,
        lane="realtime",
        schedule_seconds=60,
    ))
    session.add(CollectorRun(
        source_type="sec_edgar",
        source_key="sec_edgar:watchlist",
        status="error",
        articles_fetched=0,
        articles_saved=0,
        duration_ms=500,
        error_message="sec_edgar provider blocked HTTP 403",
        error_category="auth",
        retry_count=0,
        completed_at=attempted_at,
    ))
    session.commit()
    monkeypatch.setattr(scheduler, "get_last_results", lambda: {})
    monkeypatch.setattr(ui, "get_session", lambda: session)

    response = ui.get_realtime_feed(window="24h", limit=20)

    assert response["source_health"] == [{
        "source": "sec_edgar",
        "count": 0,
        "last_seen_at": None,
        "last_attempt_at": utc_rfc3339(attempted_at),
        "status": "degraded",
    }]
    session.close()
