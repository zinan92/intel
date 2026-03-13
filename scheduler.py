"""APScheduler-based collector scheduler for park-intel.

Automatically runs all collectors on configurable intervals.
Integrates with FastAPI lifespan for clean startup/shutdown.
"""
from __future__ import annotations

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

    Per-source intervals are defined in config.ACTIVE_SOURCES (single source of truth).
    Only non-source parameters live here.
    """

    llm_tagger_interval_hours: int = 4
    timezone: str = "Asia/Shanghai"


# Module-level storage for last run results (read by health endpoint)
_last_results: dict[str, CollectorResult] = {}


def get_last_results() -> dict[str, CollectorResult]:
    """Get the last run result for each collector."""
    return dict(_last_results)


def _run_collector_safe(collector_cls: type, source_name: str) -> CollectorResult:
    """Run a single collector with full error capture. Never raises."""
    start = time.time()
    try:
        collector = collector_cls()
        articles = collector.collect()
        fetched = len(articles) if articles else 0
        saved = collector.save(articles) if articles else 0
        result = CollectorResult(
            source=source_name,
            articles_fetched=fetched,
            articles_saved=saved,
            duration_seconds=round(time.time() - start, 1),
            error=None,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.exception("[%s] Collector failed", source_name)
        result = CollectorResult(
            source=source_name,
            articles_fetched=0,
            articles_saved=0,
            duration_seconds=round(time.time() - start, 1),
            error=str(e),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    _last_results[source_name] = result

    if result.error:
        logger.error(
            "[%s] FAILED (%.1fs): %s",
            source_name, result.duration_seconds, result.error[:200],
        )
    elif result.articles_fetched == 0:
        logger.warning("[%s] No articles fetched (%.1fs)", source_name, result.duration_seconds)
    else:
        logger.info(
            "[%s] OK — fetched=%d, saved=%d (%.1fs)",
            source_name, result.articles_fetched, result.articles_saved,
            result.duration_seconds,
        )

    return result


def _run_llm_tagger() -> None:
    """Run the LLM tagger on the most recent unscored articles (scheduled mode: limit=50)."""
    try:
        from scripts.run_llm_tagger import run_tagger
        run_tagger(limit=50)
    except ImportError:
        logger.warning("LLM tagger script not found, skipping")
    except Exception as e:
        logger.exception("LLM tagger failed: %s", e)


class CollectorScheduler:
    """Manages scheduled collector runs."""

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
        # Playwright (for Xueqiu KOL feeds)
        try:
            import playwright  # noqa: F401
            logger.info("Playwright available — Xueqiu KOL feeds enabled")
        except ImportError:
            logger.warning("Playwright not installed — Xueqiu KOL feeds DISABLED")

        # clawfeed CLI (for ClawFeed collector)
        clawfeed_path = shutil.which("clawfeed") or shutil.which(
            "clawfeed", path="/opt/homebrew/bin:/usr/local/bin"
        )
        if clawfeed_path:
            logger.info("clawfeed CLI found at %s — ClawFeed collector enabled", clawfeed_path)
        else:
            logger.warning("clawfeed CLI not found — ClawFeed collector will return empty results")

    # Map source names (as in config.ACTIVE_SOURCES) to their runner methods.
    _SOURCE_RUNNERS: dict[str, Any] = {}  # populated after class definition

    def _register_jobs(self) -> None:
        """Register collector jobs from config.ACTIVE_SOURCES + llm_tagger.

        config.ACTIVE_SOURCES is the single source of truth for source names and intervals.
        This method never hardcodes intervals — it reads them from config.
        """
        import config as cfg

        jobs: list[tuple[str, int, Any]] = []
        for entry in cfg.ACTIVE_SOURCES:
            src = entry["source"]
            hours = entry["interval_hours"]
            runner = self._SOURCE_RUNNERS.get(src)
            if runner is None:
                logger.warning("No runner registered for active source '%s' — skipping", src)
                continue
            jobs.append((src, hours, runner))

        # LLM tagger is not a data source; add it separately
        jobs.append(("llm_tagger", self._config.llm_tagger_interval_hours, _run_llm_tagger))

        base_time = datetime.now(timezone.utc)
        for idx, (name, hours, func) in enumerate(jobs):
            staggered_start = base_time + timedelta(seconds=30 * idx)
            self._scheduler.add_job(
                func,
                trigger=IntervalTrigger(hours=hours),
                id=f"collector-{name}",
                replace_existing=True,
                next_run_time=staggered_start,
            )
            logger.info("Registered collector job: %s (every %dh, first run at +%ds)", name, hours, 30 * idx)

    @staticmethod
    def _run_hackernews() -> None:
        from collectors.hackernews import HackerNewsCollector
        _run_collector_safe(HackerNewsCollector, "hackernews")

    @staticmethod
    def _run_xueqiu() -> None:
        from collectors.xueqiu import XueqiuCollector
        _run_collector_safe(XueqiuCollector, "xueqiu")

    @staticmethod
    def _run_rss() -> None:
        from collectors.rss import RSSCollector
        _run_collector_safe(RSSCollector, "rss")

    @staticmethod
    def _run_github() -> None:
        from collectors.github_trending import GitHubTrendingCollector
        _run_collector_safe(GitHubTrendingCollector, "github")

    @staticmethod
    def _run_yahoo_finance() -> None:
        from collectors.yahoo_finance import YahooFinanceCollector
        _run_collector_safe(YahooFinanceCollector, "yahoo_finance")

    @staticmethod
    def _run_google_news() -> None:
        from collectors.google_news import GoogleNewsCollector
        _run_collector_safe(GoogleNewsCollector, "google_news")

    @staticmethod
    def _run_clawfeed() -> None:
        from collectors.clawfeed import ClawFeedCollector
        _run_collector_safe(ClawFeedCollector, "clawfeed")

    @staticmethod
    def _run_reddit() -> None:
        from collectors.reddit import RedditCollector
        _run_collector_safe(RedditCollector, "reddit")

    @staticmethod
    def _run_github_release() -> None:
        from collectors.github_release import GitHubReleaseCollector
        _run_collector_safe(GitHubReleaseCollector, "github_release")

    @staticmethod
    def _run_webpage_monitor() -> None:
        from collectors.webpage_monitor import WebpageMonitorCollector
        _run_collector_safe(WebpageMonitorCollector, "webpage_monitor")


# Populate after class definition so static methods are resolved.
# This dict maps source names from config.ACTIVE_SOURCES to their runner callables.
CollectorScheduler._SOURCE_RUNNERS = {
    "hackernews":     CollectorScheduler._run_hackernews,
    "xueqiu":         CollectorScheduler._run_xueqiu,
    "rss":            CollectorScheduler._run_rss,
    "github":         CollectorScheduler._run_github,
    "yahoo_finance":  CollectorScheduler._run_yahoo_finance,
    "google_news":    CollectorScheduler._run_google_news,
    "clawfeed":       CollectorScheduler._run_clawfeed,
    "reddit":         CollectorScheduler._run_reddit,
    "github_release": CollectorScheduler._run_github_release,
    "webpage_monitor":CollectorScheduler._run_webpage_monitor,
}
