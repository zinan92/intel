"""APScheduler-based collector scheduler for park-intel.

Registry-driven: loads active source records from the source registry,
groups by source_type, and dispatches through the adapter layer.
Integrates with FastAPI lifespan for clean startup/shutdown.
"""
from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollectorResult:
    """Immutable result of a single collector run."""

    source: str
    articles_fetched: int
    articles_saved: int
    duration_seconds: float
    error: str | None
    timestamp: str


@dataclass(frozen=True)
class SchedulerConfig:
    """Immutable scheduler configuration.

    Per-source intervals are defined in the source registry (single source of truth).
    Only non-source parameters live here.
    """

    llm_tagger_interval_hours: int = 4
    timezone: str = "Asia/Shanghai"


# Module-level storage for last run results (read by health endpoint)
_last_results: dict[str, CollectorResult] = {}


def get_last_results() -> dict[str, CollectorResult]:
    """Get the last run result for each collector."""
    return dict(_last_results)


def _run_source_type(source_type: str) -> None:
    """Run all active source instances of a given type through the adapter layer.

    Groups per-instance sources (rss, reddit, etc.) into a single scheduler job.
    Each instance is collected individually via the adapter, then articles are
    saved via BaseCollector.save().
    """
    from collectors.base import BaseCollector
    from db.database import get_session
    from sources.adapters import collect_from_source
    from sources.registry import list_active_sources

    start = time.time()
    session = get_session()
    try:
        active = list_active_sources(session)
        instances = [s for s in active if s.source_type == source_type]
    finally:
        session.close()

    if not instances:
        logger.warning("[%s] No active instances in registry — skipping", source_type)
        return

    total_fetched = 0
    total_saved = 0
    errors: list[str] = []

    for instance in instances:
        record = {
            "source_key": instance.source_key,
            "source_type": instance.source_type,
            "display_name": instance.display_name,
            "category": instance.category,
            "config_json": instance.config_json,
        }
        try:
            articles = collect_from_source(record)
            fetched = len(articles)
            total_fetched += fetched
            if articles:
                # Use a minimal collector to save (reuses BaseCollector.save dedup)
                saver = _ArticleSaver(source_type)
                saved = saver.save(articles)
                total_saved += saved
        except Exception as e:
            logger.exception("[%s] Instance %s failed", source_type, instance.source_key)
            errors.append(f"{instance.source_key}: {e}")

    duration = round(time.time() - start, 1)
    error_msg = "; ".join(errors) if errors else None

    result = CollectorResult(
        source=source_type,
        articles_fetched=total_fetched,
        articles_saved=total_saved,
        duration_seconds=duration,
        error=error_msg,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    _last_results[source_type] = result

    if result.error:
        logger.error("[%s] PARTIAL FAILURE (%.1fs): %s", source_type, duration, error_msg[:200])
    elif total_fetched == 0:
        logger.warning("[%s] No articles fetched (%.1fs)", source_type, duration)
    else:
        logger.info(
            "[%s] OK — fetched=%d, saved=%d, instances=%d (%.1fs)",
            source_type, total_fetched, total_saved, len(instances), duration,
        )


class _ArticleSaver:
    """Minimal wrapper to reuse BaseCollector.save() without needing a full collector."""

    def __init__(self, source_type: str) -> None:
        from db.database import init_db
        init_db()
        self._source_type = source_type

    def save(self, articles: list[dict[str, Any]]) -> int:
        from collectors.base import BaseCollector

        class _Saver(BaseCollector):
            source = self._source_type

            def collect(self):
                return []

        saver = _Saver()
        return saver.save(articles)


def _run_llm_tagger() -> None:
    """Run the LLM tagger on the most recent unscored articles (scheduled mode: limit=50)."""
    try:
        from scripts.run_llm_tagger import run_tagger
        run_tagger(limit=50)
    except ImportError:
        logger.warning("LLM tagger script not found, skipping")
    except Exception as e:
        logger.exception("LLM tagger failed: %s", e)


def _run_event_aggregation() -> None:
    """Run event aggregation on recent articles."""
    from db.database import get_session
    from events.aggregator import run_aggregation

    session = get_session()
    try:
        run_aggregation(session)
    except Exception:
        logger.exception("Event aggregation failed")
    finally:
        session.close()


class CollectorScheduler:
    """Manages scheduled collector runs via registry-driven dispatch."""

    def __init__(self, config: SchedulerConfig | None = None) -> None:
        self._config = config or SchedulerConfig()
        self._scheduler = BackgroundScheduler(timezone=self._config.timezone)

    def start(self) -> None:
        """Register all jobs and start the scheduler."""
        self._check_dependencies()
        self._register_jobs()
        self._scheduler.start()
        logger.info("CollectorScheduler started with %d jobs", len(self._scheduler.get_jobs()))

    def shutdown(self) -> None:
        """Gracefully stop the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("CollectorScheduler stopped")

    def _check_dependencies(self) -> None:
        """Log warnings for missing optional dependencies."""
        try:
            import playwright  # noqa: F401
            logger.info("Playwright available — Xueqiu KOL feeds enabled")
        except ImportError:
            logger.warning("Playwright not installed — Xueqiu KOL feeds DISABLED")

        clawfeed_path = shutil.which("clawfeed") or shutil.which(
            "clawfeed", path="/opt/homebrew/bin:/usr/local/bin"
        )
        if clawfeed_path:
            logger.info("clawfeed CLI found at %s — social_kol collector enabled", clawfeed_path)
        else:
            logger.warning("clawfeed CLI not found — social_kol collector will return empty results")

    def _register_jobs(self) -> None:
        """Register collector jobs from the source registry + llm_tagger.

        The source registry is the single source of truth for source types
        and intervals. One job is created per source_type (not per instance).
        """
        from db.database import get_session
        from sources.registry import list_active_sources

        session = get_session()
        try:
            active = list_active_sources(session)
        finally:
            session.close()

        # Group by source_type, take the minimum schedule_hours per type
        type_intervals: dict[str, int] = {}
        for src in active:
            hours = src.schedule_hours
            if hours is None:
                continue
            if src.source_type not in type_intervals or hours < type_intervals[src.source_type]:
                type_intervals[src.source_type] = hours

        jobs: list[tuple[str, int]] = []
        for source_type, hours in sorted(type_intervals.items()):
            jobs.append((source_type, hours))

        # LLM tagger is not a data source; add it separately
        base_time = datetime.now(timezone.utc)
        for idx, (source_type, hours) in enumerate(jobs):
            staggered_start = base_time + timedelta(seconds=30 * idx)
            self._scheduler.add_job(
                _run_source_type,
                args=[source_type],
                trigger=IntervalTrigger(hours=hours),
                id=f"collector-{source_type}",
                replace_existing=True,
                next_run_time=staggered_start,
            )
            logger.info("Registered collector job: %s (every %dh, first run at +%ds)",
                         source_type, hours, 30 * idx)

        # LLM tagger
        tagger_start = base_time + timedelta(seconds=30 * len(jobs))
        self._scheduler.add_job(
            _run_llm_tagger,
            trigger=IntervalTrigger(hours=self._config.llm_tagger_interval_hours),
            id="collector-llm_tagger",
            replace_existing=True,
            next_run_time=tagger_start,
        )
        logger.info("Registered LLM tagger job (every %dh)", self._config.llm_tagger_interval_hours)

        # Event aggregation (every 1 hour)
        aggregation_start = base_time + timedelta(seconds=30 * (len(jobs) + 1))
        self._scheduler.add_job(
            _run_event_aggregation,
            trigger=IntervalTrigger(hours=1),
            id="event-aggregation",
            replace_existing=True,
            next_run_time=aggregation_start,
        )
        logger.info("Registered event aggregation job (every 1h)")
