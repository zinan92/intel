"""Source-type adapters — bridge between registry records and collectors.

Each adapter accepts a source registry record (dict with source_key,
source_type, config/config_json) and returns a list of normalized
article dicts ready for BaseCollector.save().

Thin wrappers: adapters delegate to existing collector methods,
passing config from the registry record instead of global config.
"""

import json
import logging
import time
from typing import Any, Callable

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from sources.errors import CollectorResult, ErrorCategory, categorize_error, is_retryable

logger = logging.getLogger(__name__)

# Type alias for adapter functions
AdapterFn = Callable[[dict[str, Any]], list[dict[str, Any]]]


def _parse_config(record: dict[str, Any]) -> dict[str, Any]:
    """Extract config dict from a source record."""
    if "config" in record and isinstance(record["config"], dict):
        return record["config"]
    config_json = record.get("config_json", "{}")
    return json.loads(config_json) if isinstance(config_json, str) else {}


# --- Per-instance adapters ---

def _adapt_rss(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch articles from one RSS feed using registry config."""
    from collectors.rss import RSSCollector

    cfg = _parse_config(record)
    feed_cfg = {
        "name": cfg.get("name", record.get("display_name", "")),
        "url": cfg["url"],
        "category": record.get("category", ""),
    }
    collector = RSSCollector()
    return collector._fetch_feed(feed_cfg)


def _adapt_reddit(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch top posts from one subreddit using registry config."""
    from collectors.reddit import RedditCollector

    cfg = _parse_config(record)
    sub_cfg = {
        "subreddit": cfg["subreddit"],
        "category": record.get("category", ""),
    }
    collector = RedditCollector()
    return collector._fetch_subreddit(sub_cfg)


def _adapt_github_release(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch releases from one repo using registry config."""
    from collectors.github_release import GitHubReleaseCollector

    cfg = _parse_config(record)
    repo_cfg = {
        "repo": cfg["repo"],
        "category": record.get("category", ""),
    }
    collector = GitHubReleaseCollector()
    return collector._fetch_repo(repo_cfg)


def _adapt_website_monitor(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Run one webpage monitor target using registry config."""
    from collectors.webpage_monitor import WebpageMonitorCollector, _load_state, _save_state, _STATE_FILE

    cfg = _parse_config(record)
    monitor = {
        "name": record.get("display_name", record.get("source_key", "")),
        "type": cfg.get("type"),
        "category": record.get("category", ""),
    }
    if "url" in cfg:
        monitor["url"] = cfg["url"]
    if "repo" in cfg:
        monitor["repo"] = cfg["repo"]
    if "path" in cfg:
        monitor["path"] = cfg["path"]

    collector = WebpageMonitorCollector()
    state = _load_state(_STATE_FILE)

    monitor_type = cfg.get("type")
    if monitor_type == "scrape":
        articles = collector._scrape_blog(monitor, state)
    elif monitor_type == "github_commits":
        articles = collector._monitor_github_commits(monitor, state)
    else:
        logger.warning("Unknown website_monitor type: %s", monitor_type)
        articles = []

    _save_state(_STATE_FILE, state)
    return articles


# --- Single-instance adapters (delegate to full collect()) ---

def _adapt_social_kol(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect curated KOL content via the ClawFeed CLI.

    The registry record's config.handles contains the curated handle list.
    The ClawFeed CLI currently exports its own internal list (not configurable
    via arguments), so the registry handles serve as the declared intent.
    When the CLI gains per-handle filtering, this adapter should pass
    config.handles to it. For now, articles are filtered post-collection
    to match only the registry-configured handles.
    """
    from collectors.social_kol import SocialKolCollector

    cfg = _parse_config(record)
    configured_handles = set(cfg.get("handles", []))

    collector = SocialKolCollector()
    articles = collector.collect()

    if not configured_handles:
        return articles

    # Filter to only articles from registry-configured handles
    filtered = []
    for article in articles:
        author = (article.get("author") or "").lstrip("@")
        if author in configured_handles:
            filtered.append(article)

    if len(filtered) < len(articles):
        logger.info("social_kol: filtered %d → %d articles (registry handles)",
                     len(articles), len(filtered))
    return filtered


def _adapt_hackernews(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect from Hacker News."""
    from collectors.hackernews import HackerNewsCollector

    collector = HackerNewsCollector()
    return collector.collect()


def _adapt_xueqiu(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect from Xueqiu."""
    from collectors.xueqiu import XueqiuCollector

    collector = XueqiuCollector()
    return collector.collect()


def _adapt_yahoo_finance(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect from Yahoo Finance."""
    from collectors.yahoo_finance import YahooFinanceCollector

    collector = YahooFinanceCollector()
    return collector.collect()


def _adapt_google_news(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect from Google News."""
    from collectors.google_news import GoogleNewsCollector

    collector = GoogleNewsCollector()
    return collector.collect()


def _adapt_github_trending(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect from GitHub Trending."""
    from collectors.github_trending import GitHubTrendingCollector

    collector = GitHubTrendingCollector()
    return collector.collect()


# --- Adapter registry ---

_ADAPTERS: dict[str, AdapterFn] = {
    "rss": _adapt_rss,
    "reddit": _adapt_reddit,
    "github_release": _adapt_github_release,
    "website_monitor": _adapt_website_monitor,
    "social_kol": _adapt_social_kol,
    "hackernews": _adapt_hackernews,
    "xueqiu": _adapt_xueqiu,
    "yahoo_finance": _adapt_yahoo_finance,
    "google_news": _adapt_google_news,
    "github_trending": _adapt_github_trending,
}


def get_adapter(source_type: str) -> AdapterFn | None:
    """Return the adapter function for a source type, or None."""
    return _ADAPTERS.get(source_type)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=2, max=30, jitter=2),
    retry=retry_if_exception(is_retryable),
    reraise=True,
)
def _call_adapter_with_retry(adapter_fn: AdapterFn, record: dict[str, Any]) -> list[dict[str, Any]]:
    """Call adapter with automatic retry for transient errors."""
    return adapter_fn(record)


def collect_from_source(record: dict[str, Any]) -> tuple[list[dict[str, Any]], CollectorResult]:
    """Dispatch collection for a source registry record with retry and result capture.

    Args:
        record: dict with at least source_key, source_type, and config/config_json.

    Returns:
        Tuple of (articles, CollectorResult). Articles is empty list on failure.
        CollectorResult carries status, error info, retry count, and duration.
    """
    source_type = record["source_type"]
    source_key = record.get("source_key", "")
    t0 = time.monotonic()

    adapter = get_adapter(source_type)
    if adapter is None:
        logger.warning("No adapter for source type %r (key=%s)", source_type, source_key)
        duration_ms = int((time.monotonic() - t0) * 1000)
        result = CollectorResult(
            source_type=source_type,
            source_key=source_key,
            status="error",
            articles_fetched=0,
            articles_saved=0,
            duration_ms=duration_ms,
            error_message=f"No adapter for source type {source_type!r}",
            error_category=ErrorCategory.CONFIG.value,
            retry_count=0,
        )
        return ([], result)

    try:
        articles = _call_adapter_with_retry(adapter, record)
        retry_count = _call_adapter_with_retry.statistics.get("attempt_number", 1) - 1
        duration_ms = int((time.monotonic() - t0) * 1000)
        result = CollectorResult(
            source_type=source_type,
            source_key=source_key,
            status="ok",
            articles_fetched=len(articles),
            articles_saved=0,
            duration_ms=duration_ms,
            error_message=None,
            error_category=None,
            retry_count=retry_count,
        )
        return (articles, result)
    except Exception as exc:
        retry_count = _call_adapter_with_retry.statistics.get("attempt_number", 1) - 1
        duration_ms = int((time.monotonic() - t0) * 1000)
        category = categorize_error(exc)
        logger.exception("Adapter failed for %s (type=%s)", source_key, source_type)
        result = CollectorResult(
            source_type=source_type,
            source_key=source_key,
            status="error",
            articles_fetched=0,
            articles_saved=0,
            duration_ms=duration_ms,
            error_message=str(exc)[:500],
            error_category=category.value,
            retry_count=retry_count,
        )
        return ([], result)
