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
from triage.exposure import match_article_exposure

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    """Abstract base for all collectors."""

    source: str  # Must be set by subclasses

    def __init__(self) -> None:
        init_db()
        self.last_save_stats: dict[str, int] = {
            "saved": 0,
            "duplicates": 0,
            "errors": 0,
            "missing_timestamps": 0,
            "invalid_timestamps": 0,
        }

    @abstractmethod
    def collect(self) -> list[dict[str, Any]]:
        """Fetch articles from the source. Returns list of article dicts."""
        ...

    def save(self, articles: list[dict[str, Any]]) -> int:
        """Save articles to DB with dedup. Returns count of new articles saved."""
        saved = 0
        duplicates = 0
        errors = 0
        missing_timestamps = 0
        invalid_timestamps = 0
        for data in articles:
            timestamp_status = data.get("_timestamp_status")
            if timestamp_status == "invalid":
                invalid_timestamps += 1
            elif timestamp_status == "missing" or data.get("published_at") is None:
                missing_timestamps += 1
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
                exposure = None
                if data.get("collection_lane", "hourly") == "realtime":
                    exposure = match_article_exposure(
                        data.get("title"),
                        data.get("content"),
                        tickers,
                    )

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
                    collection_lane=data.get("collection_lane", "hourly"),
                    exposure_status=exposure.status if exposure else None,
                    exposure_assets=(
                        json.dumps(list(exposure.asset_keys), ensure_ascii=False)
                        if exposure else None
                    ),
                    exposure_reason=exposure.reason if exposure else None,
                    source_authority=data.get("source_authority"),
                    corroboration_state=data.get("corroboration_state"),
                    pin_eligibility=data.get("pin_eligibility"),
                    review_state=data.get("review_state"),
                    provider_channel_id=data.get("provider_channel_id"),
                    provider_message_id=data.get("provider_message_id"),
                    provider_edit_at=data.get("provider_edit_at"),
                    upstream_url=data.get("upstream_url"),
                    upstream_attribution=data.get("upstream_attribution"),
                    is_backfill=bool(data.get("is_backfill", False)),
                    backfill_reason=data.get("backfill_reason"),
                )
                session.add(article)
                session.commit()
                saved += 1
            except IntegrityError as exc:
                session.rollback()
                if "unique" in str(exc).lower():
                    duplicates += 1
                    logger.debug("Duplicate skipped: %s", data.get("source_id"))
                else:
                    errors += 1
                    logger.exception("Integrity error saving article %s for %s", data.get("source_id"), self.source)
            except Exception:
                session.rollback()
                errors += 1
                logger.exception("Error saving article %s for %s", data.get("source_id"), self.source)
            finally:
                session.close()

        self.last_save_stats = {
            "saved": saved,
            "duplicates": duplicates,
            "errors": errors,
            "missing_timestamps": missing_timestamps,
            "invalid_timestamps": invalid_timestamps,
        }
        logger.info(
            "[%s] Saved %d new articles (of %d fetched; duplicates=%d, errors=%d)",
            self.source,
            saved,
            len(articles),
            duplicates,
            errors,
        )
        return saved

    def run(self) -> int:
        """Collect and save. Returns count of new articles."""
        articles = self.collect()
        if not articles:
            logger.info("[%s] No articles collected", self.source)
            return 0
        return self.save(articles)
