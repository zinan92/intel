"""Launchd entrypoint for Sunday Weekly publication and Monday catch-up."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from scripts.publish_weekly_finance_newsletter import (
    WeeklyDeliveryError,
    WeeklyGenerationError,
    publish_weekly_finance_newsletter,
)


BRIEF_TIMEZONE = ZoneInfo("Asia/Shanghai")
logger = logging.getLogger(__name__)


def scheduled_week_ending(now: datetime) -> date | None:
    local_now = now if now.tzinfo is not None else now.replace(tzinfo=BRIEF_TIMEZONE)
    local_now = local_now.astimezone(BRIEF_TIMEZONE)
    if local_now.weekday() == 6:
        return local_now.date()
    if local_now.weekday() == 0:
        return local_now.date() - timedelta(days=1)
    return None


def run_scheduled_weekly(now: datetime | None = None) -> str:
    target = scheduled_week_ending(now or datetime.now(BRIEF_TIMEZONE))
    if target is None:
        logger.info("Weekly scheduler noop outside Sunday/Monday catch-up window")
        return "noop"
    result = publish_weekly_finance_newsletter(target)
    logger.info("Weekly scheduler result=%s week_ending=%s", result.status, target)
    return result.status


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        print(f"weekly_scheduler: {run_scheduled_weekly()}")
    except (WeeklyDeliveryError, WeeklyGenerationError):
        logger.exception("Weekly scheduled delivery failed")
        raise SystemExit(1)
