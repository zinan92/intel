"""Webpage monitor — scrapes no-RSS pages and monitors GitHub commits for doc changes."""

import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

import config
from collectors.base import BaseCollector

logger = logging.getLogger(__name__)

_TIMEOUT = 15
_STATE_FILE = Path(__file__).parent.parent / "data" / "webpage_monitor_state.json"
_GITHUB_COMMITS_URL = "https://api.github.com/repos/{repo}/commits?path={path}&per_page=5"


def _load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"seen_urls": {}, "last_seen_commit": {}}


def _save_state(path: Path, state: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2))
    except OSError as e:
        logger.warning("Could not save webpage monitor state: %s", e)


def _slug_to_title(slug: str) -> str:
    """Convert a URL path slug to a readable title."""
    name = slug.rstrip("/").split("/")[-1]
    return name.replace("-", " ").replace("_", " ").title()


class WebpageMonitorCollector(BaseCollector):
    """Monitor high-value pages without RSS feeds."""

    source = "website_monitor"

    def __init__(self, state_path: Path | None = None) -> None:
        super().__init__()
        self._state_path = state_path or _STATE_FILE

    def _scrape_blog(self, monitor: dict[str, Any], state: dict) -> list[dict[str, Any]]:
        """Scrape blog index and return new articles not seen before."""
        name = monitor["name"]
        url = monitor["url"]
        category = monitor.get("category", "")

        seen = set(state.get("seen_urls", {}).get(name, []))

        try:
            from html.parser import HTMLParser

            resp = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": "park-intel/1.0"})
            resp.raise_for_status()
            html = resp.text

            base_parsed = urlparse(url)
            blog_path = base_parsed.path  # e.g. /blog/

            # Extract <a href> links that are deeper than the blog index
            href_pattern = re.compile(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
            articles: list[dict[str, Any]] = []
            new_seen: list[str] = []

            for match in href_pattern.finditer(html):
                href = match.group(1).strip()
                anchor_text = re.sub(r"<[^>]+>", "", match.group(2)).strip()

                # Normalize to absolute URL
                abs_url = urljoin(url, href)
                parsed = urlparse(abs_url)

                # Only keep links on the same host, under the blog path, deeper than index
                if parsed.netloc != base_parsed.netloc:
                    continue
                if not parsed.path.startswith(blog_path):
                    continue
                if parsed.path == blog_path or parsed.path.rstrip("/") == blog_path.rstrip("/"):
                    continue

                canonical = abs_url.split("?")[0].split("#")[0]

                if canonical in seen:
                    continue

                title = anchor_text if anchor_text else _slug_to_title(parsed.path)
                if not title:
                    title = canonical

                new_seen.append(canonical)
                articles.append({
                    "source": self.source,
                    "source_id": "webpage_" + _hash(canonical),
                    "author": "Anthropic",
                    "title": title,
                    "content": "",
                    "url": canonical,
                    "tags": [category] if category else [],
                    "score": 0,
                    "published_at": None,
                })

            # Update state with all new URLs found
            if new_seen:
                state.setdefault("seen_urls", {})[name] = list(seen | set(new_seen))

            return articles

        except Exception as e:
            logger.warning("Failed to scrape %s (%s): %s", name, url, e)
            return []

    def _monitor_github_commits(self, monitor: dict[str, Any], state: dict) -> list[dict[str, Any]]:
        """Fetch recent commits for a repo path; yield only unseen SHAs."""
        repo = monitor["repo"]
        path = monitor.get("path", "")
        category = monitor.get("category", "")
        state_key = f"{repo}:{path}"

        last_sha = state.get("last_seen_commit", {}).get(state_key)

        headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
        token = config.GITHUB_TOKEN
        if token:
            headers["Authorization"] = f"Bearer {token}"

        api_url = _GITHUB_COMMITS_URL.format(repo=repo, path=path)
        try:
            resp = requests.get(api_url, headers=headers, timeout=_TIMEOUT)
            resp.raise_for_status()
            commits = resp.json()
            if not isinstance(commits, list):
                return []

            articles: list[dict[str, Any]] = []
            newest_sha: str | None = None

            for commit in commits:
                sha = commit.get("sha", "")
                if not sha:
                    continue
                if newest_sha is None:
                    newest_sha = sha
                if sha == last_sha:
                    break

                message = (commit.get("commit") or {}).get("message", "").split("\n")[0]
                html_url = commit.get("html_url", "")
                committer = (
                    (commit.get("author") or {}).get("login")
                    or (commit.get("commit") or {}).get("author", {}).get("name", "")
                )

                articles.append({
                    "source": self.source,
                    "source_id": "webpage_commit_" + sha[:16],
                    "author": committer,
                    "title": f"OpenClaw Docs: {message}",
                    "content": "",
                    "url": html_url,
                    "tags": [category] if category else [],
                    "score": 0,
                    "published_at": None,
                })

            if newest_sha:
                state.setdefault("last_seen_commit", {})[state_key] = newest_sha

            return articles

        except Exception as e:
            logger.warning("Failed to fetch commits for %s path=%s: %s", repo, path, e)
            return []

    def collect(self) -> list[dict[str, Any]]:
        """Run all configured webpage monitors."""
        state = _load_state(self._state_path)
        all_articles: list[dict[str, Any]] = []

        for monitor in config.WEBPAGE_MONITORS:
            monitor_type = monitor.get("type")
            try:
                if monitor_type == "scrape":
                    articles = self._scrape_blog(monitor, state)
                elif monitor_type == "github_commits":
                    articles = self._monitor_github_commits(monitor, state)
                else:
                    logger.warning("Unknown monitor type: %s", monitor_type)
                    articles = []
                all_articles.extend(articles)
            except Exception as e:
                logger.error("Error in webpage monitor %s: %s", monitor.get("name"), e)

        _save_state(self._state_path, state)
        logger.info("Webpage monitor collected %d items", len(all_articles))
        return all_articles


def _hash(value: str) -> str:
    import hashlib
    return hashlib.sha256(value.encode()).hexdigest()[:16]
