"""Hacker News collector using Algolia API."""

import logging
import time
from datetime import datetime
from typing import Any

import requests

from collectors.base import BaseCollector
from config import HN_API_BASE, HN_HITS_PER_PAGE, HN_MIN_SCORE, HN_SEARCH_KEYWORDS

logger = logging.getLogger(__name__)


class HackerNewsCollector(BaseCollector):
    """Collect top stories and keyword-matched stories from Hacker News."""

    source = "hackernews"

    def _fetch_stories(self, query: str | None = None) -> list[dict[str, Any]]:
        """Fetch stories from HN Algolia API, limited to last 48 hours."""
        cutoff = int(time.time()) - 48 * 3600  # last 48 hours
        params: dict[str, Any] = {
            "tags": "story",
            "hitsPerPage": HN_HITS_PER_PAGE,
            "numericFilters": f"created_at_i>{cutoff}",
        }
        if query:
            params["query"] = query

        url = f"{HN_API_BASE}/search_by_date" if not query else f"{HN_API_BASE}/search"
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.error("HN API request failed: %s", e)
            return []

        articles: list[dict[str, Any]] = []
        for hit in data.get("hits", []):
            score = hit.get("points", 0) or 0
            if score < HN_MIN_SCORE:
                continue

            created = hit.get("created_at")
            published_at = None
            if created:
                try:
                    published_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            story_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"

            articles.append({
                "source": self.source,
                "source_id": f"hn_{hit.get('objectID', '')}",
                "author": hit.get("author"),
                "title": hit.get("title"),
                "content": hit.get("story_text") or hit.get("comment_text"),
                "url": story_url,
                "tags": self._infer_tags(hit.get("title", ""), query),
                "score": score,
                "published_at": published_at,
            })

        return articles

    @staticmethod
    def _infer_tags(title: str, query: str | None) -> list[str]:
        """Infer basic tags from title and query."""
        tags: list[str] = []
        title_lower = title.lower()
        tag_keywords = {
            "ai": ["ai", "artificial intelligence", "llm", "gpt", "machine learning", "deep learning"],
            "crypto": ["crypto", "bitcoin", "ethereum", "blockchain", "web3"],
            "trading": ["trading", "market", "stock", "hedge fund"],
            "chips": ["chip", "semiconductor", "nvidia", "gpu", "tsmc"],
        }
        for tag, keywords in tag_keywords.items():
            if any(kw in title_lower for kw in keywords):
                tags.append(tag)
        if query and query.lower() not in [t.lower() for t in tags]:
            tags.append(query.lower())
        return tags

    def collect(self) -> list[dict[str, Any]]:
        """Collect top stories + keyword searches."""
        seen_ids: set[str] = set()
        all_articles: list[dict[str, Any]] = []

        # Top stories (front page)
        logger.info("Fetching HN top stories")
        top = self._fetch_stories()
        for a in top:
            if a["source_id"] not in seen_ids:
                seen_ids.add(a["source_id"])
                all_articles.append(a)
        logger.info("Got %d top stories (score >= %d)", len(all_articles), HN_MIN_SCORE)

        # Keyword searches
        for keyword in HN_SEARCH_KEYWORDS:
            logger.info("Searching HN for '%s'", keyword)
            results = self._fetch_stories(query=keyword)
            new = 0
            for a in results:
                if a["source_id"] not in seen_ids:
                    seen_ids.add(a["source_id"])
                    all_articles.append(a)
                    new += 1
            logger.info("Got %d new articles for '%s'", new, keyword)

        return all_articles
