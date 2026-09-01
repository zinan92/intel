"""Behavioral tests for the CLS real-time News Item vertical slice."""

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from db.models import Article, Base, SourceRegistry


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db_session = factory()
    yield db_session
    db_session.close()


def _response(payload, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_cls_payload_becomes_realtime_news_item():
    from collectors.realtime_news import fetch_cls_telegraph

    payload = {
        "data": {
            "roll_data": [
                {
                    "id": 2470866,
                    "ctime": 1788252370,
                    "title": "",
                    "brief": "英国国债延续跌势，10年期收益率涨11个基点至5.25%。",
                    "content": "财联社9月1日电，英国国债延续跌势，10年期收益率涨11个基点至5.25%。",
                    "shareurl": "https://api3.cls.cn/share/article/2470866",
                    "author": "",
                    "is_ad": 0,
                }
            ]
        }
    }

    with patch("collectors.realtime_news.requests.get", return_value=_response(payload)) as request:
        rows = fetch_cls_telegraph(page_size=5)

    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "cls_telegraph"
    assert row["source_id"] == "cls_telegraph:2470866"
    assert row["collection_lane"] == "realtime"
    assert row["title"] == "英国国债延续跌势，10年期收益率涨11个基点至5.25%。"
    assert row["url"].startswith("https://api3.cls.cn/share/article/2470866")
    assert row["published_at"] == datetime(2026, 9, 1, 8, 46, 10)
    request.assert_called_once()


def test_cls_ads_are_not_saved_as_news_items():
    from collectors.realtime_news import fetch_cls_telegraph

    payload = {"data": {"roll_data": [{"id": 1, "ctime": 1788252370, "brief": "ad", "is_ad": 1}]}}
    with patch("collectors.realtime_news.requests.get", return_value=_response(payload)):
        assert fetch_cls_telegraph() == []


def test_cls_source_is_seeded_as_realtime_source(session: Session):
    from sources.registry import get_source_by_key
    from sources.seed import seed_source_registry

    seed_source_registry(session)

    source = get_source_by_key(session, "cls_telegraph:main")
    assert source is not None
    assert source.source_type == "cls_telegraph"
    assert source.lane == "realtime"
    assert source.schedule_seconds == 60
    assert source.schedule_hours is None
    assert source.expected_freshness_hours == pytest.approx(0.1)


def test_scheduler_registers_cls_realtime_job_without_hourly_job():
    from scheduler import CollectorScheduler

    fake_session = MagicMock()
    fake_sources = [
        SimpleNamespace(source_type="rss", schedule_hours=1, lane="hourly", schedule_seconds=None),
        SimpleNamespace(source_type="cls_telegraph", schedule_hours=None, lane="realtime", schedule_seconds=60),
    ]

    with patch("db.database.get_session", return_value=fake_session), \
         patch("sources.registry.list_active_sources", return_value=fake_sources):
        scheduler = CollectorScheduler()
        scheduler._register_jobs()

    jobs = {job.id: job for job in scheduler._scheduler.get_jobs()}
    assert "collector-rss" in jobs
    assert "realtime-cls_telegraph" in jobs
    assert jobs["realtime-cls_telegraph"].trigger.interval.total_seconds() == 60


def test_article_and_source_registry_expose_lane_columns(session: Session):
    columns = {column["name"] for column in inspect(session.bind).get_columns("articles")}
    source_columns = {column["name"] for column in inspect(session.bind).get_columns("source_registry")}
    assert "collection_lane" in columns
    assert {"lane", "schedule_seconds"}.issubset(source_columns)


def test_realtime_item_is_readable_through_existing_article_shape(session: Session):
    article = Article(
        source="cls_telegraph",
        source_id="cls_telegraph:2470866",
        title="英国国债延续跌势",
        content="10年期收益率涨11个基点至5.25%。",
        url="https://api3.cls.cn/share/article/2470866",
        collection_lane="realtime",
        published_at=datetime(2026, 9, 1, 8, 46, 10),
        collected_at=datetime(2026, 9, 1, 8, 47, 0),
    )
    session.add(article)
    session.commit()

    saved = session.query(Article).filter_by(source_id="cls_telegraph:2470866").one()
    assert saved.collection_lane == "realtime"
    assert saved.published_at == datetime(2026, 9, 1, 8, 46, 10)
