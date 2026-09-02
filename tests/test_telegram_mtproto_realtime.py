"""Behavioral tests for the authorized Telegram MTProto realtime source."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import Base
from sources.errors import SourceConfigurationError


class FakeTelegramClient:
    def __init__(self, channels):
        self.channels = channels
        self.connected = False
        self.disconnected = False

    async def connect(self):
        self.connected = True

    async def is_user_authorized(self):
        return True

    async def get_entity(self, channel_id):
        return self.channels[channel_id]["entity"]

    def iter_messages(self, entity, *, limit):
        messages = self.channels[entity.id]["messages"][:limit]

        async def iterator():
            for message in messages:
                yield message

        return iterator()

    async def disconnect(self):
        self.disconnected = True


def _approved_channel_ids():
    return {
        name: channel_id
        for channel_id, name in enumerate([
            "BRICS News",
            "BlockBeats",
            "Global News Monitor",
            "Intel Slava",
            "Disclose.tv",
            "Watcher Guru",
            "Solid Intel",
        ], start=101)
    }


def test_telegram_adapter_normalizes_approved_text_post_and_edit(monkeypatch):
    from sources.adapters import collect_from_source

    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "test-hash")
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", "/tmp/park-intel-test.session")
    entity = SimpleNamespace(id=101, title="BRICS News (renamed)", username="bricsnews")
    message = SimpleNamespace(
        id=77,
        message="JUST IN: Central bank signals an emergency policy meeting.",
        date=datetime(2026, 9, 2, 3, 0, tzinfo=timezone.utc),
        edit_date=datetime(2026, 9, 2, 3, 1, 5, tzinfo=timezone.utc),
    )
    channel_names = list(_approved_channel_ids())
    channels = {
        channel_id: {
            "entity": entity if channel_id == 101 else SimpleNamespace(
                id=channel_id,
                title=name,
                username=f"channel{channel_id}",
            ),
            "messages": [message] if channel_id == 101 else [],
        }
        for channel_id, name in enumerate(channel_names, start=101)
    }
    client = FakeTelegramClient(channels)
    monkeypatch.setattr(
        "collectors.telegram_mtproto._build_client",
        lambda: client,
    )

    rows, result = collect_from_source({
        "source_key": "telegram_mtproto:approved-channels",
        "source_type": "telegram_mtproto",
        "config": {
            "channel_ids": _approved_channel_ids(),
            "message_limit": 20,
        },
    })

    assert result.status == "ok"
    assert rows == [{
        "source": "telegram_mtproto",
        "source_id": "telegram_mtproto:101:77:20260902T030105000000",
        "author": "BRICS News",
        "title": "JUST IN: Central bank signals an emergency policy meeting.",
        "content": "JUST IN: Central bank signals an emergency policy meeting.",
        "url": "https://t.me/bricsnews/77",
        "tags": ["telegram", "brics-news"],
        "score": 0,
        "published_at": datetime(2026, 9, 2, 3, 0),
        "collection_lane": "realtime",
        "source_authority": "secondary",
        "corroboration_state": "unconfirmed",
        "pin_eligibility": "requires_independent_confirmation",
        "review_state": "confirmation_required",
        "provider_channel_id": "101",
        "provider_message_id": "77",
        "provider_edit_at": datetime(2026, 9, 2, 3, 1, 5),
        "_timestamp_status": "valid",
    }]
    assert client.connected is True
    assert client.disconnected is True


def test_telegram_source_seeds_exact_display_name_contract_without_ids(monkeypatch):
    from sources.registry import get_source_by_key
    from sources.seed import seed_source_registry

    monkeypatch.setenv("REALTIME_LANE_ENABLED", "1")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_source_registry(session)
        source = get_source_by_key(session, "telegram_mtproto:approved-channels")

    assert source is not None
    assert source.lane == "realtime"
    assert source.is_active == 0
    assert source.schedule_seconds == 60
    config = json.loads(source.config_json)
    assert config["approved_channel_names"] == [
        "BRICS News",
        "BlockBeats",
        "Global News Monitor",
        "Intel Slava",
        "Disclose.tv",
        "Watcher Guru",
        "Solid Intel",
    ]
    assert config["channel_ids"] == {}
    assert "Pavel Durov" not in config["approved_channel_names"]


def test_telegram_runtime_rejects_incomplete_or_duplicate_numeric_allowlist(monkeypatch):
    from sources.adapters import collect_from_source

    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "test-hash")
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", "/tmp/park-intel-test.session")
    rows, incomplete = collect_from_source({
        "source_key": "telegram_mtproto:approved-channels",
        "source_type": "telegram_mtproto",
        "config": {"channel_ids": {"BRICS News": 101}},
    })
    rows_duplicate, duplicate = collect_from_source({
        "source_key": "telegram_mtproto:approved-channels",
        "source_type": "telegram_mtproto",
        "config": {
            "channel_ids": {
                "BRICS News": 101,
                "BlockBeats": 101,
                "Global News Monitor": 103,
                "Intel Slava": 104,
                "Disclose.tv": 105,
                "Watcher Guru": 106,
                "Solid Intel": 107,
            },
        },
    })

    assert rows == rows_duplicate == []
    assert incomplete.error_category == "config"
    assert "exactly the approved seven" in incomplete.error_message
    assert duplicate.error_category == "config"
    assert "unique" in duplicate.error_message


def test_telegram_setup_resolves_each_joined_channel_once_and_excludes_pavel():
    from collectors.telegram_mtproto import resolve_approved_channel_ids

    joined = [
        ("BRICS News", 101),
        ("BlockBeats", 102),
        ("Global News Monitor", 103),
        ("Intel Slava", 104),
        ("Disclose.tv", 105),
        ("Watcher Guru", 106),
        ("Solid Intel", 107),
        ("Pavel Durov", 999),
        ("Unrelated Private Chat", 1000),
    ]

    resolved = resolve_approved_channel_ids(joined)

    assert resolved == {
        "BRICS News": 101,
        "BlockBeats": 102,
        "Global News Monitor": 103,
        "Intel Slava": 104,
        "Disclose.tv": 105,
        "Watcher Guru": 106,
        "Solid Intel": 107,
    }
    assert "Pavel Durov" not in resolved


def test_telegram_setup_stops_on_missing_or_ambiguous_name():
    from collectors.telegram_mtproto import resolve_approved_channel_ids

    incomplete = [
        ("BRICS News", 101),
        ("BlockBeats", 102),
    ]
    ambiguous = [
        ("BRICS News", 101),
        ("BRICS News", 201),
        ("BlockBeats", 102),
        ("Global News Monitor", 103),
        ("Intel Slava", 104),
        ("Disclose.tv", 105),
        ("Watcher Guru", 106),
        ("Solid Intel", 107),
    ]

    for joined in (incomplete, ambiguous):
        try:
            resolve_approved_channel_ids(joined)
        except SourceConfigurationError as exc:
            assert "exactly once" in str(exc)
        else:
            raise AssertionError("setup must reject missing or ambiguous channel names")


def test_telegram_approved_setup_persists_ids_and_activates_source(monkeypatch):
    from scripts.setup_telegram_channels import _persist_channel_ids
    from sources.registry import get_source_by_key
    from sources.seed import seed_source_registry

    monkeypatch.setenv("REALTIME_LANE_ENABLED", "1")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_source_registry(session)
    monkeypatch.setattr("db.database.init_db", lambda: None)
    monkeypatch.setattr("db.database.get_session", lambda: session)

    _persist_channel_ids(_approved_channel_ids())

    verification = Session(engine)
    source = get_source_by_key(
        verification,
        "telegram_mtproto:approved-channels",
    )
    assert source.is_active == 1
    assert json.loads(source.config_json)["channel_ids"] == _approved_channel_ids()
    verification.close()


def test_generic_realtime_activation_cannot_bypass_telegram_setup():
    from scripts.activate_realtime_lane import _ready_for_activation

    source = SimpleNamespace(
        source_type="telegram_mtproto",
        config_json=json.dumps({"channel_ids": {}}),
    )
    approved = SimpleNamespace(
        source_type="telegram_mtproto",
        config_json=json.dumps({"channel_ids": _approved_channel_ids()}),
    )

    assert _ready_for_activation(source) is False
    assert _ready_for_activation(approved) is True


def test_lower_trust_telegram_post_is_persisted_as_watch_needs_review(monkeypatch):
    import collectors.base as base_module
    from collectors.base import BaseCollector
    from db.models import Article
    from scheduler import _run_realtime_triage
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    class Saver(BaseCollector):
        source = "telegram_mtproto"

        def collect(self):
            return []

    monkeypatch.setattr(base_module, "init_db", lambda: None)
    monkeypatch.setattr(base_module, "get_session", factory)
    saver = Saver()
    assert saver.save([{
        "source": "telegram_mtproto",
        "source_id": "telegram_mtproto:103:88:original",
        "author": "Global News Monitor",
        "title": "Unconfirmed geopolitical report",
        "content": "A channel reports an unconfirmed escalation.",
        "published_at": datetime(2026, 9, 2, 4, 0),
        "collection_lane": "realtime",
        "source_authority": "secondary",
        "corroboration_state": "unconfirmed",
        "pin_eligibility": "requires_independent_confirmation",
        "review_state": "needs_review",
        "provider_channel_id": "103",
        "provider_message_id": "88",
        "provider_edit_at": None,
    }]) == 1

    session = factory()

    class FakeTriage:
        model_name = "test-model"

        def __init__(self, **_kwargs):
            pass

        def triage_batch(self, articles):
            return [{
                "id": articles[0]["id"],
                "bucket": "high_impact",
                "direction": "bearish",
                "rationale": "Potentially large if confirmed.",
                "affected_assets": [],
                "watch_for": ["official confirmation"],
                "scenario_bull": "Report is denied.",
                "scenario_bear": "Report is confirmed.",
            }]

    monkeypatch.setattr("db.database.get_session", lambda: session)
    monkeypatch.setattr("scheduler._realtime_lane_enabled", lambda: True)
    monkeypatch.setattr("triage.realtime.RealtimeTriage", FakeTriage)
    _run_realtime_triage()

    session.expire_all()
    article = session.query(Article).one()
    assert article.triage_bucket == "watch"
    assert article.review_state == "needs_review"
    assert article.source_authority == "secondary"
    assert article.corroboration_state == "unconfirmed"
    assert article.pin_eligibility == "requires_independent_confirmation"
    assert article.provider_channel_id == "103"
    assert article.provider_message_id == "88"
    session.close()


def test_telegram_missing_credentials_are_visible_configuration_failure(monkeypatch):
    from sources.adapters import collect_from_source

    for name in ("TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_SESSION_PATH"):
        monkeypatch.delenv(name, raising=False)

    rows, result = collect_from_source({
        "source_key": "telegram_mtproto:approved-channels",
        "source_type": "telegram_mtproto",
        "config": {"channel_ids": _approved_channel_ids()},
    })

    assert rows == []
    assert result.error_category == "config"
    assert "TELEGRAM_API_ID" in result.error_message


def test_telegram_flood_wait_pauses_source_without_automatic_retry(monkeypatch):
    from sources.adapters import collect_from_source

    class FloodWaitError(Exception):
        pass

    class FloodClient(FakeTelegramClient):
        def iter_messages(self, entity, *, limit):
            raise FloodWaitError("wait 300 seconds")

    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "test-hash")
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", "/tmp/park-intel-test.session")
    channels = {
        channel_id: {
            "entity": SimpleNamespace(id=channel_id, title=name, username=None),
            "messages": [],
        }
        for name, channel_id in _approved_channel_ids().items()
    }
    client = FloodClient(channels)
    monkeypatch.setattr("collectors.telegram_mtproto._build_client", lambda: client)

    rows, result = collect_from_source({
        "source_key": "telegram_mtproto:approved-channels",
        "source_type": "telegram_mtproto",
        "config": {"channel_ids": _approved_channel_ids()},
    })

    assert rows == []
    assert result.error_category == "auth"
    assert result.retry_count == 0
    assert "provider blocked" in result.error_message
    assert client.disconnected is True


def test_telegram_original_and_edit_versions_have_stable_distinct_ids(monkeypatch):
    from sources.adapters import collect_from_source

    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "test-hash")
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", "/tmp/park-intel-test.session")

    def client_for(edit_date):
        channels = {}
        for name, channel_id in _approved_channel_ids().items():
            entity = SimpleNamespace(id=channel_id, title=name, username="bricsnews")
            messages = []
            if name == "BRICS News":
                messages = [SimpleNamespace(
                    id=77,
                    message="A developing market report.",
                    date=datetime(2026, 9, 2, 3, 0, tzinfo=timezone.utc),
                    edit_date=edit_date,
                )]
            channels[channel_id] = {"entity": entity, "messages": messages}
        return FakeTelegramClient(channels)

    edited_at = datetime(2026, 9, 2, 3, 1, 5, tzinfo=timezone.utc)
    clients = [client_for(None), client_for(edited_at), client_for(edited_at)]
    monkeypatch.setattr(
        "collectors.telegram_mtproto._build_client",
        lambda: clients.pop(0),
    )
    record = {
        "source_key": "telegram_mtproto:approved-channels",
        "source_type": "telegram_mtproto",
        "config": {"channel_ids": _approved_channel_ids()},
    }

    original, _ = collect_from_source(record)
    edited, _ = collect_from_source(record)
    replay, _ = collect_from_source(record)

    assert original[0]["source_id"] == "telegram_mtproto:101:77:original"
    assert edited[0]["source_id"] == "telegram_mtproto:101:77:20260902T030105000000"
    assert replay[0]["source_id"] == edited[0]["source_id"]
