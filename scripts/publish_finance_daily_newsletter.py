"""Generate, archive, and deliver the Finance Daily Newsletter."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests
from dotenv import load_dotenv

from briefs.models import Brief
from db.database import get_session
from scripts.generate_narrative_signal import (
    ScoringCoverageError,
    current_brief_window,
    generate_brief,
    window_end_for_archive_date,
)
from scripts.run_llm_tagger import run_tagger

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

BRIEF_TIMEZONE = ZoneInfo("Asia/Shanghai")
DEFAULT_OBSIDIAN_DIR = Path("/Users/wendy/park-io/007_finance daily newsletter")
MAX_FEISHU_TEXT_CHARS = 16000

SOURCE_LABELS = {
    "rss": "RSS/媒体源",
    "google_news": "Google News",
    "yahoo_finance": "Yahoo Finance",
    "hackernews": "Hacker News",
    "reddit": "Reddit",
    "github_trending": "GitHub Trending",
    "github_release": "GitHub Releases",
    "website_monitor": "官网监控",
    "social_kol": "全球 KOL",
    "xueqiu": "雪球/A股社交",
}

STATUS_LABELS = {
    "ok": "正常",
    "stale": "滞后",
    "degraded": "降级",
    "error": "错误",
    "no_data": "无数据",
    "disabled": "未启用",
}

STATUS_SEVERITY = {
    "ok": 0,
    "no_data": 1,
    "stale": 2,
    "disabled": 3,
    "degraded": 4,
    "error": 5,
}


@dataclass(frozen=True)
class DeliveryResult:
    brief_id: int
    obsidian_path: Path
    feishu_sent: bool


def _obsidian_dir() -> Path:
    return Path(os.getenv("OBSIDIAN_FINANCE_NEWSLETTER_DIR", str(DEFAULT_OBSIDIAN_DIR))).expanduser()


def _find_brief(session, brief_id: int) -> Brief:
    brief = session.get(Brief, brief_id)
    if brief is None:
        raise RuntimeError(f"Brief #{brief_id} not found")
    return brief


def _latest_published_brief(session) -> Brief | None:
    return (
        session.query(Brief)
        .filter(Brief.status == "published")
        .order_by(Brief.created_at.desc())
        .first()
    )


def _source_health_lines(session) -> list[str]:
    from api.health_routes import _build_source_details

    rows = _build_source_details(session)
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["source_type"], []).append(row)

    lines: list[str] = []
    for source_type in sorted(grouped):
        group = grouped[source_type]
        active = [row for row in group if row["is_active"]]
        considered = active or group
        worst = max(
            considered,
            key=lambda row: STATUS_SEVERITY.get(str(row["status"]), 0),
        )
        status = str(worst["status"])
        label = SOURCE_LABELS.get(source_type, source_type)
        active_count = len(active)
        inactive_count = len(group) - active_count
        articles_24h = max(int(row.get("articles_24h") or 0) for row in group)

        status_text = STATUS_LABELS.get(status, status)
        if status == "disabled" and active_count:
            status_text = "配置缺失"

        details = [status_text]
        details.append(f"{active_count} active")
        if inactive_count:
            details.append(f"{inactive_count} inactive")
        details.append(f"24h fetched {articles_24h}")

        age = worst.get("freshness_age_hours")
        if age is not None:
            details.append(f"last run {age}h ago")
        if worst.get("last_error_category"):
            details.append(f"error={worst['last_error_category']}")

        lines.append(f"- {label}: " + "; ".join(details))

    return lines


def _source_health_text(session) -> str:
    lines = _source_health_lines(session)
    if not lines:
        lines = ["- Source health unavailable"]

    from api.health_routes import _build_processing_health

    processing = _build_processing_health(session)
    tagger = processing["llm_tagger"]
    events = processing["event_aggregation"]
    lines.extend([
        "",
        "Processing Status:",
        f"- Article scoring: {STATUS_LABELS.get(tagger['status'], tagger['status'])}; "
        f"scored {tagger['scored']}/{tagger['attempted']}; provider={tagger['provider'] or 'unknown'}",
        f"- Event aggregation: {STATUS_LABELS.get(events['status'], events['status'])}; "
        f"usable {events['usable_articles']}/{events['fresh_articles']}; "
        f"events updated {events['events_updated']}; provider={events['provider'] or 'none'}",
    ])
    return "\n".join(lines)


def _safe_title_part(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "-", text).strip("-")


def _obsidian_path_for(brief: Brief, output_dir: Path) -> Path:
    created = brief.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=ZoneInfo("UTC"))
    local_created = created.astimezone(BRIEF_TIMEZONE)
    date_part = local_created.strftime("%Y-%m-%d")
    base = output_dir / f"{date_part}-finance-daily-newsletter.md"
    if not base.exists():
        return base

    existing = base.read_text(encoding="utf-8", errors="ignore")
    if f"brief_id: {brief.id}" in existing:
        return base

    title_part = _safe_title_part(f"brief-{brief.id}")
    return output_dir / f"{date_part}-finance-daily-newsletter-{title_part}.md"


def _markdown_for_brief(brief: Brief, source_health: str) -> str:
    created = brief.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=ZoneInfo("UTC"))
    local_created = created.astimezone(BRIEF_TIMEZONE)
    title_date = local_created.strftime("%Y-%m-%d")
    generated_at = local_created.strftime("%Y-%m-%d %H:%M:%S %Z")

    return f"""---
