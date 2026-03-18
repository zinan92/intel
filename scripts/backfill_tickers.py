"""One-time backfill: extract tickers for existing articles.

Uses a processed marker ('[]') to distinguish unprocessed (NULL) from
processed-but-no-tickers-found. After backfill, unprocessed articles
have tickers=NULL, processed-with-tickers have tickers='["NVDA",...]',
processed-without-tickers have tickers='[]'.
"""
import json
import logging
import sys

from db.database import get_session, init_db
from db.models import Article
from tagging.tickers import extract_tickers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def backfill_tickers(batch_size: int = 500) -> int:
    """Backfill tickers for articles where tickers IS NULL."""
    init_db()
    session = get_session()
    total = 0

    try:
        while True:
            articles = (
                session.query(Article)
                .filter(Article.tickers.is_(None))
                .limit(batch_size)
                .all()
            )
            if not articles:
                break

            for article in articles:
                tickers = extract_tickers(article.title, article.content)
                # Use '[]' as "processed, no tickers" marker to avoid re-processing
                article.tickers = json.dumps(tickers) if tickers else "[]"

            session.commit()
            total += len(articles)
            logger.info("Backfilled %d articles (total: %d)", len(articles), total)

    finally:
        session.close()

    logger.info("Backfill complete: %d articles processed", total)
    return total


if __name__ == "__main__":
    batch = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    backfill_tickers(batch)
