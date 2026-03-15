"""Seed the source registry from legacy config arrays.

Reads config.ACTIVE_SOURCES and the type-specific config lists
(RSS_FEEDS, REDDIT_SUBREDDITS, etc.) and creates one SourceRegistry
record per source instance.

Normalization rules:
  - clawfeed   → social_kol
  - github     → github_trending
  - webpage_monitor → website_monitor

Idempotent: uses upsert_source, safe to run multiple times.
"""

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

import config as cfg
from sources.registry import upsert_source

logger = logging.getLogger(__name__)

# --- Name normalization ---

_SOURCE_TYPE_MAP: dict[str, str] = {
    "clawfeed": "social_kol",
    "github": "github_trending",
    "webpage_monitor": "website_monitor",
}


def _normalize_type(legacy_name: str) -> str:
    """Map legacy source name to normalized source_type."""
    return _SOURCE_TYPE_MAP.get(legacy_name, legacy_name)


# --- Key generation ---

def _slugify(text: str) -> str:
    """Convert a display name to a URL-safe slug."""
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-")


def _interval_for_type(source_type: str) -> int | None:
    """Look up interval_hours from ACTIVE_SOURCES for a normalized source type.

    Reverse-maps normalized types back to legacy names for the lookup,
    since ACTIVE_SOURCES still uses legacy names.
    """
    reverse_map = {v: k for k, v in _SOURCE_TYPE_MAP.items()}
    legacy_name = reverse_map.get(source_type, source_type)

    for entry in cfg.ACTIVE_SOURCES:
        if entry["source"] == legacy_name:
            return entry["interval_hours"]
    return None


# --- Per-type seed functions ---

def _seed_rss(session: Session, schedule_hours: int | None) -> int:
    """Seed one registry record per RSS feed."""
    count = 0
    for feed in cfg.RSS_FEEDS:
        name = feed["name"]
        key = f"rss:{_slugify(name)}"
        upsert_source(session, {
            "source_key": key,
            "source_type": "rss",
            "display_name": name,
            "category": feed.get("category"),
            "config": {"url": feed["url"], "name": name},
            "schedule_hours": schedule_hours,
        })
        count += 1
    return count


def _seed_reddit(session: Session, schedule_hours: int | None) -> int:
    """Seed one registry record per subreddit."""
    count = 0
    for sub in cfg.REDDIT_SUBREDDITS:
        subreddit = sub["subreddit"]
        key = f"reddit:{_slugify(subreddit)}"
        upsert_source(session, {
            "source_key": key,
            "source_type": "reddit",
            "display_name": f"r/{subreddit}",
            "category": sub.get("category"),
            "config": {"subreddit": subreddit},
            "schedule_hours": schedule_hours,
        })
        count += 1
    return count


def _seed_github_release(session: Session, schedule_hours: int | None) -> int:
    """Seed one registry record per monitored repo."""
    count = 0
    for repo_cfg in cfg.GITHUB_RELEASE_REPOS:
        repo = repo_cfg["repo"]
        repo_slug = _slugify(repo.replace("/", "-"))
        key = f"github_release:{repo_slug}"
        upsert_source(session, {
            "source_key": key,
            "source_type": "github_release",
            "display_name": repo,
            "category": repo_cfg.get("category"),
            "config": {"repo": repo},
            "schedule_hours": schedule_hours,
        })
        count += 1
    return count


def _seed_website_monitor(session: Session, schedule_hours: int | None) -> int:
    """Seed one registry record per webpage monitor target."""
    count = 0
    for monitor in cfg.WEBPAGE_MONITORS:
        name = monitor["name"]
        key = f"website_monitor:{_slugify(name)}"
        config: dict[str, Any] = {"type": monitor.get("type")}
        if "url" in monitor:
            config["url"] = monitor["url"]
        if "repo" in monitor:
            config["repo"] = monitor["repo"]
        if "path" in monitor:
            config["path"] = monitor["path"]
        upsert_source(session, {
            "source_key": key,
            "source_type": "website_monitor",
            "display_name": name,
            "category": monitor.get("category"),
            "config": config,
            "schedule_hours": schedule_hours,
        })
        count += 1
    return count


def _seed_social_kol(session: Session, schedule_hours: int | None) -> int:
    """Seed one registry record per KOL handle (replaces clawfeed)."""
    count = 0
    for kol in cfg.CLAWFEED_KOL_LIST:
        handle = kol["handle"]
        key = f"social_kol:{_slugify(handle)}"
        upsert_source(session, {
            "source_key": key,
            "source_type": "social_kol",
            "display_name": f"@{handle}",
            "category": kol.get("category"),
            "config": {"handle": handle},
            "schedule_hours": schedule_hours,
        })
        count += 1
    return count


def _seed_single_instance(
    session: Session,
    source_type: str,
    display_name: str,
    category: str | None,
    schedule_hours: int | None,
    instance_config: dict[str, Any],
) -> None:
    """Seed a single-instance source (hackernews, xueqiu, etc.)."""
    key = f"{source_type}:main"
    upsert_source(session, {
        "source_key": key,
        "source_type": source_type,
        "display_name": display_name,
        "category": category,
        "config": instance_config,
        "schedule_hours": schedule_hours,
    })


# --- Main entry point ---

def seed_source_registry(session: Session) -> int:
    """Populate the source registry from legacy config. Idempotent.

    Returns the total number of source instances seeded.
    """
    total = 0

    # Per-instance sources
    total += _seed_rss(session, _interval_for_type("rss"))
    total += _seed_reddit(session, _interval_for_type("reddit"))
    total += _seed_github_release(session, _interval_for_type("github_release"))
    total += _seed_website_monitor(session, _interval_for_type("website_monitor"))
    total += _seed_social_kol(session, _interval_for_type("social_kol"))

    # Single-instance sources
    _seed_single_instance(
        session, "hackernews", "Hacker News",
        category="frontier-tech",
        schedule_hours=_interval_for_type("hackernews"),
        instance_config={
            "min_score": cfg.HN_MIN_SCORE,
            "hits_per_page": cfg.HN_HITS_PER_PAGE,
            "search_keywords": cfg.HN_SEARCH_KEYWORDS,
        },
    )
    total += 1

    _seed_single_instance(
        session, "xueqiu", "Xueqiu KOL Feed",
        category="cn-finance",
        schedule_hours=_interval_for_type("xueqiu"),
        instance_config={"kol_ids": cfg.XUEQIU_KOL_IDS},
    )
    total += 1

    _seed_single_instance(
        session, "yahoo_finance", "Yahoo Finance",
        category="macro",
        schedule_hours=_interval_for_type("yahoo_finance"),
        instance_config={
            "tickers": cfg.YAHOO_TICKERS,
            "search_keywords": cfg.YAHOO_SEARCH_KEYWORDS,
        },
    )
    total += 1

    _seed_single_instance(
        session, "google_news", "Google News",
        category="macro",
        schedule_hours=_interval_for_type("google_news"),
        instance_config={"queries": cfg.GOOGLE_NEWS_QUERIES},
    )
    total += 1

    _seed_single_instance(
        session, "github_trending", "GitHub Trending",
        category="frontier-tech",
        schedule_hours=_interval_for_type("github_trending"),
        instance_config={},
    )
    total += 1

    logger.info("Source registry seeded: %d instances", total)
    return total
