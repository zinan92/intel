"""Backfill outcome_data for closed events with tickers."""
import asyncio
import json
import logging
import sys

from db.database import get_session, init_db
from db.models import Article
from events.models import Event, EventArticle
from bridge.quant import get_price_impacts

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def backfill_outcomes(limit: int = 50) -> int:
    init_db()
    session = get_session()
    total = 0

    try:
        events = (
            session.query(Event)
            .filter(Event.status == "closed", Event.outcome_data.is_(None))
            .order_by(Event.signal_score.desc())
            .limit(limit)
            .all()
        )

        for event in events:
            linked_ids = [
                ea.article_id for ea in
                session.query(EventArticle).filter(EventArticle.event_id == event.id).all()
            ]
            tickers = set()
            for art in session.query(Article).filter(Article.id.in_(linked_ids)).all():
                if art.tickers:
                    try:
                        for t in json.loads(art.tickers):
                            if t:
                                tickers.add(t)
                    except (json.JSONDecodeError, TypeError):
                        pass

            if not tickers:
                continue

            try:
                impacts = asyncio.run(get_price_impacts(list(tickers)[:5], event.window_start))
                if impacts:
                    from datetime import datetime
                    outcome = {
                        "tickers": {
                            pi["ticker"]: {k: pi.get(k) for k in ["price_at_event", "change_1d", "change_3d", "change_5d"]}
                            for pi in impacts
                        },
                        "captured_at": datetime.utcnow().isoformat(),
                    }
                    event.outcome_data = json.dumps(outcome)
                    total += 1
                    logger.info("Captured outcome for '%s': %d tickers", event.narrative_tag, len(impacts))
            except Exception:
                logger.warning("Failed for '%s'", event.narrative_tag, exc_info=True)

        session.commit()
    finally:
        session.close()

    logger.info("Backfill complete: %d events updated", total)
    return total


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    backfill_outcomes(limit)
