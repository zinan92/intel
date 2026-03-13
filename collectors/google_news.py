"""Google News collector via RSS feeds (no API key required)."""

import hashlib
import logging
from datetime import datetime
from typing import Any
from urllib.parse import quote

import feedparser

from collectors.base import BaseCollector
from config import GOOGLE_NEWS_QUERIES

logger = logging.getLogger(__name__)

# Google News RSS base URL
_GNEWS_RSS_BASE = "https://news.google.com/rss/search"


class GoogleNewsCollector(BaseCollector):
    """Collect gold-related news from Google News RSS."""

    source = "google_news"

    def _fetch_query(self, query: str, hl: str = "en-US", gl: str = "US") -> list[dict[str, Any]]:
        """Fetch Google News RSS for a single query."""
        url = f"{_GNEWS_RSS_BASE}?q={quote(query)}&hl={hl}&gl={gl}&ceid={gl}:{hl[:2]}"

        try:
            feed = feedparser.parse(url)
        except Exception as e:
            logger.error("Google News RSS parse failed for '%s': %s", query, e)
            return []

        if feed.bozo and feed.bozo_exception:
            logger.warning("Google News feed issue for '%s': %s", query, feed.bozo_exception)

        articles: list[dict[str, Any]] = []
        for entry in feed.entries or []:
            title = entry.get("title", "").strip()
            if not title:
                continue

            link = entry.get("link", "")
            if not link:
                continue

            # Google News titles often end with " - Publisher Name"
            author = ""
            if " - " in title:
                parts = title.rsplit(" - ", 1)
                if len(parts) == 2:
                    author = parts[1].strip()

            # Parse published date
            published_at = None
            for date_field in ["published_parsed", "updated_parsed"]:
                date_tuple = getattr(entry, date_field, None)
                if date_tuple:
                    try:
                        published_at = datetime(*date_tuple[:6])
                        break
                    except (ValueError, TypeError):
                        continue

            # Content from summary
            content = ""
            if hasattr(entry, "summary") and entry.summary:
                content = _strip_html(entry.summary)

            url_hash = hashlib.md5(link.encode()).hexdigest()[:16]

            articles.append({
                "source": self.source,
                "source_id": f"gnews_{url_hash}",
                "author": author,
                "title": title,
                "content": content,
                "url": link,
                "tags": ["gold", "news", f"query:{query}"] + _infer_tags(title),
                "score": 0,
                "published_at": published_at,
            })

        return articles

    def collect(self) -> list[dict[str, Any]]:
        """Collect articles from all configured Google News queries."""
        seen_ids: set[str] = set()
        all_articles: list[dict[str, Any]] = []

        for query_cfg in GOOGLE_NEWS_QUERIES:
            query = query_cfg["query"]
            hl = query_cfg.get("hl", "en-US")
            gl = query_cfg.get("gl", "US")

            logger.info("Fetching Google News for '%s' (hl=%s, gl=%s)", query, hl, gl)
            articles = self._fetch_query(query, hl=hl, gl=gl)

            new = 0
            for a in articles:
                if a["source_id"] not in seen_ids:
                    seen_ids.add(a["source_id"])
                    all_articles.append(a)
                    new += 1
            logger.info("Got %d new articles for '%s'", new, query)

        logger.info("Total Google News articles: %d", len(all_articles))
        return all_articles


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    import re
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:2000]


def _infer_tags(title: str) -> list[str]:
    """Infer tags from title content."""
    tags: list[str] = []
    lower = title.lower()
    tag_map = {
        "macro": ["fed", "federal reserve", "interest rate", "inflation", "treasury", "central bank", "fomc"],
        "geopolitical": ["war", "sanction", "tariff", "geopolit", "conflict", "middle east", "china"],
        "commodity": ["gold", "silver", "oil", "commodity", "precious metal", "xau"],
        "etf": ["etf", "spdr", "gld", "iau"],
        "usd": ["dollar", "usd", "dxy", "forex"],
    }
    for tag, keywords in tag_map.items():
        if any(kw in lower for kw in keywords):
            tags.append(tag)
    return tags
