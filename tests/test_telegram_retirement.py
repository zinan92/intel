"""Behavioral contract for permanent Telegram source retirement."""

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import config
from db.migrations import run_migrations
from db.models import Article, Base, SourceRegistry
from sources.adapters import get_adapter
from sources.registry import get_source_by_key, list_active_sources, upsert_source
from sources.seed import seed_source_registry


def test_telegram_has_no_runtime_adapter_or_bootstrap_source():
    assert get_adapter("telegram_mtproto") is None
    assert "telegram_mtproto" not in config.REALTIME_SOURCE_TYPES
    assert all(
        entry["source"] != "telegram_mtproto"
        for entry in config.REALTIME_SOURCE_BOOTSTRAP
    )


def test_startup_migration_retires_legacy_telegram_source_without_deleting_it():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(SourceRegistry(
            source_key="telegram_mtproto:approved-channels",
            source_type="telegram_mtproto",
            display_name="Authorized Telegram Channels",
            config_json=json.dumps({"channel_ids": {"BlockBeats": 123}}),
            is_active=1,
            lane="realtime",
            schedule_seconds=60,
        ))
        session.add(Article(
            source="telegram_mtproto",
            source_id="telegram:123:456",
            title="Preserved historical post",
            collection_lane="realtime",
        ))
        session.commit()

    run_migrations(engine)

    with Session(engine) as session:
        source = get_source_by_key(
            session,
            "telegram_mtproto:approved-channels",
        )
        assert source is not None
        assert source.is_active == 0
        assert source.retired_at is not None
        assert json.loads(source.config_json)["channel_ids"] == {"BlockBeats": 123}
        assert session.query(Article).filter_by(
            source_id="telegram:123:456",
        ).count() == 1


def test_generic_upsert_cannot_reactivate_or_recreate_telegram_source():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        upsert_source(session, {
            "source_key": "telegram_mtproto:approved-channels",
            "source_type": "telegram_mtproto",
            "display_name": "Legacy Telegram",
            "is_active": 1,
            "lane": "realtime",
            "schedule_seconds": 60,
        })
        source = get_source_by_key(
            session,
            "telegram_mtproto:approved-channels",
        )
        assert source is not None
        assert source.is_active == 0
        assert source.retired_at is not None

        upsert_source(session, {
            "source_key": source.source_key,
            "is_active": 1,
        })
        assert list_active_sources(session) == []
        assert source.is_active == 0
        assert source.retired_at is not None


def test_scheduler_rejects_active_legacy_telegram_row(monkeypatch):
    from scheduler import CollectorScheduler

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(SourceRegistry(
        source_key="telegram_mtproto:approved-channels",
        source_type="telegram_mtproto",
        display_name="Legacy Telegram",
        is_active=1,
        lane="realtime",
        schedule_seconds=60,
    ))
    session.commit()
    monkeypatch.setenv("REALTIME_LANE_ENABLED", "1")
    monkeypatch.setattr("db.database.get_session", lambda: session)

    scheduler = CollectorScheduler()
    scheduler._register_jobs()

    assert "realtime-telegram_mtproto" not in {
        job.id for job in scheduler._scheduler.get_jobs()
    }


def test_fresh_seed_does_not_recreate_telegram_source(monkeypatch):
    monkeypatch.setenv("REALTIME_LANE_ENABLED", "1")
    monkeypatch.setenv("TELEGRAM_API_ID", "legacy-id")
    monkeypatch.setenv("TELEGRAM_API_HASH", "legacy-hash")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_source_registry(session)
        assert get_source_by_key(
            session,
            "telegram_mtproto:approved-channels",
        ) is None
