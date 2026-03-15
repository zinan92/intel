"""Seed the source registry from legacy config arrays.

Reads config.ACTIVE_SOURCES and the type-specific config lists
(RSS_FEEDS, REDDIT_SUBREDDITS, etc.) and creates one SourceRegistry
record per source instance.

Normalization rules:
  - clawfeed   → social_kol
  - github     → github_trending
  - webpage_monitor → website_monitor

Insert-only: existing rows are never overwritten, so DB-side edits
to priority, schedule, active state, or config survive restarts.
"""

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

import config as cfg
from sources.registry import get_source_by_key, upsert_source

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


# --- Insert-only helper ---

def _insert_if_missing(session: Session, payload: dict[str, Any]) -> bool:
    """Insert a source record only if the key does not already exist.

    Returns True if a new row was inserted, False if skipped.
    This ensures DB-side edits survive app restarts.
    """
    if get_source_by_key(session, payload["source_key"]) is not None:
        return False
    upsert_source(session, payload)
    return True


# --- Per-type seed functions ---

def _seed_rss(session: Session, schedule_hours: int | None) -> int:
    """Seed one registry record per RSS feed."""
    count = 0
    for feed in cfg.RSS_FEEDS:
        name = feed["name"]
        key = f"rss:{_slugify(name)}"
        if _insert_if_missing(session, {
            "source_key": key,
            "source_type": "rss",
            "display_name": name,
            "category": feed.get("category"),
            "config": {"url": feed["url"], "name": name},
            "schedule_hours": schedule_hours,
        }):
            count += 1
    return count


def _seed_reddit(session: Session, schedule_hours: int | None) -> int:
    """Seed one registry record per subreddit."""
    count = 0
    for sub in cfg.REDDIT_SUBREDDITS:
        subreddit = sub["subreddit"]
        key = f"reddit:{_slugify(subreddit)}"
        if _insert_if_missing(session, {
            "source_key": key,
            "source_type": "reddit",
            "display_name": f"r/{subreddit}",
            "category": sub.get("category"),
            "config": {"subreddit": subreddit},
            "schedule_hours": schedule_hours,
        }):
            count += 1
    return count


def _seed_github_release(session: Session, schedule_hours: int | None) -> int:
    """Seed one registry record per monitored repo."""
    count = 0
    for repo_cfg in cfg.GITHUB_RELEASE_REPOS:
        repo = repo_cfg["repo"]
        repo_slug = _slugify(repo.replace("/", "-"))
        key = f"github_release:{repo_slug}"
        if _insert_if_missing(session, {
            "source_key": key,
            "source_type": "github_release",
            "display_name": repo,
            "category": repo_cfg.get("category"),
            "config": {"repo": repo},
            "schedule_hours": schedule_hours,
        }):
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
        if _insert_if_missing(session, {
            "source_key": key,
            "source_type": "website_monitor",
            "display_name": name,
            "category": monitor.get("category"),
            "config": config,
            "schedule_hours": schedule_hours,
        }):
            count += 1
    return count


def _seed_social_kol(session: Session, schedule_hours: int | None) -> int:
    """Seed one registry record for the curated social KOL stream (replaces clawfeed).

    The KOL handle list is stored in config, not as individual source rows.
    social_kol is a curated stream/channel — one source instance, not one per handle.
    """
    handles = [kol["handle"] for kol in cfg.CLAWFEED_KOL_LIST]
    categories = list({kol.get("category", "") for kol in cfg.CLAWFEED_KOL_LIST} - {""})
    if _insert_if_missing(session, {
        "source_key": "social_kol:curated-stream",
        "source_type": "social_kol",
        "display_name": "Curated Social KOL Stream",
        "category": "mixed" if len(categories) > 1 else (categories[0] if categories else None),
        "config": {"handles": handles},
        "schedule_hours": schedule_hours,
    }):
        return 1
    return 0


def _seed_single_instance(
    session: Session,
    source_type: str,
    display_name: str,
    category: str | None,
    schedule_hours: int | None,
    instance_config: dict[str, Any],
) -> bool:
    """Seed a single-instance source (hackernews, xueqiu, etc.).

    Returns True if inserted, False if already existed.
    """
    key = f"{source_type}:main"
    return _insert_if_missing(session, {
        "source_key": key,
        "source_type": source_type,
        "display_name": display_name,
        "category": category,
        "config": instance_config,
        "schedule_hours": schedule_hours,
    })


# --- Main entry point ---

def seed_source_registry(session: Session) -> int:
    """Populate the source registry from legacy config. Insert-only.

    Existing rows are never overwritten — DB-side edits to priority,
    schedule, active state, or config survive restarts.

    Returns the number of NEW source instances inserted (0 on subsequent runs).
    """
    inserted = 0

    # Per-instance sources
    inserted += _seed_rss(session, _interval_for_type("rss"))
    inserted += _seed_reddit(session, _interval_for_type("reddit"))
    inserted += _seed_github_release(session, _interval_for_type("github_release"))
    inserted += _seed_website_monitor(session, _interval_for_type("website_monitor"))
    inserted += _seed_social_kol(session, _interval_for_type("social_kol"))

    # Single-instance sources
    for src_type, name, cat, cfg_data in [
        ("hackernews", "Hacker News", "frontier-tech", {
            "min_score": cfg.HN_MIN_SCORE,
            "hits_per_page": cfg.HN_HITS_PER_PAGE,
            "search_keywords": cfg.HN_SEARCH_KEYWORDS,
        }),
        ("xueqiu", "Xueqiu KOL Feed", "cn-finance", {
            "kol_ids": cfg.XUEQIU_KOL_IDS,
        }),
        ("yahoo_finance", "Yahoo Finance", "macro", {
            "tickers": cfg.YAHOO_TICKERS,
            "search_keywords": cfg.YAHOO_SEARCH_KEYWORDS,
        }),
        ("google_news", "Google News", "macro", {
            "queries": cfg.GOOGLE_NEWS_QUERIES,
        }),
        ("github_trending", "GitHub Trending", "frontier-tech", {}),
    ]:
        if _seed_single_instance(
            session, src_type, name,
            category=cat,
            schedule_hours=_interval_for_type(src_type),
            instance_config=cfg_data,
        ):
            inserted += 1

    if inserted > 0:
        logger.info("Source registry: inserted %d new instances", inserted)
    else:
        logger.debug("Source registry: no new instances to seed")
    return inserted
