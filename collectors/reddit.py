"""Reddit collector — pulls top daily posts from curated subreddits via RSS."""

import hashlib
import logging
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import feedparser

import config
from collectors.base import BaseCollector

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "park-intel/1.0 (qualitative data pipeline)"}


class RedditCollector(BaseCollector):
    """Collect top daily Reddit posts from subreddits in config.REDDIT_SUBREDDITS."""

    source = "reddit"

    def _fetch_subreddit(self, sub_cfg: dict[str, Any]) -> list[dict[str, Any]]:
        subreddit = sub_cfg["subreddit"]
        category = sub_cfg.get("category", "")
        url = f"https://www.reddit.com/r/{subreddit}/top/.rss?t=day&limit=25"

        logger.info("Fetching Reddit r/%s", subreddit)
        try:
            feed = feedparser.parse(url, request_headers=_HEADERS)

            if not getattr(feed, "entries", None):
                logger.warning("No entries for r/%s", subreddit)
                return []

            articles = []
            for entry in feed.entries:
                title_raw = getattr(entry, "title", "") or ""
                title = title_raw.strip() if isinstance(title_raw, str) else ""
                if not title:
                    continue

                # URL: prefer the actual post link
                post_url = getattr(entry, "link", "") or ""
                if not isinstance(post_url, str):
                    post_url = ""

                # Content: summary when available
                content = ""
                summary = getattr(entry, "summary", None)
                if isinstance(summary, str) and summary:
                    content = summary

                # Author
                author = ""
                author_detail = getattr(entry, "author_detail", None)
                if author_detail and isinstance(getattr(author_detail, "name", None), str):
                    author = author_detail.name
                if not author:
                    raw_author = getattr(entry, "author", None)
                    if isinstance(raw_author, str):
                        author = raw_author

                # Deterministic source_id: entry id > URL hash
                entry_id = getattr(entry, "id", None)
                if isinstance(entry_id, str) and entry_id:
                    source_id = "reddit_" + hashlib.sha256(entry_id.encode()).hexdigest()[:16]
                elif post_url:
                    source_id = "reddit_" + hashlib.sha256(post_url.encode()).hexdigest()[:16]
                else:
                    source_id = "reddit_" + hashlib.sha256(title.encode()).hexdigest()[:16]

                published_at: datetime | None = None
                for date_field in ("published_parsed", "updated_parsed"):
                    dt = getattr(entry, date_field, None)
                    if dt:
                        try:
                            published_at = datetime(*dt[:6])
                            break
                        except (ValueError, TypeError):
                            continue

                articles.append({
                    "source": self.source,
                    "source_id": source_id,
                    "author": author,
                    "title": title,
                    "content": content,
                    "url": post_url,
                    "tags": [category] if category else [],
                    "score": 0,
                    "published_at": published_at,
                })

            return articles

        except Exception as e:
            logger.warning("Failed to fetch r/%s: %s", subreddit, e)
            return []

    def collect(self) -> list[dict[str, Any]]:
        """Collect top daily posts from all configured subreddits."""
        all_articles: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for sub_cfg in config.REDDIT_SUBREDDITS:
            try:
                for article in self._fetch_subreddit(sub_cfg):
                    url = article.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_articles.append(article)
                    elif not url:
                        all_articles.append(article)
            except Exception as e:
                logger.error("Error processing subreddit %s: %s", sub_cfg.get("subreddit"), e)

        logger.info("Total Reddit articles collected: %d", len(all_articles))
        return all_articles
