"""ClawFeed collector — replaces the legacy Twitter/bird collector."""

import hashlib
import json
import logging
import shutil
import subprocess
from datetime import datetime
from typing import Any

from collectors.base import BaseCollector

logger = logging.getLogger(__name__)

_CLAWFEED_CMD = ["clawfeed", "export", "--format", "json", "--limit", "20"]


class ClawFeedCollector(BaseCollector):
    """Collect curated KOL content via the clawfeed CLI."""

    source = "clawfeed"

    def __init__(self) -> None:
        super().__init__()
        self._cli_path = shutil.which("clawfeed") or shutil.which(
            "clawfeed", path="/opt/homebrew/bin:/usr/local/bin"
        )

    def collect(self) -> list[dict[str, Any]]:
        if not self._cli_path:
            logger.warning("ClawFeed CLI not available - skipping")
            return []
        return self._fetch_via_cli()

    def _fetch_via_cli(self) -> list[dict[str, Any]]:
        try:
            result = subprocess.run(
                [self._cli_path, "export", "--format", "json", "--limit", "20"],
                capture_output=True,
                timeout=60,
            )
            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")

            if result.returncode != 0:
                logger.warning("clawfeed export failed (rc=%d): %s", result.returncode, stderr.strip())
                return []

            raw = json.loads(stdout) if stdout.strip() else []
            if isinstance(raw, dict):
                raw = raw.get("data", raw.get("items", [raw]))
            if not isinstance(raw, list):
                logger.warning("Unexpected clawfeed output structure")
                return []

            articles: list[dict[str, Any]] = []
            for item in raw:
                article = self._map_item(item)
                if article:
                    articles.append(article)

            logger.info("ClawFeed: collected %d items", len(articles))
            return articles

        except subprocess.TimeoutExpired:
            logger.warning("clawfeed export timed out")
            return []
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to parse clawfeed output: %s", e)
            return []

    def _map_item(self, item: dict[str, Any]) -> dict[str, Any] | None:
        title = item.get("headline") or item.get("title") or ""
        content = item.get("summary") or item.get("body") or item.get("content") or ""
        author = item.get("handle") or item.get("author") or item.get("kol") or ""
        url = item.get("tweet_url") or item.get("url") or item.get("source_url") or ""

        if not content and not title:
            logger.warning("ClawFeed item missing both content and title — skipping")
            return None

        source_id = self._make_source_id(item, url, title, author)

        return {
            "source": self.source,
            "source_id": source_id,
            "author": author,
            "title": title or None,
            "content": content,
            "url": url,
            "tags": [],
            "score": 0,
            "published_at": None,
        }

    @staticmethod
    def _make_source_id(item: dict[str, Any], url: str, title: str, author: str) -> str:
        item_id = item.get("id")
        if item_id:
            return f"clawfeed_{item_id}"
        if url:
            return "clawfeed_" + hashlib.sha256(url.encode()).hexdigest()[:16]
        return "clawfeed_" + hashlib.sha256((title + author).encode()).hexdigest()[:16]
