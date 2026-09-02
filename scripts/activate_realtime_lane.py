#!/usr/bin/env python3
"""Explicitly activate seeded realtime sources after an operator review."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from db.database import get_session, init_db
from sources.registry import list_all_sources

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _activation_blocker(source) -> str | None:
    if source.source_type == "blockbeats_newsflash":
        from collectors.blockbeats import blockbeats_key_available

        if not blockbeats_key_available():
            return "BLOCKBEATS_API_KEY missing"
    return None


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
        blockers: list[str] = []
        for source in list_all_sources(session):
            if source.lane != "realtime" or source.is_active != 0 or source.retired_at:
                continue
            blocker = _activation_blocker(source)
            if blocker:
                blockers.append(f"{source.source_key}: {blocker}")
                logger.error("Activation skipped for %s: %s", source.source_key, blocker)
            else:
                source.is_active = 1
                activated += 1
        session.commit()
        logger.info("Activated %d realtime source(s)", activated)
        if blockers:
            raise SystemExit(2)
    finally:
        session.close()


if __name__ == "__main__":
    main()
