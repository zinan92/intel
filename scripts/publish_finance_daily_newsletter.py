"""Generate, archive, and deliver the Finance Daily Newsletter."""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

from briefs.models import Brief
from db.database import get_session
from scripts.generate_narrative_signal import generate_brief

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

BRIEF_TIMEZONE = ZoneInfo("Asia/Shanghai")
DEFAULT_OBSIDIAN_DIR = Path("/Users/wendy/park-io/finance daily newsletter")
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
        return "- Source health unavailable"
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
---

# 财经日报 | {title_date}

Generated by Park Intel.

## Source Status

{source_health}

---

{brief.content.strip()}
"""


def save_to_obsidian(brief: Brief, source_health: str) -> Path:
    output_dir = _obsidian_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = _obsidian_path_for(brief, output_dir)
    path.write_text(_markdown_for_brief(brief, source_health), encoding="utf-8")
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

    webhook = os.getenv("FEISHU_BOT_WEBHOOK", "").strip()
    secret = os.getenv("FEISHU_BOT_SECRET", "").strip()
    if not webhook:
        raise RuntimeError("FEISHU_BOT_WEBHOOK is not configured")

    timestamp = str(int(time.time()))
    payload = {
        "timestamp": timestamp,
        "msg_type": "text",
        "content": {"text": _feishu_text(brief, obsidian_path, source_health)},
    }
    if secret:
        payload["sign"] = _feishu_signature(secret, timestamp)

    response = requests.post(webhook, json=payload, timeout=20)
    response.raise_for_status()
    data = response.json()
    code = data.get("code", data.get("StatusCode", 0))
    if code not in (0, "0"):
        raise RuntimeError(f"Feishu bot send failed: {data}")

    logger.info("Sent finance newsletter brief #%d to Feishu", brief.id)
    return True


def publish_finance_daily_newsletter(limit: int = 100, *, generate: bool = True) -> DeliveryResult | None:
    """Generate the latest brief, archive it to Obsidian, and send it to Feishu."""
    brief_id = generate_brief(limit=limit) if generate else None

    session = get_session()
    try:
        brief = _find_brief(session, brief_id) if brief_id is not None else _latest_published_brief(session)
        if brief is None:
            logger.error("No published brief available for finance newsletter delivery")
            return None
        if generate and brief_id is None:
            logger.error("Brief generation failed; delivery skipped")
            return None

        source_health = _source_health_text(session)
        obsidian_path = save_to_obsidian(brief, source_health)
        feishu_sent = send_to_feishu(brief, obsidian_path, source_health)
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
    args = parser.parse_args()

    result = publish_finance_daily_newsletter(limit=args.limit, generate=not args.no_generate)
    if result is None:
        raise SystemExit("Finance daily newsletter delivery failed")
    print(f"Delivered brief #{result.brief_id} to {result.obsidian_path}; feishu_sent={result.feishu_sent}")
