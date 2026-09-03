#!/usr/bin/env python3
"""Bounded Daily/Weekly recovery with backups and an auditable receipt."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import DB_PATH
from db.database import get_session, init_db
from scripts.publish_finance_daily_newsletter import (
    DeliveryResult,
    publish_finance_daily_newsletter,
)
from scripts.publish_weekly_finance_newsletter import (
    DEFAULT_WEEKLY_ARCHIVE_DIR,
    WeeklyDeliveryResult,
    publish_weekly_finance_newsletter,
)
from scripts.run_llm_tagger import TaggerRunResult, run_tagger
from scripts.weekly_finance_newsletter import weekly_window


RECOVERY_REASON = "score-coverage-recovery-94"
DEFAULT_RECEIPT_DIR = Path(__file__).resolve().parents[1] / "docs"


@dataclass(frozen=True)
class DailyRecovery:
    day: str
    tagger_status: str
    tagger_attempted: int
    tagger_scored: int
    scoring_provider: str | None
    fallback_reason: str | None
    brief_id: int
    archive_path: str
    synthesis_provider: str | None
    candidate_articles: int | None
    scored_articles: int | None
    scoring_coverage: float | None
    feishu_sent: bool


class FinanceRecoveryError(RuntimeError):
    """Raised when a bounded recovery cannot satisfy every publication gate."""


def backup_database(backup_dir: Path) -> Path:
    """Create a transactionally consistent SQLite backup without copying WAL files."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    destination = backup_dir / f"park_intel-before-finance-recovery-{stamp}.db"
    with sqlite3.connect(DB_PATH) as source, sqlite3.connect(destination) as target:
        source.backup(target)
    return destination


def _brief_metadata(brief_id: int) -> dict[str, object]:
    from briefs.models import Brief

    session = get_session()
    try:
        brief = session.get(Brief, brief_id)
        if brief is None:
            raise FinanceRecoveryError(f"Recovered Brief #{brief_id} is missing")
        return {
            "synthesis_provider": brief.provider,
            "candidate_articles": brief.candidate_article_count,
            "scored_articles": brief.scored_article_count,
            "scoring_coverage": brief.scoring_coverage,
        }
    finally:
        session.close()


def _residual_gaps() -> list[str]:
    from db.models import Article

    session = get_session()
    try:
        count = (
            session.query(Article)
            .filter(Article.collection_lane == "hourly", Article.relevance_score.is_(None))
            .count()
        )
    finally:
        session.close()
    if not count:
        return []
    return [
        f"{count} hourly articles outside the bounded recovery windows remain unscored; "
        "they were not published in the recovered Weekly."
    ]


