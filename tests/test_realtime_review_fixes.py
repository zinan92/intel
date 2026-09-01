"""Regression tests for the post-review realtime lane fixes."""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Article, Base, CollectorRun, SourceRegistry


def test_realtime_seed_is_inactive_without_explicit_opt_in(monkeypatch):
    from sources.registry import get_source_by_key
    from sources.seed import seed_source_registry

    monkeypatch.delenv("REALTIME_LANE_ENABLED", raising=False)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_source_registry(session)
        cls = get_source_by_key(session, "cls_telegraph:main")
        eastmoney = get_source_by_key(session, "eastmoney_global_news:main")

        assert cls is not None and cls.is_active == 0
        assert eastmoney is not None and eastmoney.is_active == 0

        monkeypatch.setenv("REALTIME_LANE_ENABLED", "1")
        seed_source_registry(session)
        assert get_source_by_key(session, "cls_telegraph:main").is_active == 1
        assert get_source_by_key(session, "eastmoney_global_news:main").is_active == 1


def test_scheduler_does_not_register_realtime_job_when_opt_in_is_off(monkeypatch):
    from scheduler import CollectorScheduler

    monkeypatch.delenv("REALTIME_LANE_ENABLED", raising=False)
    fake_session = MagicMock()
    fake_sources = [
        type("Source", (), {
            "source_type": "cls_telegraph",
            "schedule_hours": None,
            "lane": "realtime",
            "schedule_seconds": 60,
        })(),
    ]
    with patch("db.database.get_session", return_value=fake_session), \
         patch("sources.registry.list_active_sources", return_value=fake_sources):
        scheduler = CollectorScheduler()
        scheduler._register_jobs()

    assert "realtime-cls_telegraph" not in {
        job.id for job in scheduler._scheduler.get_jobs()
    }


def test_empty_success_has_no_freshness_and_is_not_healthy():
    from dual_run.receipt import build_dual_run_receipt

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    end = datetime(2026, 9, 1, 9, 0, 0)
    with Session(engine) as session:
        session.add(SourceRegistry(
            source_key="cls_telegraph:main",
            source_type="cls_telegraph",
            display_name="CLS",
            config_json="{}",
            is_active=1,
            lane="realtime",
            schedule_seconds=60,
            expected_freshness_hours=0.1,
        ))
        session.add(CollectorRun(
            source_type="cls_telegraph",
            source_key="cls_telegraph:main",
            status="ok",
            articles_fetched=0,
            articles_saved=0,
            completed_at=end - timedelta(seconds=5),
        ))
        session.commit()

        receipt = build_dual_run_receipt(
            session,
            window_start=end - timedelta(hours=1),
            window_end=end,
        )

    lane = receipt["lanes"]["realtime"]
    assert lane["evidence_status"] == "empty_success"
    assert lane["freshness_age_seconds"] is None
    source = receipt["source_health"][0]
    assert source["status"] == "stale"
    assert source["evidence_status"] == "empty_success"


def test_save_stats_separate_duplicates_from_save_errors():
    from collectors.base import BaseCollector

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    seed_session = factory()
    seed_session.add(Article(
        source="cls_telegraph",
        source_id="cls_telegraph:duplicate",
        title="Existing",
        content="Existing",
        collection_lane="realtime",
    ))
    seed_session.commit()
    seed_session.close()

    class TestCollector(BaseCollector):
        source = "cls_telegraph"

        def collect(self):
            return []

    with patch("collectors.base.init_db"), patch(
        "collectors.base.get_session", side_effect=factory
    ):
        collector = TestCollector()
        saved = collector.save([
            {
                "source_id": "cls_telegraph:duplicate",
                "title": "Existing",
                "content": "Existing",
                "collection_lane": "realtime",
            },
            {
                "source_id": "cls_telegraph:bad",
                "title": "Bad",
                "content": "Bad",
                "tags": object(),
                "collection_lane": "realtime",
            },
        ])

    assert saved == 0
    assert collector.last_save_stats == {"saved": 0, "duplicates": 1, "errors": 1}


def test_realtime_event_aggregation_is_contained():
    from events.aggregator import run_aggregation
    from events.models import Event

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Article(
            source="cls_telegraph",
            source_id="cls_telegraph:event",
            title="Realtime event candidate",
            narrative_tags=json.dumps(["realtime-event"]),
            relevance_score=5,
            published_at=datetime.utcnow() - timedelta(hours=1),
            collected_at=datetime.utcnow() - timedelta(hours=1),
            collection_lane="realtime",
        ))
        session.commit()
        run_aggregation(session)
        assert session.query(Event).count() == 0


def test_unknown_eastmoney_market_code_is_not_emitted():
    from collectors.realtime_news import _eastmoney_ticker

    assert _eastmoney_ticker("116.00700") is None
    assert _eastmoney_ticker("0.300765") == "300765.SZ"


