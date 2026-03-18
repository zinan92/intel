"""Yahoo Finance news collector using yfinance."""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from collectors.base import BaseCollector
from config import YAHOO_TICKERS, YAHOO_SEARCH_KEYWORDS

logger = logging.getLogger(__name__)


class YahooFinanceCollector(BaseCollector):
    """Collect gold-related news from Yahoo Finance via yfinance."""

    source = "yahoo_finance"

    def _fetch_ticker_news(self, symbol: str) -> list[dict[str, Any]]:
        """Fetch news for a single ticker."""
        try:
            import yfinance as yf
        except ImportError:
            logger.error("yfinance not installed — run: pip install yfinance")
            return []

        try:
            ticker = yf.Ticker(symbol)
            raw_news = ticker.news or []
        except Exception as e:
            logger.error("yfinance failed for %s: %s", symbol, e)
            return []

        articles: list[dict[str, Any]] = []
        for item in raw_news:
            # yfinance >= 0.2.40 nests data under "content"
            content = item.get("content", item)

            title = content.get("title", "")
            if not title:
                continue

            # New format: canonicalUrl.url; old format: link
            link = content.get("link", "")
            if not link:
                canonical = content.get("canonicalUrl")
                if isinstance(canonical, dict):
                    link = canonical.get("url", "")

            # New format: provider.displayName; old format: publisher
            publisher = content.get("publisher", "")
            if not publisher:
                provider = content.get("provider")
                if isinstance(provider, dict):
                    publisher = provider.get("displayName", "")

            # Parse publish time — new format: ISO string pubDate; old: epoch
            published_at = None
            pub_date_str = content.get("pubDate")
            if pub_date_str and isinstance(pub_date_str, str):
                try:
                    published_at = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass
            if not published_at:
                pub_epoch = content.get("providerPublishTime")
                if pub_epoch:
                    try:
                        published_at = datetime.fromtimestamp(pub_epoch, tz=timezone.utc)
                    except (ValueError, TypeError, OSError):
                        pass

            # Deterministic source_id
            url_hash = hashlib.md5(
                (link or title).encode()
            ).hexdigest()[:16]

            # Infer tags
            tags = ["gold", "finance", f"ticker:{symbol}"]
            tags.extend(self._infer_tags(title))

            articles.append({
                "source": self.source,
                "source_id": f"yf_{url_hash}",
                "author": publisher,
                "title": title,
                "content": content.get("summary", ""),
                "url": link,
                "tags": tags,
                "tickers": [symbol],
                "score": 0,
                "published_at": published_at,
            })

        return articles

    @staticmethod
    def _infer_tags(title: str) -> list[str]:
        """Infer tags from title keywords."""
        tags: list[str] = []
        lower = title.lower()
        tag_map = {
            "macro": ["fed", "federal reserve", "interest rate", "inflation", "cpi", "treasury", "central bank"],
            "geopolitical": ["war", "sanction", "tariff", "geopolit", "conflict", "tension"],
            "commodity": ["gold", "silver", "oil", "commodity", "precious metal"],
            "etf": ["etf", "spdr", "ishares", "gld", "iau"],
            "mining": ["mining", "miner", "newmont", "barrick", "agnico"],
        }
        for tag, keywords in tag_map.items():
            if any(kw in lower for kw in keywords):
                tags.append(tag)
        return tags

    def collect(self) -> list[dict[str, Any]]:
        """Collect news from all configured tickers + keyword search."""
        seen_ids: set[str] = set()
        all_articles: list[dict[str, Any]] = []

        # Ticker-based news
        for symbol in YAHOO_TICKERS:
            logger.info("Fetching Yahoo Finance news for %s", symbol)
            articles = self._fetch_ticker_news(symbol)
            for a in articles:
                if a["source_id"] not in seen_ids:
                    seen_ids.add(a["source_id"])
                    all_articles.append(a)
            logger.info("Got %d articles for %s", len(articles), symbol)

        # Keyword search via yfinance.Search
        for keyword in YAHOO_SEARCH_KEYWORDS:
            logger.info("Searching Yahoo Finance for '%s'", keyword)
            try:
                import yfinance as yf
                search = yf.Search(keyword, news_count=10)
                for item in search.news or []:
                    content = item.get("content", item)
                    title = content.get("title", "")
                    link = content.get("link", "")
                    if not link:
                        canonical = content.get("canonicalUrl")
                        if isinstance(canonical, dict):
                            link = canonical.get("url", "")
                    if not title:
                        continue
                    url_hash = hashlib.md5(
                        (link or title).encode()
                    ).hexdigest()[:16]
                    sid = f"yf_{url_hash}"
                    if sid in seen_ids:
                        continue
                    seen_ids.add(sid)

                    published_at = None
                    pub_date_str = content.get("pubDate")
                    if pub_date_str and isinstance(pub_date_str, str):
                        try:
                            published_at = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                        except (ValueError, TypeError):
                            pass
                    if not published_at:
                        pub_epoch = content.get("providerPublishTime")
                        if pub_epoch:
                            try:
                                published_at = datetime.fromtimestamp(pub_epoch, tz=timezone.utc)
                            except (ValueError, TypeError, OSError):
                                pass

                    publisher = content.get("publisher", "")
                    if not publisher:
                        provider = content.get("provider")
                        if isinstance(provider, dict):
                            publisher = provider.get("displayName", "")

                    all_articles.append({
                        "source": self.source,
                        "source_id": sid,
                        "author": publisher,
                        "title": title,
                        "content": content.get("summary", ""),
                        "url": link,
                        "tags": ["gold", "finance", f"search:{keyword}"] + self._infer_tags(title),
                        "tickers": [],
                        "score": 0,
                        "published_at": published_at,
                    })
            except Exception as e:
                logger.warning("Yahoo search failed for '%s': %s", keyword, e)

        logger.info("Total Yahoo Finance articles: %d", len(all_articles))
        return all_articles
