"""Behavioral tests for the Eastmoney 7x24 realtime News Item slice."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


def _response(payload):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


def test_eastmoney_payload_becomes_realtime_news_item():
    from collectors.realtime_news import fetch_eastmoney_global_news

    payload = {
        "data": {
            "fastNewsList": [
                {
                    "code": "202609013861523839",
                    "showTime": "2026-09-01 16:41:36",
                    "title": "石药创新：SYS6010纳入突破性治疗品种名单",
                    "summary": "公司控股子公司 SYS6010 被纳入突破性治疗品种名单。",
                    "stockList": ["0.300765", "1.600000"],
                }
            ]
        }
    }

    with patch(
        "collectors.realtime_news.requests.get",
        return_value=_response(payload),
    ) as request:
        rows = fetch_eastmoney_global_news(page_size=5)

    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "eastmoney_global_news"
    assert row["source_id"] == "eastmoney_global_news:202609013861523839"
    assert row["collection_lane"] == "realtime"
    assert row["title"] == "石药创新：SYS6010纳入突破性治疗品种名单"
    assert row["content"] == "公司控股子公司 SYS6010 被纳入突破性治疗品种名单。"
    assert row["tickers"] == ["300765.SZ", "600000.SH"]
    assert row["published_at"] == datetime(2026, 9, 1, 8, 41, 36)
    assert row["url"] is None
    request.assert_called_once()
    assert request.call_args.kwargs["params"]["fastColumn"] == 102


def test_eastmoney_malformed_rows_are_skipped():
    from collectors.realtime_news import fetch_eastmoney_global_news

    payload = {
        "data": {
            "fastNewsList": [
                {"code": "", "title": "missing id"},
                {"code": "2", "title": ""},
            ]
        }
    }
    with patch(
        "collectors.realtime_news.requests.get",
        return_value=_response(payload),
    ):
        rows = fetch_eastmoney_global_news()

    assert len(rows) == 1
    assert rows[0]["source_id"].startswith("eastmoney_global_news:sha256:")


def test_eastmoney_source_is_seeded_as_realtime_source():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from db.models import Base
    from sources.registry import get_source_by_key
    from sources.seed import seed_source_registry

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_source_registry(session)
        source = get_source_by_key(session, "eastmoney_global_news:main")

        assert source is not None
        assert source.source_type == "eastmoney_global_news"
        assert source.lane == "realtime"
        assert source.schedule_seconds == 60
        assert source.schedule_hours is None
        assert source.expected_freshness_hours == pytest.approx(0.1)
