"""Source registry service — CRUD operations for SourceRegistry records."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from db.models import SourceRegistry

logger = logging.getLogger(__name__)


def list_active_sources(session: Session) -> list[SourceRegistry]:
    """Return all active (non-retired) source registry records."""
    return (
        session.query(SourceRegistry)
        .filter(SourceRegistry.is_active == 1)
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


def upsert_source(session: Session, payload: dict[str, Any]) -> SourceRegistry:
    """Insert or update a source registry record by source_key.

    The payload should include:
      - source_key (required)
      - source_type (required)
      - display_name (required)
      - config (dict, serialized to config_json)
      - category, owner_type, visibility, is_active, schedule_hours, priority (optional)
    """
    source_key = payload["source_key"]
    existing = get_source_by_key(session, source_key)

    config_raw = payload.get("config", {})
    config_json = json.dumps(config_raw) if isinstance(config_raw, dict) else str(config_raw)

    if existing is not None:
        existing.source_type = payload.get("source_type", existing.source_type)
        existing.display_name = payload.get("display_name", existing.display_name)
        existing.category = payload.get("category", existing.category)
        existing.config_json = config_json
        existing.owner_type = payload.get("owner_type", existing.owner_type)
        existing.visibility = payload.get("visibility", existing.visibility)
        existing.is_active = payload.get("is_active", existing.is_active)
        existing.schedule_hours = payload.get("schedule_hours", existing.schedule_hours)
        existing.priority = payload.get("priority", existing.priority)
        session.commit()
        return existing

    record = SourceRegistry(
        source_key=source_key,
        source_type=payload["source_type"],
        display_name=payload["display_name"],
        category=payload.get("category"),
        config_json=config_json,
        owner_type=payload.get("owner_type", "system"),
        visibility=payload.get("visibility", "internal"),
        is_active=payload.get("is_active", 1),
        schedule_hours=payload.get("schedule_hours"),
        priority=payload.get("priority", 100),
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