title: 财经日报 {title_date}
brief_id: {brief.id}
generated_at: {generated_at}
article_count: {brief.article_count}
signal_count: {brief.signal_count}
source: park-intel
provider: {brief.provider or "unknown"}
scoring_coverage: {(brief.scoring_coverage or 0.0):.1%}
scored_articles: {brief.scored_article_count or 0}/{brief.candidate_article_count or 0}
---

# 财经日报 | {title_date}

Generated by Park Intel.

## Source Status

{source_health}

---

{brief.content.strip()}
"""


def save_to_obsidian(
    brief: Brief,
    source_health: str,
    *,
    replace_existing: bool = False,
) -> Path:
    output_dir = _obsidian_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = _obsidian_path_for(brief, output_dir)
    if replace_existing:
        created = brief.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=ZoneInfo("UTC"))
        date_part = created.astimezone(BRIEF_TIMEZONE).strftime("%Y-%m-%d")
        path = output_dir / f"{date_part}-finance-daily-newsletter.md"
        if path.exists() and f"brief_id: {brief.id}" not in path.read_text(encoding="utf-8", errors="ignore"):
            backup_dir = output_dir / ".recovery-backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
            backup = backup_dir / f"{date_part}-finance-daily-newsletter-{digest}.md"
            if not backup.exists():
                shutil.copy2(path, backup)

    pending = path.with_name(f".{path.name}.pending")
    pending.write_text(_markdown_for_brief(brief, source_health), encoding="utf-8")
    pending.replace(path)
    logger.info("Saved finance newsletter brief #%d to %s", brief.id, path)
    return path


def _feishu_signature(secret: str, timestamp: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _feishu_text(brief: Brief, obsidian_path: Path, source_health: str) -> str:
    created = brief.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=ZoneInfo("UTC"))
    local_created = created.astimezone(BRIEF_TIMEZONE)
    header = (
        f"财经日报 | {local_created.strftime('%Y-%m-%d')}\n"
        f"Brief #{brief.id} | {brief.article_count} articles | {brief.signal_count} signals\n"
        f"评分覆盖率: {(brief.scoring_coverage or 0.0):.1%} "
        f"({brief.scored_article_count or 0}/{brief.candidate_article_count or 0})\n"
        f"Obsidian: {obsidian_path}\n\n"
        "Source Status:\n"
        f"{source_health}\n\n"
        "----------------\n\n"
    )
    text = header + brief.content.strip()
    if len(text) <= MAX_FEISHU_TEXT_CHARS:
        return text
    return text[: MAX_FEISHU_TEXT_CHARS - 80] + "\n\n[内容过长，已截断；完整版本见 Obsidian。]"


def send_to_feishu(brief: Brief, obsidian_path: Path, source_health: str) -> bool:
    if os.getenv("PARK_INTEL_SKIP_FEISHU", "").strip() == "1":
        logger.info("PARK_INTEL_SKIP_FEISHU=1, skipping Feishu send")
        return False

    _send_feishu_status(_feishu_text(brief, obsidian_path, source_health))

    logger.info("Sent finance newsletter brief #%d to Feishu", brief.id)
    return True


def _send_feishu_status(text: str) -> None:
    webhook = os.getenv("FEISHU_BOT_WEBHOOK", "").strip()
    secret = os.getenv("FEISHU_BOT_SECRET", "").strip()
    if not webhook:
        raise RuntimeError("FEISHU_BOT_WEBHOOK is not configured")

    timestamp = str(int(time.time()))
    payload = {
        "timestamp": timestamp,
        "msg_type": "text",
        "content": {"text": text},
    }
    if secret:
        payload["sign"] = _feishu_signature(secret, timestamp)

    response = requests.post(webhook, json=payload, timeout=20)
    response.raise_for_status()
    data = response.json()
    code = data.get("code", data.get("StatusCode", 0))
    if code not in (0, "0"):
        raise RuntimeError(f"Feishu bot send failed: {data}")


def _record_generation_failure(
    error: Exception,
    *,
    is_backfill: bool,
    archive_date: date | None = None,
) -> Path:
    output_dir = _obsidian_dir() / ".delivery-manifests"
    output_dir.mkdir(parents=True, exist_ok=True)
    if archive_date is not None:
        report_date = archive_date.isoformat()
    else:
        window_end = getattr(error, "window_end", None)
        if window_end is None:
            report_date = datetime.now(BRIEF_TIMEZONE).date().isoformat()
        else:
            report_date = (
                window_end.replace(tzinfo=ZoneInfo("UTC"))
                .astimezone(BRIEF_TIMEZONE)
                .date()
                .isoformat()
            )
    is_scoring_failure = isinstance(error, ScoringCoverageError)
    status = "blocked_scoring_coverage" if is_scoring_failure else "generation_failed"
    path = output_dir / f"{report_date}-daily.json"
    fingerprint = hashlib.sha256(
        f"finance_daily_newsletter|{report_date}|{status}".encode("utf-8")
    ).hexdigest()

    previous: dict = {}
    if path.exists():
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = {}

    already_alerted = (
        previous.get("report_date") == report_date
        and previous.get("alert_sent") is True
    )
    payload: dict[str, object] = {
        "report": "finance_daily_newsletter",
        "report_date": report_date,
        "status": status,
        "failure_type": type(error).__name__,
        "error_message": str(error)[:500],
        "fingerprint": fingerprint,
        "alert_sent": already_alerted,
        "updated_at": datetime.now(BRIEF_TIMEZONE).isoformat(),
    }
    if is_scoring_failure:
        payload.update({
            "window_start": error.window_start.isoformat(),
            "window_end": error.window_end.isoformat(),
            "eligible_count": error.eligible_count,
            "scored_count": error.scored_count,
            "scoring_coverage": error.coverage,
        })

    if not is_backfill and not already_alerted and os.getenv("PARK_INTEL_SKIP_FEISHU", "").strip() != "1":
        message = (
            f"财经日报 | {report_date} | "
            + (
                f"生成已阻断\n评分覆盖率 {error.scored_count}/{error.eligible_count} "
                f"({error.coverage:.1%})，不足以进行相关性排序。"
                if is_scoring_failure
                else "生成失败\n本次没有发布新日报，也没有使用旧日报替代。"
            )
            + "\n请查看 Obsidian delivery manifest。"
        )
        try:
            _send_feishu_status(message)
            payload["alert_sent"] = True
        except Exception as exc:
            payload["alert_error"] = type(exc).__name__
            logger.exception("Failed to send Daily scoring status to Feishu")

    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)
    logger.error("Daily publication blocked; scoring status saved to %s", path)
    return path


def _record_scoring_failure(
    error: ScoringCoverageError,
    *,
    is_backfill: bool,
    archive_date: date | None = None,
) -> Path:
    return _record_generation_failure(
        error,
        is_backfill=is_backfill,
        archive_date=archive_date,
    )


def _mark_daily_delivery_resolved(
    brief: Brief,
    obsidian_path: Path,
    feishu_sent: bool,
    *,
    is_backfill: bool,
) -> None:
    """Close a same-day failure manifest without discarding its evidence."""
    created = brief.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=ZoneInfo("UTC"))
    report_date = created.astimezone(BRIEF_TIMEZONE).date().isoformat()
    path = _obsidian_dir() / ".delivery-manifests" / f"{report_date}-daily.json"
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(payload, dict) or payload.get("status") not in {
        "blocked_scoring_coverage",
        "generation_failed",
    }:
        return
    previous_status = payload["status"]
    payload.update({
        "status": "archived" if is_backfill else "published",
        "previous_failure_status": previous_status,
        "resolved": True,
        "resolved_brief_id": brief.id,
        "resolved_archive_path": str(obsidian_path),
        "feishu_sent": feishu_sent,
        "updated_at": datetime.now(BRIEF_TIMEZONE).isoformat(),
    })
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


def _generate_current_brief_with_preflight(limit: int) -> int | None:
    """Generate against one frozen window, filling missing scores first."""
    _, frozen_end, _ = current_brief_window()
    try:
        return generate_brief(limit=limit, window_end=frozen_end, publish_current=True)
    except ScoringCoverageError as coverage_error:
        run_tagger(
            limit=max(limit * 3, 300),
            batch_size=20,
            window_start=coverage_error.window_start,
            window_end=coverage_error.window_end,
        )
        return generate_brief(limit=limit, window_end=frozen_end, publish_current=True)


def publish_finance_daily_newsletter(
    limit: int = 100,
    *,
    generate: bool = True,
    archive_date: date | None = None,
    replace_archive: bool = False,
) -> DeliveryResult | None:
    """Publish the current Daily Brief or archive one explicit historical day."""

    is_backfill = archive_date is not None
    try:
        brief_id = (
            _generate_current_brief_with_preflight(limit)
            if not is_backfill
            else generate_brief(
                limit=limit,
                window_end=window_end_for_archive_date(archive_date),
                publish_current=False,
            )
            if generate
            else None
        )
    except ScoringCoverageError as exc:
        _record_scoring_failure(exc, is_backfill=is_backfill, archive_date=archive_date)
        return None
    except Exception as exc:
        _record_generation_failure(exc, is_backfill=is_backfill, archive_date=archive_date)
        return None

    session = get_session()
    try:
        if generate and brief_id is None:
            _record_generation_failure(
                RuntimeError("generation returned no brief"),
                is_backfill=is_backfill,
                archive_date=archive_date,
            )
            logger.error("Brief generation failed; delivery skipped")
            return None
        brief = _find_brief(session, brief_id) if brief_id is not None else _latest_published_brief(session)
        if brief is None:
            logger.error("No published brief available for finance newsletter delivery")
            return None

        source_health = _source_health_text(session)
        obsidian_path = save_to_obsidian(
            brief,
            source_health,
            replace_existing=is_backfill and replace_archive,
        )
        if is_backfill:
            logger.info("Historical Daily backfill for %s is archive-only; Feishu skipped", archive_date)
            feishu_sent = False
        else:
            feishu_sent = send_to_feishu(brief, obsidian_path, source_health)
        _mark_daily_delivery_resolved(
            brief,
            obsidian_path,
            feishu_sent,
            is_backfill=is_backfill,
        )
        return DeliveryResult(
            brief_id=brief.id,
            obsidian_path=obsidian_path,
            feishu_sent=feishu_sent,
        )
    finally:
        session.close()


if __name__ == "__main__":
    import argparse
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Publish Finance Daily Newsletter")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--no-generate", action="store_true", help="Deliver latest published brief without generating a new one")
    parser.add_argument("--for-date", help="Archive one historical Beijing date (YYYY-MM-DD) without sending Feishu")
    parser.add_argument(
        "--replace-archive",
        action="store_true",
        help="Replace canonical history after preserving a recovery backup",
    )
    args = parser.parse_args()

    if args.no_generate and args.for_date:
        parser.error("--no-generate cannot be combined with --for-date")
    if args.replace_archive and not args.for_date:
        parser.error("--replace-archive requires --for-date")
    try:
        archive_date = date.fromisoformat(args.for_date) if args.for_date else None
    except ValueError:
        parser.error("--for-date must use YYYY-MM-DD")

    result = publish_finance_daily_newsletter(
        limit=args.limit,
        generate=not args.no_generate,
        archive_date=archive_date,
        replace_archive=args.replace_archive,
    )
    if result is None:
        raise SystemExit("Finance daily newsletter delivery failed")
    print(f"Delivered brief #{result.brief_id} to {result.obsidian_path}; feishu_sent={result.feishu_sent}")
