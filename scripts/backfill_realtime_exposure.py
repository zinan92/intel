"""Classify existing realtime Articles against the approved exposure universe."""

from __future__ import annotations

import argparse
import json
from collections import Counter

from db.database import get_session, init_db
from db.models import Article
from triage.exposure import EXPOSURE_UNIVERSE_VERSION, match_article_exposure


def _parse_tickers(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(item) for item in value] if isinstance(value, list) else []


def classify_realtime_exposure(*, apply: bool = False) -> dict[str, int]:
    """Report or persist exposure matches; never changes raw article content."""
    init_db()
    session = get_session()
    counts: Counter[str] = Counter()
    try:
        articles = session.query(Article).filter(
            Article.collection_lane == "realtime",
        ).order_by(Article.id.asc()).all()
        for article in articles:
            match = match_article_exposure(
                article.title,
                article.content,
                _parse_tickers(article.tickers),
            )
            counts[match.status] += 1
            if apply:
                article.exposure_status = match.status
                article.exposure_assets = json.dumps(
                    list(match.asset_keys), ensure_ascii=False,
                )
                article.exposure_reason = match.reason
        if apply:
            session.commit()
        return dict(counts)
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Classify realtime articles for {EXPOSURE_UNIVERSE_VERSION}",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist exposure fields; default is a read-only report",
    )
    args = parser.parse_args()
    counts = classify_realtime_exposure(apply=args.apply)
    mode = "applied" if args.apply else "dry-run"
    print(f"universe={EXPOSURE_UNIVERSE_VERSION} mode={mode}")
    for status, count in sorted(counts.items()):
        print(f"{status}={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
