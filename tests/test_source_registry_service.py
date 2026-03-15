"""Tests for the source registry service layer."""

import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base, SourceRegistry
from sources.registry import (
    get_source_by_key,
    list_active_sources,
    list_all_sources,
    retire_source,
    upsert_source,
)


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    factory = sessionmaker(bind=engine)
    sess = factory()
    yield sess
    sess.close()


def _make_source(key: str, source_type: str = "rss", active: int = 1, **kwargs):
    """Helper to build a source payload dict."""
    payload = {
        "source_key": key,
        "source_type": source_type,
        "display_name": kwargs.get("display_name", key),
        "category": kwargs.get("category"),
        "config": kwargs.get("config", {}),
        "owner_type": kwargs.get("owner_type", "system"),
        "visibility": kwargs.get("visibility", "internal"),
        "is_active": active,
        "schedule_hours": kwargs.get("schedule_hours"),
        "priority": kwargs.get("priority", 100),
    }
    return payload


class TestListActiveSources:
    def test_returns_only_active(self, session: Session):
        upsert_source(session, _make_source("rss:a", active=1))
        upsert_source(session, _make_source("rss:b", active=0))
        upsert_source(session, _make_source("rss:c", active=1))

        active = list_active_sources(session)
        keys = [s.source_key for s in active]
        assert "rss:a" in keys
        assert "rss:c" in keys
        assert "rss:b" not in keys

    def test_empty_db(self, session: Session):
        assert list_active_sources(session) == []


class TestListAllSources:
    def test_returns_all(self, session: Session):
        upsert_source(session, _make_source("rss:a", active=1))
        upsert_source(session, _make_source("rss:b", active=0))

        all_sources = list_all_sources(session)
        assert len(all_sources) == 2


class TestGetSourceByKey:
    def test_found(self, session: Session):
        upsert_source(session, _make_source("reddit:localllama", source_type="reddit"))
        result = get_source_by_key(session, "reddit:localllama")
        assert result is not None
        assert result.source_type == "reddit"

    def test_not_found(self, session: Session):
        result = get_source_by_key(session, "nonexistent:key")
        assert result is None


class TestUpsertSource:
    def test_insert_new(self, session: Session):
        payload = _make_source(
            "rss:openai-blog",
            display_name="OpenAI Blog",
            category="llm",
            config={"url": "https://openai.com/blog/rss.xml"},
            schedule_hours=6,
        )
        upsert_source(session, payload)

        result = get_source_by_key(session, "rss:openai-blog")
        assert result is not None
        assert result.display_name == "OpenAI Blog"
        assert result.category == "llm"
        assert json.loads(result.config_json) == {"url": "https://openai.com/blog/rss.xml"}
        assert result.schedule_hours == 6

    def test_update_existing(self, session: Session):
        upsert_source(session, _make_source("rss:test", display_name="Original"))
        upsert_source(session, _make_source("rss:test", display_name="Updated", category="crypto"))

        result = get_source_by_key(session, "rss:test")
        assert result is not None
        assert result.display_name == "Updated"
        assert result.category == "crypto"

    def test_config_serialized_as_json(self, session: Session):
        payload = _make_source("rss:cfg", config={"url": "http://example.com", "max_items": 10})
        upsert_source(session, payload)

        result = get_source_by_key(session, "rss:cfg")
        assert result is not None
        parsed = json.loads(result.config_json)
        assert parsed == {"url": "http://example.com", "max_items": 10}

    def test_partial_update_preserves_config(self, session: Session):
        """Bug fix: partial update without config must not wipe stored config."""
        original_config = {"url": "https://example.com/feed", "max_items": 50}
        upsert_source(session, _make_source("rss:partial", config=original_config))

        # Update only display_name, omit config entirely
        upsert_source(session, {"source_key": "rss:partial", "display_name": "Renamed"})

        result = get_source_by_key(session, "rss:partial")
        assert result is not None
        assert result.display_name == "Renamed"
        assert json.loads(result.config_json) == original_config

    def test_config_list_serialized_as_valid_json(self, session: Session):
        """Bug fix: non-dict config (list, bool, etc.) must produce valid JSON."""
        list_config = ["tag1", "tag2", "tag3"]
        upsert_source(session, _make_source("rss:list-cfg", config=list_config))

        result = get_source_by_key(session, "rss:list-cfg")
        assert result is not None
        parsed = json.loads(result.config_json)  # Must not raise
        assert parsed == list_config

    def test_config_string_serialized_as_valid_json(self, session: Session):
        """Non-dict config: string value produces valid JSON string."""
        upsert_source(session, _make_source("rss:str-cfg", config="simple-value"))

        result = get_source_by_key(session, "rss:str-cfg")
        assert result is not None
        parsed = json.loads(result.config_json)
        assert parsed == "simple-value"

    def test_reactivate_clears_retired_at(self, session: Session):
        """Bug fix: reactivating a retired source must clear retired_at."""
        upsert_source(session, _make_source("rss:bounce", active=1))
        retire_source(session, "rss:bounce")

        # Verify it's retired
        result = get_source_by_key(session, "rss:bounce")
        assert result is not None
        assert result.is_active == 0
        assert result.retired_at is not None

        # Reactivate
        upsert_source(session, {"source_key": "rss:bounce", "is_active": 1})

        result = get_source_by_key(session, "rss:bounce")
        assert result is not None
        assert result.is_active == 1
        assert result.retired_at is None


class TestRetireSource:
    def test_retire_marks_inactive(self, session: Session):
        upsert_source(session, _make_source("rss:old", active=1))
        retire_source(session, "rss:old")

        result = get_source_by_key(session, "rss:old")
        assert result is not None
        assert result.is_active == 0
        assert result.retired_at is not None

    def test_retire_nonexistent_is_noop(self, session: Session):
        # Should not raise
        retire_source(session, "nonexistent:key")

    def test_retired_excluded_from_active(self, session: Session):
        upsert_source(session, _make_source("rss:keep", active=1))
        upsert_source(session, _make_source("rss:retire", active=1))
        retire_source(session, "rss:retire")

        active = list_active_sources(session)
        keys = [s.source_key for s in active]
        assert "rss:keep" in keys
        assert "rss:retire" not in keys
