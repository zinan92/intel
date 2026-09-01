"""Behavioral tests for realtime AI triage and the realtime read model."""

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from db.models import Article, Base, SourceRegistry


def test_triage_batch_normalizes_ai_contract():
    from triage.realtime import RealtimeTriage

    client = MagicMock()
    client.complete.return_value = json.dumps({
        "results": [{
            "id": 7,
            "bucket": "high_impact",
            "direction": "bearish",
            "rationale": "A policy surprise changes the rate path.",
            "affected_assets": [
                {"symbol": "GC=F", "name": "Gold", "impact": "down"},
            ],
            "watch_for": ["real yields", "dollar index"],
            "scenario_bull": "If the market fades the surprise, gold stabilizes.",
            "scenario_bear": "If yields persist higher, gold and beta risk sell off.",
        }]
    })

    result = RealtimeTriage(client=client).triage_batch([{
        "id": 7,
        "title": "Unexpected policy signal",
        "content": "The central bank changes its guidance.",
        "source": "cls_telegraph",
    }])

    assert result == [{
        "id": 7,
        "bucket": "high_impact",
        "direction": "bearish",
        "rationale": "A policy surprise changes the rate path.",
        "affected_assets": [
            {"symbol": "GC=F", "name": "Gold", "impact": "down"},
        ],
        "watch_for": ["real yields", "dollar index"],
        "scenario_bull": "If the market fades the surprise, gold stabilizes.",
        "scenario_bear": "If yields persist higher, gold and beta risk sell off.",
    }]
    prompt = client.complete.call_args.args[0]
    assert "Unexpected policy signal" in prompt


def test_fomc_floor_is_high_impact_even_when_direction_is_unclear():
    from triage.realtime import RealtimeTriage

    client = MagicMock()
    client.complete.return_value = json.dumps({
        "results": [{
            "id": 8,
            "bucket": "watch",
            "direction": "unclear",
            "rationale": "The direction is not yet clear.",
            "affected_assets": [],
            "watch_for": ["Powell's guidance"],
            "scenario_bull": "Risk appetite holds.",
            "scenario_bear": "Rates reprice.",
        }]
    })

    result = RealtimeTriage(client=client).triage_batch([{
        "id": 8,
        "title": "FOMC decision is released",
        "content": "The Federal Open Market Committee publishes its statement.",
        "source": "eastmoney_global_news",
    }])

    assert result[0]["bucket"] == "high_impact"
    assert result[0]["direction"] == "unclear"


def test_triage_rejects_invalid_ai_bucket():
    from triage.realtime import RealtimeTriage

    client = MagicMock()
    client.complete.return_value = json.dumps({
        "results": [{"id": 9, "bucket": "maybe", "direction": "unclear"}]
    })

    with pytest.raises(ValueError, match="bucket"):
        RealtimeTriage(client=client).triage_batch([{
            "id": 9,
            "title": "Unclear item",
            "content": "Content",
            "source": "cls_telegraph",
        }])


def test_article_has_persisted_triage_columns():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("articles")}

    assert {
        "triage_bucket",
        "triage_status",
        "triage_direction",
        "triage_rationale",
        "triage_assets",
        "triage_watch_for",
        "triage_scenario_bull",
        "triage_scenario_bear",
        "triage_model",
        "triage_error",
        "triage_attempts",
        "triaged_at",
    }.issubset(columns)


def test_scheduler_registers_triage_job_only_with_realtime_lane():
    from scheduler import CollectorScheduler

    fake_session = MagicMock()
    fake_sources = [SimpleNamespace(
        source_type="cls_telegraph",
        schedule_hours=None,
        lane="realtime",
        schedule_seconds=60,
    )]

    with patch.dict("os.environ", {"REALTIME_LANE_ENABLED": "1"}), \
         patch("db.database.get_session", return_value=fake_session), \
         patch("sources.registry.list_active_sources", return_value=fake_sources):
        scheduler = CollectorScheduler()
        scheduler._register_jobs()

    jobs = {job.id: job for job in scheduler._scheduler.get_jobs()}
    assert "realtime-triage" in jobs
    assert jobs["realtime-triage"].trigger.interval.total_seconds() == 30


def test_triage_scheduler_persists_a_real_result_shape():
    from scheduler import _run_realtime_triage

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    article = Article(
        source="cls_telegraph",
        source_id="cls_telegraph:triage-test",
        title="FOMC statement",
        content="The FOMC statement is released.",
        collection_lane="realtime",
        published_at=datetime(2026, 9, 1, 8, 0, 0),
        collected_at=datetime(2026, 9, 1, 8, 0, 5),
    )
    session.add(article)
    session.commit()
    article_id = article.id

    class FakeTriage:
        model_name = "test-model"

        def __init__(self, **_kwargs):
            pass

        def triage_batch(self, articles):
            return [{
                "id": articles[0]["id"],
                "bucket": "high_impact",
                "direction": "unclear",
                "rationale": "FOMC is a macro event.",
                "affected_assets": [{"symbol": "GC=F", "name": "Gold", "impact": "mixed"}],
                "watch_for": ["real yields"],
                "scenario_bull": "Cuts are priced in.",
                "scenario_bear": "Yields rise.",
            }]

    with patch("db.database.get_session", return_value=session), \
         patch("scheduler._realtime_lane_enabled", return_value=True), \
         patch("triage.realtime.RealtimeTriage", FakeTriage):
        _run_realtime_triage()

    session.expire_all()
    saved = session.query(Article).filter_by(id=article_id).one()
    assert saved.triage_status == "complete"
    assert saved.triage_bucket == "high_impact"
    assert json.loads(saved.triage_assets)[0]["symbol"] == "GC=F"
    assert saved.triage_model == "test-model"
    session.close()


def test_realtime_endpoint_exposes_real_buckets(monkeypatch):
    import api.ui_routes as ui

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(SourceRegistry(
        source_key="cls_telegraph:main",
        source_type="cls_telegraph",
        display_name="CLS",
        config_json="{}",
        is_active=1,
        lane="realtime",
        schedule_seconds=60,
    ))
    session.add(Article(
        source="cls_telegraph",
        source_id="cls_telegraph:endpoint",
        title="FOMC decision",
        content="Macro event",
        collection_lane="realtime",
        triage_status="complete",
        triage_bucket="high_impact",
        triage_direction="unclear",
        triage_rationale="Large macro event.",
        triage_assets=json.dumps([{"symbol": "GC=F", "name": "Gold", "impact": "mixed"}]),
        triage_watch_for=json.dumps(["real yields"]),
        triage_scenario_bull="Gold holds.",
        triage_scenario_bear="Gold sells off.",
        published_at=datetime.utcnow(),
        collected_at=datetime.utcnow(),
    ))
    session.commit()
    monkeypatch.setattr(ui, "get_session", lambda: session)

    response = ui.get_realtime_feed(window="24h", limit=20)

    assert response["stats"]["triaged"] == 1
    assert response["buckets"]["high_impact"][0]["triage"]["affected_assets"][0]["symbol"] == "GC=F"
    assert response["items"][0]["collection_lane"] == "realtime"
