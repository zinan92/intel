"""Source registry service — CRUD operations for SourceRegistry records."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from db.models import SourceRegistry

logger = logging.getLogger(__name__)

# Policy-denied source types remain queryable for audit/history but can never
# be made active through generic registry CRUD. This is intentionally separate
# from adapter availability so a future refactor cannot silently re-enable one.
PERMANENTLY_RETIRED_SOURCE_TYPES = frozenset({"telegram_mtproto"})


def list_active_sources(session: Session) -> list[SourceRegistry]:
    """Return all source registry records where is_active == 1."""
    return (
        session.query(SourceRegistry)
        .filter(SourceRegistry.is_active == 1)
        .filter(~SourceRegistry.source_type.in_(PERMANENTLY_RETIRED_SOURCE_TYPES))
        .order_by(SourceRegistry.priority, SourceRegistry.source_key)
        .all()
    )


def list_all_sources(session: Session) -> list[SourceRegistry]:
    """Return all source registry records including retired ones."""
    return (
        session.query(SourceRegistry)
        .order_by(SourceRegistry.source_key)
        .all()
    )


def get_source_by_key(session: Session, source_key: str) -> SourceRegistry | None:
    """Return a single source by its unique key, or None."""
    return (
        session.query(SourceRegistry)
        .filter(SourceRegistry.source_key == source_key)
        .first()
    )


def _serialize_config(config_raw: Any) -> str:
    """Serialize a config value to a JSON string. Always produces valid JSON."""
    return json.dumps(config_raw)


_SENTINEL = object()


def upsert_source(session: Session, payload: dict[str, Any]) -> SourceRegistry:
    """Insert or update a source registry record by source_key.

    The payload should include:
      - source_key (required)
      - source_type (required for insert)
      - display_name (required for insert)
      - config (any JSON-serializable value, serialized to config_json)
      - category, owner_type, visibility, is_active, schedule_hours, lane,
        schedule_seconds, expected_freshness_hours, priority (optional)

    On update, only keys present in the payload are modified.
    Reactivating a source (is_active=1) clears retired_at unless its source
    type has been permanently retired by policy.
    """
    source_key = payload["source_key"]
    existing = get_source_by_key(session, source_key)

    if existing is not None:
        original_source_type = existing.source_type
        existing.source_type = payload.get("source_type", existing.source_type)
        existing.display_name = payload.get("display_name", existing.display_name)
        existing.category = payload.get("category", existing.category)
        existing.owner_type = payload.get("owner_type", existing.owner_type)
        existing.visibility = payload.get("visibility", existing.visibility)
        if "schedule_hours" in payload:
            existing.schedule_hours = payload["schedule_hours"]
        if "lane" in payload:
            existing.lane = payload["lane"]
        if "schedule_seconds" in payload:
            existing.schedule_seconds = payload["schedule_seconds"]
        if "expected_freshness_hours" in payload:
            existing.expected_freshness_hours = payload["expected_freshness_hours"]
        if "priority" in payload:
            existing.priority = payload["priority"]

        # Only update config_json if config is explicitly provided
        config_raw = payload.get("config", _SENTINEL)
        if config_raw is not _SENTINEL:
            existing.config_json = _serialize_config(config_raw)

        # Handle is_active + retired_at consistency
        permanently_retired = (
            original_source_type in PERMANENTLY_RETIRED_SOURCE_TYPES
            or existing.source_type in PERMANENTLY_RETIRED_SOURCE_TYPES
        )
        new_active = 0 if permanently_retired else payload.get(
            "is_active", existing.is_active,
        )
        existing.is_active = new_active
        if permanently_retired and existing.retired_at is None:
            existing.retired_at = datetime.now(timezone.utc)
        elif new_active == 1 and existing.retired_at is not None:
            existing.retired_at = None

        session.commit()
        return existing

    config_json = _serialize_config(payload.get("config", {}))

    permanently_retired = (
        payload["source_type"] in PERMANENTLY_RETIRED_SOURCE_TYPES
    )
    record = SourceRegistry(
        source_key=source_key,
        source_type=payload["source_type"],
        display_name=payload["display_name"],
        category=payload.get("category"),
        config_json=config_json,
        owner_type=payload.get("owner_type", "system"),
        visibility=payload.get("visibility", "internal"),
        is_active=0 if permanently_retired else payload.get("is_active", 1),
        retired_at=datetime.now(timezone.utc) if permanently_retired else None,
        schedule_hours=payload.get("schedule_hours"),
        lane=payload.get("lane", "hourly"),
        schedule_seconds=payload.get("schedule_seconds"),
        priority=payload.get("priority", 100),
        expected_freshness_hours=payload.get("expected_freshness_hours"),
    )
    session.add(record)
    session.commit()
    return record


def retire_source(session: Session, source_key: str) -> None:
    """Mark a source as retired (inactive) without deleting it."""
    existing = get_source_by_key(session, source_key)
    if existing is None:
        logger.debug("retire_source: key %r not found, skipping", source_key)
        return
    existing.is_active = 0
    existing.retired_at = datetime.now(timezone.utc)
    session.commit()