def test_provider_block_is_not_retryable():
    from sources.errors import SourceBlockedError, categorize_error, is_retryable

    error = SourceBlockedError("provider blocked HTTP 429")
    assert categorize_error(error).value == "auth"
    assert is_retryable(error) is False


def test_cls_and_eastmoney_receive_persisted_cursors():
    from collectors.realtime_news import fetch_cls_telegraph, fetch_eastmoney_global_news

    cls_payload = {"data": {"roll_data": [{
        "id": 10,
        "ctime": 1788252370,
        "brief": "CLS item",
        "content": "CLS item",
        "shareurl": "https://example.test/cls/10",
        "is_ad": 0,
    }]}}
    eastmoney_payload = {"data": {"fastNewsList": [{
        "code": "202609013861523839",
        "realSort": "1788252991023839",
        "showTime": "2026-09-01 16:41:36",
        "title": "Eastmoney item",
        "summary": "Eastmoney item",
    }]}}
    cls_response = MagicMock(status_code=200)
    cls_response.json.return_value = cls_payload
    cls_response.raise_for_status.return_value = None
    eastmoney_response = MagicMock(status_code=200)
    eastmoney_response.json.return_value = eastmoney_payload
    eastmoney_response.raise_for_status.return_value = None

    with patch("collectors.realtime_news.requests.get", side_effect=[cls_response, eastmoney_response]) as get, \
         patch("collectors.realtime_news.time.sleep"):
        fetch_cls_telegraph(last_time="1788252000")
        fetch_eastmoney_global_news(sort_end="1788252000000000")

    cls_url = get.call_args_list[0].args[0]
    assert "last_time=1788252000" in cls_url
    assert get.call_args_list[1].kwargs["params"]["sortEnd"] == "1788252000000000"


def test_scheduler_persists_only_newer_realtime_cursor():
    from scheduler import _persist_realtime_cursor

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(SourceRegistry(
        source_key="cls_telegraph:main",
        source_type="cls_telegraph",
        display_name="CLS",
        config_json=json.dumps({"last_time": "10"}),
        lane="realtime",
        is_active=1,
    ))
    session.commit()

    with patch("db.database.get_session", return_value=session):
        _persist_realtime_cursor(
            "cls_telegraph:main",
            "cls_telegraph",
            [{"_provider_cursor": "9"}, {"_provider_cursor": "11"}],
        )

    session.expire_all()
    source = session.query(SourceRegistry).filter_by(source_key="cls_telegraph:main").one()
    assert json.loads(source.config_json)["last_time"] == "11"
    session.close()


def test_legacy_database_migration_keeps_lane_columns_non_null():
    from sqlalchemy import inspect, text

    from db.migrations import run_migrations

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE articles ("
            "id INTEGER PRIMARY KEY, source TEXT NOT NULL, source_id TEXT, "
            "author TEXT, title TEXT, content TEXT, url TEXT, tags TEXT, "
            "score INTEGER NOT NULL DEFAULT 0, published_at DATETIME, "
            "collected_at DATETIME NOT NULL)"
        ))
        connection.execute(text(
            "CREATE TABLE source_registry ("
            "id INTEGER PRIMARY KEY, source_key TEXT NOT NULL UNIQUE, "
            "source_type TEXT NOT NULL, display_name TEXT NOT NULL, category TEXT, "
            "config_json TEXT NOT NULL, owner_type TEXT NOT NULL, "
            "visibility TEXT NOT NULL, is_active INTEGER NOT NULL, "
            "retired_at DATETIME, schedule_hours INTEGER, priority INTEGER NOT NULL)"
        ))
        connection.execute(text(
            "CREATE TABLE collector_runs ("
            "id INTEGER PRIMARY KEY, source_type TEXT NOT NULL, source_key TEXT, "
            "status TEXT NOT NULL, articles_fetched INTEGER NOT NULL DEFAULT 0, "
            "articles_saved INTEGER NOT NULL DEFAULT 0, duration_ms INTEGER NOT NULL DEFAULT 0, "
            "error_message TEXT, error_category TEXT, retry_count INTEGER NOT NULL DEFAULT 0, "
            "completed_at DATETIME NOT NULL)"
        ))

    run_migrations(engine)
    columns = {
        column["name"]: column
        for column in inspect(engine).get_columns("articles")
    }
    source_columns = {
        column["name"]: column
        for column in inspect(engine).get_columns("source_registry")
    }
    run_columns = {
        column["name"]: column
        for column in inspect(engine).get_columns("collector_runs")
    }
    assert columns["collection_lane"]["nullable"] is False
    assert source_columns["lane"]["nullable"] is False
    assert run_columns["articles_duplicate"]["nullable"] is False
    assert run_columns["articles_failed"]["nullable"] is False
