"""Source URL resolver — classifies a URL or reference into a normalized source type.

Internal-only tool for source onboarding. Not exposed to end users in v1.

Given a candidate URL, returns:
  - source_type: normalized type (rss, reddit, hackernews, etc.)
  - display_name: human-readable label
  - config: type-specific configuration dict
"""

import re
from typing import Any
from urllib.parse import urlparse


def resolve_source(url_or_ref: str) -> dict[str, Any]:
    """Classify a URL or reference into a normalized source type.

    Returns a dict with source_type, display_name, and config.
    Falls back to website_monitor for unrecognized URLs.
    """
    url = url_or_ref.strip()
    if not url:
        return _website_monitor_result(url)

    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path

    # Reddit
    if _is_reddit(host):
        return _resolve_reddit(path)

    # Hacker News
    if host in ("news.ycombinator.com", "hn.algolia.com"):
        return {
            "source_type": "hackernews",
            "display_name": "Hacker News",
            "config": {},
        }

    # GitHub
    if host in ("github.com", "www.github.com"):
        return _resolve_github(path)

    # RSS/Atom detection by URL pattern
    if _looks_like_rss(path, url):
        return _rss_result(url, parsed)

    # Default: website_monitor
    return _website_monitor_result(url)


def _is_reddit(host: str) -> bool:
    return host in ("reddit.com", "www.reddit.com", "old.reddit.com")


def _resolve_reddit(path: str) -> dict[str, Any]:
    """Extract subreddit from a Reddit path."""
    match = re.match(r"/r/([^/]+)", path)
    if match:
        subreddit = match.group(1)
        return {
            "source_type": "reddit",
            "display_name": f"r/{subreddit}",
            "config": {"subreddit": subreddit},
        }
    return {
        "source_type": "reddit",
        "display_name": "Reddit",
        "config": {},
    }


def _resolve_github(path: str) -> dict[str, Any]:
    """Classify GitHub URLs: trending, repo releases, or website_monitor.

    Only URLs with an explicit /releases path segment are classified as
    github_release. Generic /owner/repo URLs fall through to website_monitor
    to avoid creating false release monitors from ordinary repo links.
    """
    # /trending or /trending/python
    if re.match(r"/trending(/|$)", path):
        return {
            "source_type": "github_trending",
            "display_name": "GitHub Trending",
            "config": {},
        }

    # /owner/repo/releases — explicit release endpoint only
    release_match = re.match(r"/([^/]+)/([^/]+)/releases", path)
    if release_match:
        owner = release_match.group(1)
        repo_name = release_match.group(2)
        repo = f"{owner}/{repo_name}"
        return {
            "source_type": "github_release",
            "display_name": repo,
            "config": {"repo": repo},
        }

    # Generic /owner/repo — not enough signal to classify as release monitor
    return _website_monitor_result(f"https://github.com{path}")


_RSS_PATTERNS = re.compile(
    r"(\.xml|\.rss|/feed|/rss|/atom|\.atom)(/|$)",
    re.IGNORECASE,
)


def _looks_like_rss(path: str, url: str) -> bool:
    """Heuristic: does this URL look like an RSS/Atom feed?"""
    return bool(_RSS_PATTERNS.search(path))


def _rss_result(url: str, parsed: Any) -> dict[str, Any]:
    host = parsed.netloc.replace("www.", "")
    return {
        "source_type": "rss",
        "display_name": host,
        "config": {"url": url},
    }


def _website_monitor_result(url: str) -> dict[str, Any]:
    return {
        "source_type": "website_monitor",
        "display_name": url or "Unknown",
        "config": {"url": url} if url else {},
    }