def _write_receipt(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(f".{path.name}.pending")
    pending.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def recover_finance_newsletters(
    *,
    week_ending: date,
    affected_start: date,
    receipt_path: Path,
    batch_size: int = 20,
) -> dict[str, object]:
    window = weekly_window(week_ending)
    if not window.lookback_start <= affected_start <= window.lookback_end:
        raise ValueError("affected_start must fall inside the Weekly lookback")

    previous: dict[str, object] = {}
    if receipt_path.exists():
        try:
            loaded = json.loads(receipt_path.read_text(encoding="utf-8"))
            if loaded.get("recovery_reason") == RECOVERY_REASON:
                previous = loaded
        except (OSError, ValueError):
            previous = {}
    previous_backup = previous.get("database_backup")
    backup_path = (
        Path(str(previous_backup))
        if previous_backup and Path(str(previous_backup)).exists()
        else backup_database(DB_PATH.parent / "recovery-backups")
    )
    previous_daily = [
        DailyRecovery(**row)
        for row in previous.get("daily", [])
        if isinstance(row, dict)
    ]
    completed_days = {
        row.day
        for row in previous_daily
        if row.scoring_coverage == 1.0 and Path(row.archive_path).exists()
    }
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    receipt: dict[str, object] = {
        "status": "running",
        "recovery_reason": RECOVERY_REASON,
        "week_ending": week_ending.isoformat(),
        "affected_start": affected_start.isoformat(),
        "lookback_start": window.lookback_start.isoformat(),
        "lookback_end": window.lookback_end.isoformat(),
        "database_backup": str(backup_path),
        "started_at": started_at,
        "daily": [asdict(row) for row in previous_daily],
        "weekly": None,
        "replay_status": None,
        "residual_gaps": [],
    }
    _write_receipt(receipt_path, receipt)

    try:
        init_db()
        daily_rows: list[DailyRecovery] = list(previous_daily)
        for offset in range(7):
            day = window.lookback_start + timedelta(days=offset)
            if day < affected_start:
                continue
            if day.isoformat() in completed_days:
                continue
            window_end = datetime.combine(day, time.min)
            if day >= affected_start:
                tagger = run_tagger(
                    limit=300,
                    batch_size=batch_size,
                    window_start=window_end - timedelta(hours=24),
                    window_end=window_end,
                )
            else:
                tagger = TaggerRunResult("not_needed", 0, 0, None, None)

            delivery = publish_finance_daily_newsletter(
                archive_date=day,
                replace_archive=True,
            )
            if delivery is None:
                raise FinanceRecoveryError(f"Daily recovery failed for {day}")
            metadata = _brief_metadata(delivery.brief_id)
            if metadata["scoring_coverage"] != 1.0:
                raise FinanceRecoveryError(f"Daily recovery coverage is not complete for {day}")
            daily_rows.append(DailyRecovery(
                day=day.isoformat(),
                tagger_status=tagger.status,
                tagger_attempted=tagger.attempted,
                tagger_scored=tagger.scored,
                scoring_provider=tagger.provider,
                fallback_reason=tagger.fallback_reason,
                brief_id=delivery.brief_id,
                archive_path=str(delivery.obsidian_path),
                synthesis_provider=metadata["synthesis_provider"],
                candidate_articles=metadata["candidate_articles"],
                scored_articles=metadata["scored_articles"],
                scoring_coverage=metadata["scoring_coverage"],
                feishu_sent=delivery.feishu_sent,
            ))
            receipt["daily"] = [asdict(row) for row in daily_rows]
            _write_receipt(receipt_path, receipt)

        weekly = publish_weekly_finance_newsletter(
            week_ending,
            archive_dir=DEFAULT_WEEKLY_ARCHIVE_DIR,
            force_resend=True,
            revision_reason=RECOVERY_REASON,
        )
        replay = publish_weekly_finance_newsletter(
            week_ending,
            archive_dir=DEFAULT_WEEKLY_ARCHIVE_DIR,
            force_resend=True,
            revision_reason=RECOVERY_REASON,
        )
        if weekly.status not in {"published", "noop"} or replay.status != "noop":
            raise FinanceRecoveryError(
                f"Weekly idempotency failed: first={weekly.status}, replay={replay.status}"
            )
        receipt["weekly"] = _weekly_receipt(weekly)
        receipt["replay_status"] = replay.status
        receipt["residual_gaps"] = _residual_gaps()
        receipt["status"] = "complete"
    except Exception as exc:
        receipt["status"] = "partial"
        receipt["residual_gaps"] = [f"{type(exc).__name__}: {exc}"]
        raise
    finally:
        receipt["completed_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        _write_receipt(receipt_path, receipt)

    return receipt


def _weekly_receipt(result: WeeklyDeliveryResult) -> dict[str, object]:
    return {
        "status": result.status,
        "archive_path": str(result.archive_path),
        "manifest_path": str(result.manifest_path),
        "content_sha256": result.content_sha256,
        "feishu_sent": result.feishu_sent,
        "source_status": result.source_status,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover one Finance Weekly lookback")
    parser.add_argument("--week-ending", required=True, help="Sunday in YYYY-MM-DD")
    parser.add_argument("--affected-start", required=True, help="First Daily date requiring rescoring")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    week_ending = date.fromisoformat(args.week_ending)
    receipt_path = args.receipt or (
        DEFAULT_RECEIPT_DIR / f"finance-newsletter-recovery-{week_ending.isoformat()}.json"
    )
    result = recover_finance_newsletters(
        week_ending=week_ending,
        affected_start=date.fromisoformat(args.affected_start),
        receipt_path=receipt_path,
        batch_size=args.batch_size,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
