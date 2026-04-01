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


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _get_scheduler_alive() -> bool:
    """Check if the scheduler heartbeat is recent (< 10 minutes)."""
    from scheduler import get_heartbeat

    heartbeat = get_heartbeat()
    if heartbeat is None:
        return False
    age = (datetime.now(timezone.utc) - heartbeat).total_seconds()
    return age < 600  # 10 minutes


def _get_process_health() -> dict[str, Any]:
    """Return process uptime and restart-loop detection."""
    from scheduler import get_process_start, get_uptime_seconds

    uptime = get_uptime_seconds()
    start = get_process_start()
    return {
        "started_at": start.isoformat(),
        "uptime_seconds": round(uptime),
        "restart_loop_warning": uptime < 600,  # < 10 min = likely restarting
    }


def _build_source_details(session) -> list[dict[str, Any]]:
    """Build per-source health details from DB queries.

    Returns a list of dicts, one per source in the registry.
    """
    from sqlalchemy import Date, case, cast, distinct, func

    from db.models import CollectorRun, SourceRegistry

    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)

    # Fetch all sources
    sources = session.query(SourceRegistry).all()

    # Get latest run per source_type via subquery
    latest_subq = (
        session.query(
            CollectorRun.source_type,
            func.max(CollectorRun.completed_at).label("max_completed"),
        )
        .group_by(CollectorRun.source_type)
        .subquery()
    )

    latest_runs_rows = (
        session.query(CollectorRun)
        .join(
            latest_subq,
            (CollectorRun.source_type == latest_subq.c.source_type)
            & (CollectorRun.completed_at == latest_subq.c.max_completed),
        )
        .all()
    )
    latest_runs: dict[str, Any] = {}
    for run in latest_runs_rows:
        latest_runs[run.source_type] = run

    # Get 24h article counts per source_type
    articles_24h_rows = (
        session.query(
            CollectorRun.source_type,
            func.sum(CollectorRun.articles_fetched).label("count_24h"),
        )
        .filter(CollectorRun.completed_at >= cutoff_24h)
        .group_by(CollectorRun.source_type)
        .all()
    )
    articles_24h: dict[str, int] = {row.source_type: row.count_24h or 0 for row in articles_24h_rows}

    # Get 7-day total + distinct days per source_type for average
    articles_7d_rows = (
        session.query(
            CollectorRun.source_type,
            func.sum(CollectorRun.articles_fetched).label("total_7d"),
            func.count(distinct(cast(CollectorRun.completed_at, Date))).label("days_with_data"),
        )
        .filter(CollectorRun.completed_at >= cutoff_7d)
        .group_by(CollectorRun.source_type)
        .all()
    )
    articles_7d_stats: dict[str, tuple[int, int]] = {
        row.source_type: (row.total_7d or 0, row.days_with_data or 0)
        for row in articles_7d_rows
    }

    result = []
    for src in sources:
        st = src.source_type

        # Disabled check
        disabled_reason = _check_source_disabled(st)

        # Latest run info
        latest = latest_runs.get(st)
        last_run_at = None
        last_run_status = None
        last_error = None
        last_error_category = None
        freshness_age_hours = None

        if latest is not None:
            last_run_at = latest.completed_at.isoformat() if latest.completed_at else None
            last_run_status = latest.status
            last_error = latest.error_message
            last_error_category = latest.error_category if latest.status == "error" else None
            if latest.completed_at:
                # SQLite returns naive datetimes; treat as UTC
                completed = latest.completed_at
                if completed.tzinfo is None:
                    completed = completed.replace(tzinfo=timezone.utc)
                age_td = now - completed
                freshness_age_hours = round(age_td.total_seconds() / 3600, 2)

        # Determine status
        if disabled_reason is not None:
            status = "disabled"
        elif not src.is_active:
            status = "disabled"
        else:
            status = compute_status(
                age_hours=freshness_age_hours,
                expected_freshness_hours=src.expected_freshness_hours,
                last_error_category=last_error_category,
            )

        # Volume stats
        count_24h = articles_24h.get(st, 0)
        total_7d, days = articles_7d_stats.get(st, (0, 0))
        avg_7d = total_7d / days if days > 0 else 0.0
        volume_anomaly = compute_volume_anomaly(
            articles_24h=count_24h,
            articles_7d_avg=avg_7d,
            days_with_data=days,
        )

        result.append({
            "source_type": st,
            "display_name": src.display_name,
            "status": status,
            "is_active": bool(src.is_active),
            "freshness_age_hours": freshness_age_hours,
            "expected_freshness_hours": src.expected_freshness_hours,
            "articles_24h": count_24h,
            "articles_7d_avg": round(avg_7d, 1),
            "volume_anomaly": volume_anomaly,
            "last_run_at": last_run_at,
            "last_run_status": last_run_status,
            "last_error": last_error,
            "last_error_category": last_error_category,
            "disabled_reason": disabled_reason,
        })

    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def get_session():
    """Import and return a DB session. Separated for test patching."""
    from db.database import get_session as _get_session
    return _get_session()


@health_router.get("/sources")
def health_sources() -> dict[str, Any]:
    """Per-source health status with freshness, volume, anomaly detection."""
    session = get_session()
    try:
        sources = _build_source_details(session)
        scheduler_alive = _get_scheduler_alive()
        process_health = _get_process_health()
        return {
            "scheduler_alive": scheduler_alive,
            "process": process_health,
            "sources": sources,
        }
    finally:
        session.close()


@health_router.get("/summary")
def health_summary() -> dict[str, Any]:
    """Aggregate health summary across all sources."""
    session = get_session()
    try:
        sources = _build_source_details(session)
        scheduler_alive = _get_scheduler_alive()
        process_health = _get_process_health()

        status_counts = {
            "healthy_count": 0,
            "stale_count": 0,
            "degraded_count": 0,
            "error_count": 0,
            "disabled_count": 0,
        }
        total_articles_24h = 0

        for src in sources:
            s = src["status"]
            if s == "ok":
                status_counts["healthy_count"] += 1
            elif s == "stale":
                status_counts["stale_count"] += 1
            elif s == "degraded":
                status_counts["degraded_count"] += 1
            elif s == "error":
                status_counts["error_count"] += 1
            elif s in ("disabled", "no_data"):
                status_counts["disabled_count"] += 1
            total_articles_24h += src["articles_24h"]

        return {
            "total_sources": len(sources),
            **status_counts,
            "total_articles_24h": total_articles_24h,
            "scheduler_alive": scheduler_alive,
            "process": process_health,
        }
    finally:
        session.close()
