"""Behavioral tests for reversible SEC realtime backfill handling."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from db.models import Article, Base, SourceRegistry


def _response(payload):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_sec_collector_marks_only_parsed_filings_outside_72h_as_backfill(monkeypatch):
    from collectors.sec_edgar import fetch_sec_edgar_filings

    monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "ParkIntel <ops@example.com>")
    now = datetime(2026, 9, 2, 12, 0, 0)
    company_tickers = {
        "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    }
    submissions = {
        "name": "NVIDIA CORP",
        "filings": {"recent": {
            "accessionNumber": ["old-accession", "recent-accession", "missing-time"],
            "filingDate": ["2026-08-20", "2026-09-02", ""],
            "acceptanceDateTime": [
                "2026-08-20T12:00:00.000Z",
                "2026-09-02T11:00:00.000Z",
                "",
            ],
            "reportDate": ["2026-08-20", "2026-09-02", ""],
            "form": ["8-K", "8-K", "8-K"],
            "primaryDocument": ["old.htm", "recent.htm", "missing.htm"],
            "primaryDocDescription": ["8-K", "8-K", "8-K"],
            "items": ["", "", ""],
        }},
    }
    with patch(
        "collectors.sec_edgar.requests.get",
        side_effect=[_response(company_tickers), _response(submissions)],
    ):
        rows = fetch_sec_edgar_filings(
            tickers=["NVDA"],
            forms=["8-K"],
            cik_map={"NVDA": 1045810},
            lookback_hours=72,
            now=now,
        )

    by_id = {row["source_id"]: row for row in rows}
    assert by_id["sec_edgar:old-accession"]["is_backfill"] is True
    assert by_id["sec_edgar:old-accession"]["backfill_reason"] == (
        "outside_realtime_lookback_72h"
    )
    assert by_id["sec_edgar:recent-accession"]["is_backfill"] is False
    assert by_id["sec_edgar:recent-accession"]["backfill_reason"] is None
    assert by_id["sec_edgar:missing-time"]["is_backfill"] is False


def test_realtime_triage_excludes_backfill_candidates(monkeypatch):
    from scheduler import _run_realtime_triage

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add_all([
        Article(
            source="sec_edgar",
            source_id="sec:backfill",
            title="Historical 8-K",
            content="Historical filing",
            collection_lane="realtime",
            is_backfill=True,
            backfill_reason="test-history",
            collected_at=datetime(2026, 9, 2, 12, 0),
        ),
        Article(
            source="sec_edgar",
            source_id="sec:current",
            title="Current 8-K",
            content="Current filing",
            collection_lane="realtime",
            is_backfill=False,
            exposure_status="matched",
            exposure_assets='["sp500"]',
            exposure_reason="test_fixture",
            collected_at=datetime(2026, 9, 2, 12, 1),
        ),
    ])
    session.commit()

    class FakeTriage:
        model_name = "test-model"

        def __init__(self, **_kwargs):
            pass

        def triage_batch(self, articles):
            assert [article["title"] for article in articles] == ["Current 8-K"]
            return [{
                "id": articles[0]["id"],
                "bucket": "watch",
                "direction": "unclear",
                "rationale": "Current filing",
                "affected_assets": [],
                "watch_for": [],
                "scenario_bull": "",
                "scenario_bear": "",
            }]

    monkeypatch.setattr("db.database.get_session", lambda: session)
    monkeypatch.setattr("scheduler._realtime_lane_enabled", lambda: True)
    monkeypatch.setattr("triage.realtime.RealtimeTriage", FakeTriage)

    _run_realtime_triage()

    session.expire_all()
    backfill = session.query(Article).filter_by(source_id="sec:backfill").one()
    current = session.query(Article).filter_by(source_id="sec:current").one()
    assert backfill.triage_status is None
    assert current.triage_status == "complete"
    session.close()


def test_realtime_ui_hides_backfill_by_default_and_can_include_it(monkeypatch):
    import api.ui_routes as ui

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(SourceRegistry(
        source_key="sec_edgar:watchlist",
        source_type="sec_edgar",
        display_name="SEC",
        config_json="{}",
        is_active=1,
        lane="realtime",
        schedule_seconds=60,
    ))
    for source_id, title, is_backfill in (
        ("sec:old", "Historical filing", True),
        ("sec:new", "Current filing", False),
    ):
        session.add(Article(
            source="sec_edgar",
            source_id=source_id,
            title=title,
            content=title,
            collection_lane="realtime",
            is_backfill=is_backfill,
            exposure_status="unmatched" if is_backfill else "matched",
            exposure_assets="[]" if is_backfill else '["sp500"]',
            exposure_reason="no_approved_exposure" if is_backfill else "test_fixture",
            backfill_reason="test-history" if is_backfill else None,
            collected_at=datetime.utcnow(),
        ))
    session.commit()
    monkeypatch.setattr(ui, "get_session", lambda: session)

    default_response = ui.get_realtime_feed(window="24h", limit=20)
    research_response = ui.get_realtime_feed(
        window="24h",
        limit=20,
        include_backfill=True,
    )

    assert [item["title"] for item in default_response["items"]] == ["Current filing"]
    assert {item["title"] for item in research_response["items"]} == {
        "Current filing",
        "Historical filing",
    }
    historical = next(
        item for item in research_response["items"]
        if item["title"] == "Historical filing"
    )
    assert historical["is_backfill"] is True
    assert historical["backfill_reason"] == "test-history"
    session.close()


def test_backfill_marker_is_dry_run_first_and_reversible():
    from scripts.mark_sec_backfill import mark_sec_backfill, undo_sec_backfill

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime(2026, 9, 2, 12, 0)
    session.add_all([
        Article(
            source="sec_edgar",
            source_id="sec:old",
            title="Old",
            collection_lane="realtime",
            published_at=now - timedelta(days=10),
            collected_at=now,
        ),
        Article(
            source="sec_edgar",
            source_id="sec:new",
            title="New",
            collection_lane="realtime",
            published_at=now - timedelta(hours=1),
            collected_at=now,
        ),
        Article(
            source="sec_edgar",
            source_id="sec:missing",
            title="Missing",
            collection_lane="realtime",
            published_at=None,
            collected_at=now,
        ),
    ])
    session.commit()
    reason = "sec_initial_history_before_2026-08-30T12:00:00"
    cutoff = now - timedelta(hours=72)

    assert mark_sec_backfill(session, cutoff=cutoff, reason=reason, apply=False) == 1
    assert session.query(Article).filter(Article.is_backfill.is_(True)).count() == 0
    assert mark_sec_backfill(session, cutoff=cutoff, reason=reason, apply=True) == 1
    marked = session.query(Article).filter_by(source_id="sec:old").one()
    assert marked.is_backfill is True
    assert marked.backfill_reason == reason
    assert session.query(Article).count() == 3

    assert undo_sec_backfill(session, reason=reason, apply=True) == 1
    assert session.query(Article).filter(Article.is_backfill.is_(True)).count() == 0
    assert session.query(Article).count() == 3
    session.close()


def test_existing_article_table_migrates_backfill_to_false():
    from db.migrations import run_migrations

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE articles ("
            "id INTEGER PRIMARY KEY, source TEXT NOT NULL, title TEXT, "
            "collected_at DATETIME)"
        ))
        connection.execute(text(
            "INSERT INTO articles (id, source, title, collected_at) "
            "VALUES (1, 'sec_edgar', 'Legacy filing', '2026-09-02 12:00:00')"
        ))

    run_migrations(engine)

    columns = {column["name"]: column for column in inspect(engine).get_columns("articles")}
    assert "is_backfill" in columns
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT is_backfill, backfill_reason FROM articles WHERE id = 1"
        )).one()
    assert row[0] == 0
    assert row[1] is None
