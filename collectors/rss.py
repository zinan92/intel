"""RSS collector — config-driven, reads feed list from config.RSS_FEEDS."""

import hashlib
import logging
import re
from datetime import datetime
from typing import Any

import feedparser

import config
from collectors.base import BaseCollector

logger = logging.getLogger(__name__)


class RSSCollector(BaseCollector):
    """Collect articles from RSS feeds defined in config.RSS_FEEDS."""

    source = "rss"

    def _fetch_feed(self, feed_cfg: dict[str, Any]) -> list[dict[str, Any]]:
        """Fetch articles from a single RSS feed. Returns [] on any failure."""
        name = feed_cfg["name"]
        url = feed_cfg["url"]
        category = feed_cfg.get("category", "")

        logger.info("Fetching RSS feed: %s", name)
        try:
            feed = feedparser.parse(url)

            if feed.bozo and feed.bozo_exception:
                logger.warning("Feed %s has parsing issues: %s", name, feed.bozo_exception)

            if not getattr(feed, "entries", None):
                logger.warning("No entries found in feed: %s", name)
                return []

            articles = []
            for entry in feed.entries:
                title_raw = getattr(entry, "title", "") or ""
                title = title_raw.strip() if isinstance(title_raw, str) else ""
                if not title:
                    continue

                # Prefer content > summary > description
                content = ""
                content_raw = getattr(entry, "content", None)
                if isinstance(content_raw, list) and content_raw:
                    raw = getattr(content_raw[0], "value", "")
                    content = _clean_html(raw) if isinstance(raw, str) else ""
                if not content:
                    summary = getattr(entry, "summary", None)
                    if isinstance(summary, str) and summary:
                        content = _clean_html(summary)
                if not content:
                    desc = getattr(entry, "description", None)
                    if isinstance(desc, str) and desc:
                        content = _clean_html(desc)

                article_url = getattr(entry, "link", "") or ""
                if not isinstance(article_url, str) or not article_url:
                    continue

                published_at: datetime | None = None
                for date_field in ("published_parsed", "updated_parsed"):
                    date_tuple = getattr(entry, date_field, None)
                    if date_tuple:
                        try:
                            published_at = datetime(*date_tuple[:6])
                            break
                        except (ValueError, TypeError):
                            continue

                # Deterministic source_id: hash of URL (stable across runs)
                url_hash = hashlib.sha256(article_url.encode()).hexdigest()[:16]
                source_id = f"rss_{url_hash}"

                author_raw = getattr(entry, "author", "")
                author = author_raw if isinstance(author_raw, str) else ""
                if not author:
                    raw_authors = getattr(entry, "authors", None)
                    if isinstance(raw_authors, list) and raw_authors:
                        author = raw_authors[0] if isinstance(raw_authors[0], str) else str(raw_authors[0])

                # category from config becomes the primary tag; merge with entry tags
                tags: list[str] = [category] if category else []
                for tag in getattr(entry, "tags", []) or []:
                    tag_name = tag.term if hasattr(tag, "term") else str(tag)
                    if tag_name and tag_name.lower() not in [t.lower() for t in tags]:
                        tags.append(tag_name.lower())

                articles.append({
                    "source": self.source,
                    "source_id": source_id,
                    "author": author,
                    "title": title,
                    "content": content[:2000],
                    "url": article_url,
                    "tags": tags,
                    "score": 0,
                    "published_at": published_at,
                })

            logger.info("Fetched %d articles from %s", len(articles), name)
            return articles

        except Exception as e:
            logger.warning("Failed to fetch feed %s: %s", name, e)
            return []

    def collect(self) -> list[dict[str, Any]]:
        """Collect articles from all feeds in config.RSS_FEEDS."""
        all_articles: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for feed_cfg in config.RSS_FEEDS:
            try:
                for article in self._fetch_feed(feed_cfg):
                    url = article.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_articles.append(article)
            except Exception as e:
                logger.error("Error processing feed %s: %s", feed_cfg.get("name"), e)

        logger.info("Total RSS articles collected: %d", len(all_articles))
        return all_articles


def _clean_html(text: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
