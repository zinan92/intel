#!/usr/bin/env python3
"""Run LLM tagger on articles that haven't been scored yet.

Uses Claude Code CLI (claude -p) — no API key needed.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func

from db.database import get_session, init_db
from db.models import Article
from tagging.llm import LLMTagger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_tagger(
    backfill: bool = False,
    limit: int = 0,
    prefiltered: bool = False,
    batch_size: int = 10,
) -> None:
    """Run the LLM tagger programmatically (no argparse). Called by scheduler and main()."""
    if not backfill and limit <= 0 and not prefiltered:
        raise ValueError("Specify backfill=True, limit>0, or prefiltered=True")

    init_db()
    session = get_session()
    tagger = LLMTagger(batch_size=batch_size)

    try:
        if prefiltered:
            from sqlalchemy import text as sa_text
            rows = session.execute(sa_text("""
                SELECT a.id FROM articles a
                JOIN prefiltered_articles p ON a.id = p.article_id
                WHERE a.relevance_score IS NULL
                ORDER BY a.collected_at DESC
            """)).fetchall()
            article_ids = [r[0] for r in rows]
            articles = session.query(Article).filter(Article.id.in_(article_ids)).order_by(Article.collected_at.desc()).all() if article_ids else []
        else:
            query = session.query(Article).filter(Article.relevance_score.is_(None))
            if backfill:
                articles = query.order_by(Article.collected_at.desc()).all()
            else:
                articles = query.order_by(Article.collected_at.desc()).limit(limit).all()

        logger.info("Found %d unscored articles to process", len(articles))

        if not articles:
            return

        scored = 0
        for i in range(0, len(articles), batch_size):
            batch = articles[i : i + batch_size]
            batch_dicts = [
                {"id": a.id, "title": a.title, "content": a.content, "source": a.source}
                for a in batch
            ]

            results = tagger.tag_batch(batch_dicts)
            if not results:
                logger.warning("Empty results for batch %d, stopping", i // batch_size + 1)
                break

            result_map = {r["id"]: r for r in results}
            for a in batch:
                if a.id in result_map:
                    r = result_map[a.id]
                    a.relevance_score = r["relevance_score"]
                    a.narrative_tags = json.dumps(r["narrative_tags"])
                    scored += 1

            session.commit()
            logger.info(
                "Batch %d: scored %d/%d articles (%d batches total)",
                i // batch_size + 1,
                len(results),
                len(batch),
                tagger.batches_processed,
            )

        logger.info("Done. Total scored: %d", scored)

        rows = session.execute(
            session.query(Article.relevance_score, func.count(Article.id))
            .group_by(Article.relevance_score)
            .statement
        ).all()
        for score, count in sorted(rows, key=lambda x: (x[0] is None, x[0])):
            label = str(score) if score is not None else "unscored"
            logger.info("  relevance_score=%s: %d articles", label, count)

    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM tagger on unscored articles")
    parser.add_argument("--backfill", action="store_true", help="Process all unscored articles")
    parser.add_argument("--limit", type=int, default=0, help="Process N most recent unscored articles")
    parser.add_argument("--prefiltered", action="store_true", help="Only score prefiltered articles")
    parser.add_argument("--batch-size", type=int, default=10, help="Articles per LLM call")
    args = parser.parse_args()

    if not args.backfill and args.limit <= 0 and not args.prefiltered:
        parser.error("Specify --backfill, --limit N, or --prefiltered")

    run_tagger(
        backfill=args.backfill,
        limit=args.limit,
        prefiltered=args.prefiltered,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
