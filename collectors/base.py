"""Base collector with common dedup and save logic."""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

from db.database import get_session, init_db
from db.models import Article
from tagging import tag_article, extract_tickers

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    """Abstract base for all collectors."""

    source: str  # Must be set by subclasses

    def __init__(self) -> None:
        init_db()

    @abstractmethod
    def collect(self) -> list[dict[str, Any]]:
        """Fetch articles from the source. Returns list of article dicts."""
        ...

    def save(self, articles: list[dict[str, Any]]) -> int:
        """Save articles to DB with dedup. Returns count of new articles saved."""
        saved = 0
        for data in articles:
            session = get_session()
            try:
                # Merge collector tags with keyword-based tags
                collector_tags = data.get("tags", [])
                if isinstance(collector_tags, str):
                    try:
                        collector_tags = json.loads(collector_tags)
                    except (json.JSONDecodeError, TypeError):
                        collector_tags = []
                keyword_tags = tag_article(data.get("title"), data.get("content"))
                merged_tags = list(dict.fromkeys(collector_tags + keyword_tags))  # dedup, preserve order

                source_tickers = data.get("tickers", None)
                if isinstance(source_tickers, str):
                    try:
                        source_tickers = json.loads(source_tickers)
                    except (json.JSONDecodeError, TypeError):
                        source_tickers = None
                tickers = extract_tickers(data.get("title"), data.get("content"), source_tickers)

                article = Article(
                    source=data.get("source", self.source),
                    source_id=data.get("source_id"),
                    author=data.get("author"),
                    title=data.get("title"),
                    content=data.get("content"),
                    url=data.get("url"),
                    tags=json.dumps(merged_tags),
                    tickers=json.dumps(tickers) if tickers else None,
                    score=data.get("score", 0),
                    published_at=data.get("published_at"),
                    collected_at=datetime.utcnow(),
                )
                session.add(article)
                session.commit()
                saved += 1
            except IntegrityError:
                session.rollback()
                logger.debug("Duplicate skipped: %s", data.get("source_id"))
            except Exception:
                session.rollback()
                logger.exception("Error saving article %s for %s", data.get("source_id"), self.source)
            finally:
                session.close()

        logger.info("[%s] Saved %d new articles (of %d fetched)", self.source, saved, len(articles))
        return saved

    def run(self) -> int:
        """Collect and save. Returns count of new articles."""
        articles = self.collect()
        if not articles:
            logger.info("[%s] No articles collected", self.source)
            return 0
        return self.save(articles)
