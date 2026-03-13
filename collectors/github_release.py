"""GitHub Release collector — monitors release events from pinned repos."""

import hashlib
import logging
from datetime import datetime
from typing import Any

import requests

import config
from collectors.base import BaseCollector

logger = logging.getLogger(__name__)

_RELEASES_URL = "https://api.github.com/repos/{repo}/releases?per_page=5"
_TIMEOUT = 15


class GitHubReleaseCollector(BaseCollector):
    """Collect latest release events from repos in config.GITHUB_RELEASE_REPOS."""

    source = "github_release"

    def _fetch_repo(self, repo_cfg: dict[str, Any]) -> list[dict[str, Any]]:
        repo = repo_cfg["repo"]
        category = repo_cfg.get("category", "")
        url = _RELEASES_URL.format(repo=repo)

        headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
        token = config.GITHUB_TOKEN
        if token:
            headers["Authorization"] = f"Bearer {token}"

        logger.info("Fetching GitHub releases for %s", repo)
        try:
            resp = requests.get(url, headers=headers, timeout=_TIMEOUT)
            if resp.status_code == 404:
                logger.warning("Repo %s not found (404)", repo)
                return []
            resp.raise_for_status()
            releases = resp.json()
            if not isinstance(releases, list):
                logger.warning("Unexpected releases response for %s", repo)
                return []

            articles: list[dict[str, Any]] = []
            repo_name = repo.split("/")[-1]
            for rel in releases:
                tag_name = rel.get("tag_name", "")
                title = f"{repo_name} {tag_name}"
                body = rel.get("body") or ""
                content = body[:1000]
                html_url = rel.get("html_url", "")
                author = (rel.get("author") or {}).get("login", "")
                rel_id = rel.get("id")

                if rel_id:
                    source_id = f"github_release_{rel_id}"
                else:
                    source_id = "github_release_" + hashlib.sha256(
                        f"{repo}_{tag_name}".encode()
                    ).hexdigest()[:16]

                published_at: datetime | None = None
                published_raw = rel.get("published_at") or rel.get("created_at")
                if published_raw:
                    try:
                        published_at = datetime.fromisoformat(
                            published_raw.replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                    except (ValueError, TypeError):
                        pass

                articles.append({
                    "source": self.source,
                    "source_id": source_id,
                    "author": author,
                    "title": title,
                    "content": content,
                    "url": html_url,
                    "tags": [category] if category else [],
                    "score": 0,
                    "published_at": published_at,
                })

            return articles

        except requests.RequestException as e:
            logger.warning("Failed to fetch releases for %s: %s", repo, e)
            return []

    def collect(self) -> list[dict[str, Any]]:
        """Collect releases from all repos in config.GITHUB_RELEASE_REPOS."""
        all_articles: list[dict[str, Any]] = []
        for repo_cfg in config.GITHUB_RELEASE_REPOS:
            try:
                all_articles.extend(self._fetch_repo(repo_cfg))
            except Exception as e:
                logger.error("Error processing repo %s: %s", repo_cfg.get("repo"), e)
        logger.info("Total GitHub releases collected: %d", len(all_articles))
        return all_articles
