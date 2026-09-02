#!/usr/bin/env python3
"""Dry-run, apply, or undo reversible SEC backfill markers."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import get_session, init_db  # noqa: E402
from db.models import Article  # noqa: E402


def mark_sec_backfill(
    session,
    *,
    cutoff: datetime,
    reason: str,
    apply: bool,
) -> int:
    """Mark parsed SEC rows older than cutoff; return candidate count."""
    query = session.query(Article).filter(
        Article.source == "sec_edgar",
        Article.published_at.isnot(None),
        Article.published_at < cutoff,
        Article.is_backfill.is_(False),
    )
    count = query.count()
    if apply and count:
        query.update(
            {
                Article.is_backfill: True,
                Article.backfill_reason: reason,
            },
            synchronize_session=False,
        )
        session.commit()
    return count


def undo_sec_backfill(session, *, reason: str, apply: bool) -> int:
    """Undo only SEC markers carrying the exact supplied reason."""
    query = session.query(Article).filter(
        Article.source == "sec_edgar",
        Article.is_backfill.is_(True),
        Article.backfill_reason == reason,
    )
    count = query.count()
    if apply and count:
        query.update(
            {
                Article.is_backfill: False,
                Article.backfill_reason: None,
            },
            synchronize_session=False,
        )
        session.commit()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=int, default=72)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--undo", action="store_true")
    args = parser.parse_args()
    if args.hours < 1:
        raise SystemExit("--hours must be positive")

    init_db()
    session = get_session()
    try:
        if args.undo:
            count = undo_sec_backfill(
                session,
                reason=args.reason,
                apply=args.apply,
            )
            action = "unmark"
        else:
            cutoff = datetime.utcnow() - timedelta(hours=args.hours)
            count = mark_sec_backfill(
                session,
                cutoff=cutoff,
                reason=args.reason,
                apply=args.apply,
            )
            action = "mark"
        mode = "applied" if args.apply else "dry-run"
        print(f"{mode}: {action} candidates={count} reason={args.reason}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
