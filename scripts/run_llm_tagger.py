#!/usr/bin/env python3
"""Run LLM tagger on articles that haven't been scored yet.

Uses the DeepSeek API with a file-based credential.
"""

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func

from db.database import get_session, init_db
from db.models import Article, CollectorRun
from tagging.llm import LLMTagger, TaggingError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class TaggerRunError(RuntimeError):
    """Raised when pending articles cannot be scored by either provider."""


@dataclass(frozen=True)
class TaggerRunResult:
    status: str
    attempted: int
    scored: int
    provider: str | None
    fallback_reason: str | None


def _record_run(
    session,
    *,
    status: str,
    attempted: int,
    scored: int,
    duration_ms: int,
    provider: str | None,
    fallback_reason: str | None,
    error_message: str | None = None,
) -> None:
    session.add(CollectorRun(
        source_type="llm_tagger",
        source_key="finance:article-scoring",
        status=status,
        articles_fetched=attempted,
        articles_saved=scored,
        articles_failed=max(attempted - scored, 0),
        duration_ms=duration_ms,
        error_message=error_message,
        error_category="provider" if error_message else None,
        provider=provider,
        fallback_reason=fallback_reason,
        retry_count=0,
        completed_at=datetime.utcnow(),
    ))
    session.commit()


def run_tagger(
    backfill: bool = False,
    limit: int = 0,
    prefiltered: bool = False,
    batch_size: int = 10,
    include_realtime: bool = False,
    tagger: LLMTagger | None = None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> TaggerRunResult:
    """Run the LLM tagger programmatically (no argparse). Called by scheduler and main()."""
    if not backfill and limit <= 0 and not prefiltered:
        raise ValueError("Specify backfill=True, limit>0, or prefiltered=True")
    if (window_start is None) != (window_end is None):
        raise ValueError("window_start and window_end must be supplied together")
    if prefiltered and window_start is not None:
        raise ValueError("explicit windows cannot be combined with prefiltered mode")

    init_db()
    session = get_session()
    tagger = tagger or LLMTagger(batch_size=batch_size)
    started = time.monotonic()

    try:
        if prefiltered:
            from sqlalchemy import text as sa_text
            lane_filter = "" if include_realtime else (
                " AND (a.collection_lane IS NULL OR a.collection_lane = 'hourly')"
            )
            rows = session.execute(sa_text(f"""
                SELECT a.id FROM articles a
                JOIN prefiltered_articles p ON a.id = p.article_id
                WHERE a.relevance_score IS NULL{lane_filter}
                ORDER BY a.collected_at DESC
            """)).fetchall()
            article_ids = [r[0] for r in rows]
            articles = (
                session.query(Article)
                .filter(Article.id.in_(article_ids))
                .order_by(Article.collected_at.desc())
                .all()
                if article_ids
                else []
            )
        else:
            query = session.query(Article).filter(Article.relevance_score.is_(None))
            if not include_realtime:
                query = query.filter(Article.collection_lane == "hourly")
            if window_start is not None and window_end is not None:
                query = query.filter(
                    Article.collected_at >= window_start,
                    Article.collected_at < window_end,
                    (Article.published_at.is_(None)) | (Article.published_at >= window_start),
                    (Article.published_at.is_(None)) | (Article.published_at < window_end),
                )
            if backfill:
                articles = query.order_by(Article.collected_at.desc()).all()
            else:
                articles = query.order_by(Article.collected_at.desc()).limit(limit).all()

        logger.info("Found %d unscored articles to process", len(articles))

        if not articles:
            result = TaggerRunResult("ok", 0, 0, None, None)
            _record_run(
                session,
                status=result.status,
                attempted=0,
                scored=0,
                duration_ms=round((time.monotonic() - started) * 1000),
                provider=None,
                fallback_reason=None,
            )
            return result

        scored = 0
        providers: set[str] = set()
        fallback_reasons: set[str] = set()
        for i in range(0, len(articles), batch_size):
            batch = articles[i : i + batch_size]
            batch_dicts = [
                {"id": a.id, "title": a.title, "content": a.content, "source": a.source}
                for a in batch
            ]

            try:
                batch_result = tagger.tag_batch(batch_dicts)
            except TaggingError as exc:
                message = str(exc)
                _record_run(
                    session,
                    status="error",
                    attempted=len(articles),
                    scored=scored,
                    duration_ms=round((time.monotonic() - started) * 1000),
                    provider=",".join(sorted(providers)) or None,
                    fallback_reason=",".join(sorted(fallback_reasons)) or None,
                    error_message=message,
                )
                raise TaggerRunError(message) from exc

            results = batch_result.items
            providers.add(batch_result.provider)
            if batch_result.fallback_reason:
                fallback_reasons.add(batch_result.fallback_reason)

            result_map = {r["id"]: r for r in results}
            for a in batch:
                if a.id in result_map:
                    r = result_map[a.id]
                    a.relevance_score = r["relevance_score"]
                    a.narrative_tags = json.dumps(r["narrative_tags"])
                    a.relevance_provider = batch_result.provider
                    a.relevance_scored_at = datetime.utcnow()
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

        provider = ",".join(sorted(providers)) or None
        fallback_reason = ",".join(sorted(fallback_reasons)) or None
        result = TaggerRunResult("ok", len(articles), scored, provider, fallback_reason)
        _record_run(
            session,
            status=result.status,
            attempted=result.attempted,
            scored=result.scored,
            duration_ms=round((time.monotonic() - started) * 1000),
            provider=provider,
            fallback_reason=fallback_reason,
        )
        return result

    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM tagger on unscored articles")
    parser.add_argument("--backfill", action="store_true", help="Process all unscored articles")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process N most recent unscored articles",
    )
    parser.add_argument(
        "--prefiltered",
        action="store_true",
        help="Only score prefiltered articles",
    )
    parser.add_argument("--batch-size", type=int, default=10, help="Articles per LLM call")
    parser.add_argument(
        "--include-realtime",
        action="store_true",
        help="Explicitly include realtime candidates after the convergence decision",
    )
    parser.add_argument(
        "--window-end",
        help="Bound recovery to the 24h UTC window ending at this ISO timestamp",
    )
    args = parser.parse_args()

    if not args.backfill and args.limit <= 0 and not args.prefiltered:
        parser.error("Specify --backfill, --limit N, or --prefiltered")
    try:
        window_end = datetime.fromisoformat(args.window_end) if args.window_end else None
    except ValueError:
        parser.error("--window-end must be an ISO timestamp")
    window_start = window_end - timedelta(hours=24) if window_end else None

    run_tagger(
        backfill=args.backfill,
        limit=args.limit,
        prefiltered=args.prefiltered,
        batch_size=args.batch_size,
        include_realtime=args.include_realtime,
        window_start=window_start,
        window_end=window_end,
    )


if __name__ == "__main__":
    main()
