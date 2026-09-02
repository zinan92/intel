#!/usr/bin/env python3
"""Explicitly activate seeded realtime sources after an operator review."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from db.database import get_session, init_db
from sources.registry import list_all_sources

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _ready_for_activation(source) -> bool:
    if source.source_type != "telegram_mtproto":
        return True
    from collectors.telegram_mtproto import APPROVED_CHANNEL_NAMES

    try:
        channel_ids = json.loads(source.config_json).get("channel_ids", {})
        numeric_ids = [int(channel_ids[name]) for name in APPROVED_CHANNEL_NAMES]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return False
    return (
        set(channel_ids) == set(APPROVED_CHANNEL_NAMES)
        and len(set(numeric_ids)) == len(APPROVED_CHANNEL_NAMES)
    )


def main() -> None:
    if not config.realtime_lane_enabled():
        raise SystemExit(
            "Set REALTIME_LANE_ENABLED=1 for this explicit activation command "
            "after reviewing source terms."
        )

    init_db()
    session = get_session()
    try:
        activated = 0
        for source in list_all_sources(session):
            if (
                source.lane == "realtime"
                and source.is_active == 0
                and source.retired_at is None
                and _ready_for_activation(source)
            ):
                source.is_active = 1
                activated += 1
        session.commit()
        logger.info("Activated %d realtime source(s)", activated)
    finally:
        session.close()


if __name__ == "__main__":
    main()
