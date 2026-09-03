"""Regression coverage for scheduled realtime news that must remain visible."""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import Article, Base


def _scheduled_result(article_id: int) -> dict:
    return {
        "id": article_id,
        "bucket": "high_impact",
        "direction": "unclear",
        "rationale": "The scheduled release can reprice rates and risk assets.",
        "affected_assets": [{
            "symbol": "QQQ",
            "name": "Nasdaq 100 ETF",
            "impact": "unclear",
        }],
        "watch_for": ["the official release and the market reaction"],
    }


@pytest.mark.parametrize("title", [
    "美国8月非农明晚来袭！美银：仅是开胃菜",
    "三因素有望推动8月份CPI同比温和上涨",
    "OPEC+据悉可能维持下月原油产量配额不变",
    "日本央行决议前交易员高度警惕干预风险",
    "8月份新增信贷、社融或同比少增",
])
def test_chinese_scheduled_preview_is_accepted_without_repair_call(title):
    from triage.realtime import RealtimeTriage

    client = MagicMock()
    client.complete.return_value = json.dumps({"results": [
        _scheduled_result(1),
    ]})

    result = RealtimeTriage(client=client).triage_batch([{
        "id": 1,
        "title": title,
        "content": "市场正在等待就业数据，结果尚未发布。",
        "source": "eastmoney_global_news",
    }])

    assert result[0]["bucket"] == "high_impact"
    assert result[0]["direction"] == "unclear"
    assert client.complete.call_count == 1


def test_unclear_high_impact_without_scheduled_evidence_isolated_without_repair():
    from triage.realtime import RealtimeTriage

    client = MagicMock()
    client.complete.return_value = json.dumps({"results": [
        _scheduled_result(2),
    ]})

    result = RealtimeTriage(client=client).triage_batch([{
        "id": 2,
        "title": "某公司市场动态",
        "content": "这是一条没有明确时间或未来事件的简讯。",
        "source": "eastmoney_global_news",
    }])

    assert result[0]["bucket"] == "unknown"
    assert result[0]["retryable"] is False
    assert result[0]["failure_kind"] == "deterministic_validation"
    assert client.complete.call_count == 1


def test_deterministic_validation_fallback_is_persisted_as_visible_complete_unknown():
    import api.ui_routes as ui
    import scheduler

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(Article(
        source="eastmoney_global_news",
        source_id="scheduled-preview-1",
            title="美国8月非农明晚来袭",
            content="等待非农数据。",
            collection_lane="realtime",
            exposure_status="matched",
            exposure_assets='["sp500"]',
            exposure_reason="macro:us_macro",
            collected_at=datetime(2026, 9, 3, 3, 0, 0),
        triage_attempts=0,
    ))
    session.commit()

    class FakeTriage:
        model_name = "test-model"

        def __init__(self, **_kwargs):
            pass

        def triage_batch(self, _articles):
            return [{
                "id": session.query(Article).one().id,
                "bucket": "unknown",
                "direction": "unclear",
                "rationale": "The contract could not verify the event state.",
                "affected_assets": [],
                "watch_for": ["manual review"],
                "validation_error": "high_impact direction must be bullish or bearish",
                "failure_kind": "deterministic_validation",
                "retryable": False,
            }]

    with patch("db.database.get_session", return_value=session), \
         patch.object(scheduler, "_realtime_lane_enabled", return_value=True), \
         patch("triage.realtime.RealtimeTriage", FakeTriage):
        scheduler._run_realtime_triage()

    saved = session.query(Article).one()
    assert saved.triage_bucket == "unknown"
    assert saved.triage_status == "complete"
    assert saved.triage_attempts == 1
    assert saved.triage_error == "high_impact direction must be bullish or bearish"
    with patch.object(ui, "get_session", return_value=session), \
         patch("scheduler.get_last_results", return_value={}):
        response = ui.get_realtime_feed(window="24h", limit=20)

    assert response["items"][0]["triage"]["bucket"] == "unknown"
    assert response["operational"]["unknown"]["count"] == 1
    assert response["operational"]["failed"] == 0
    assert response["stats"]["operational_events_hidden"] == 1
    session.close()
