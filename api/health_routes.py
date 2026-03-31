"""Health API routes for per-source freshness, status, and volume anomaly.

Provides:
- compute_status(): Determine source health from age and freshness policy
- compute_volume_anomaly(): Flag volume drops vs 7-day average
- _check_source_disabled(): Detect sources missing required env vars
- health_router: FastAPI router with /api/health/sources and /api/health/summary
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)

health_router = APIRouter(prefix="/api/health")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FRESHNESS_DEFAULTS: dict[str, float] = {
    "rss": 2.0,
    "hackernews": 2.0,
    "reddit": 2.0,
    "github_release": 12.0,
    "github_trending": 12.0,
    "yahoo_finance": 6.0,
    "google_news": 4.0,
    "social_kol": 4.0,
    "xueqiu": 4.0,
    "website_monitor": 4.0,
}

_DEFAULT_FRESHNESS_HOURS = 4.0

# Maps source_type -> (env_var_name, human-readable message with enable instructions)
_REQUIRED_RESOURCES: dict[str, tuple[str, str]] = {
    "github_release": (
        "GITHUB_TOKEN",
        "Set GITHUB_TOKEN in .env to enable GitHub release monitoring. "
        "Create a token at https://github.com/settings/tokens",
    ),
    "github_trending": (
        "GITHUB_TOKEN",
        "Set GITHUB_TOKEN in .env to enable GitHub trending monitoring. "
        "Create a token at https://github.com/settings/tokens",
    ),
    "xueqiu": (
        "XUEQIU_COOKIE",
        "Set XUEQIU_COOKIE in .env to enable Xueqiu data collection. "
        "Extract cookie from browser after logging in to xueqiu.com",
    ),
}


# ---------------------------------------------------------------------------
# Pure computation functions (easily testable)
# ---------------------------------------------------------------------------


def compute_status(
    *,
    age_hours: float | None,
    expected_freshness_hours: float | None,
    last_error_category: str | None,
) -> str:
    """Determine source health status.

    Returns one of: "ok", "stale", "degraded", "error", "no_data".

    Rules:
    - If last_error_category is set -> "error"
    - If age_hours is None -> "no_data"
    - If age <= expected -> "ok"
    - If expected < age <= 2*expected -> "stale"
    - If age > 2*expected -> "degraded"
    """
    if last_error_category is not None:
        return "error"
    if age_hours is None:
        return "no_data"

    expected = expected_freshness_hours if expected_freshness_hours is not None else _DEFAULT_FRESHNESS_HOURS

    if age_hours <= expected:
        return "ok"
    if age_hours <= expected * 2:
        return "stale"
    return "degraded"


def compute_volume_anomaly(
    *,
    articles_24h: int,
    articles_7d_avg: float,
    days_with_data: int,
) -> bool | None:
    """Flag volume anomaly when 24h count drops below 50% of 7-day daily average.

    Returns None if fewer than 3 days of data (insufficient baseline).
    """
    if days_with_data < 3:
        return None
    if articles_7d_avg <= 0:
        return None
    return articles_24h < articles_7d_avg * 0.5


def _check_source_disabled(source_type: str) -> str | None:
    """Check if a source type is disabled due to missing env vars.

    Returns a human-readable message if disabled, None if enabled.
    """
    resource = _REQUIRED_RESOURCES.get(source_type)
    if resource is None:
        return None

    env_key, message = resource
    value = os.environ.get(env_key, "")
    if not value.strip():
        return message
    return None
