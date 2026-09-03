"""Publish the validated Weekly Finance Newsletter exactly once per week."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

from scripts.generate_narrative_signal import PROJECT_ROOT
from scripts.publish_finance_daily_newsletter import _feishu_signature
from scripts.weekly_finance_newsletter import (
    DEFAULT_ARCHIVE_DIR,
    WeeklyGenerationError,
    generate_weekly_dry_run,
)


DEFAULT_WEEKLY_ARCHIVE_DIR = Path("/Users/wendy/park-io/008_finance weekly newsletter")
MAX_FEISHU_TEXT_CHARS = 16000
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class WeeklyDeliveryResult:
    week_ending: date
    status: str
    archive_path: Path
    manifest_path: Path
    content_sha256: str
    feishu_sent: bool
    source_status: dict[str, str]


class WeeklyDeliveryError(RuntimeError):
    """Raised when Weekly publication cannot meet its delivery contract."""


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _paths(archive_dir: Path, week_ending: date) -> tuple[Path, Path, Path]:
    archive_path = archive_dir / f"{week_ending.isoformat()}-finance-weekly-newsletter.md"
    manifest_dir = archive_dir / ".delivery-manifests"
    snapshot_dir = archive_dir / ".source-snapshots" / week_ending.isoformat()
    return archive_path, manifest_dir / f"{week_ending.isoformat()}.json", snapshot_dir


def _read_revisions(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    return [payload]


def _write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _feishu_text(markdown: str, archive_path: Path) -> str:
    text = f"Weekly Finance Newsletter\nObsidian: {archive_path}\n\n{markdown}"
    if len(text) <= MAX_FEISHU_TEXT_CHARS:
        return text
    return text[: MAX_FEISHU_TEXT_CHARS - 80] + "\n\n[内容过长，完整版本见 Obsidian。]"


def _send_to_feishu(markdown: str, archive_path: Path) -> bool:
    if os.getenv("PARK_INTEL_SKIP_FEISHU", "").strip() == "1":
        raise WeeklyDeliveryError("PARK_INTEL_SKIP_FEISHU=1 cannot satisfy live Weekly delivery")
    webhook = os.getenv("FEISHU_BOT_WEBHOOK", "").strip()
    if not webhook:
        raise WeeklyDeliveryError("FEISHU_BOT_WEBHOOK is not configured")
    secret = os.getenv("FEISHU_BOT_SECRET", "").strip()
    timestamp = str(int(time.time()))
    payload = {
        "timestamp": timestamp,
        "msg_type": "text",
        "content": {"text": _feishu_text(markdown, archive_path)},
    }
    if secret:
        payload["sign"] = _feishu_signature(secret, timestamp)
    response = requests.post(webhook, json=payload, timeout=20)
    response.raise_for_status()
    data = response.json()
    code = data.get("code", data.get("StatusCode", 0))
    if code not in (0, "0"):
        raise WeeklyDeliveryError(f"Feishu send failed with code={code}")
    return True


def publish_weekly_finance_newsletter(
    week_ending: date | str,
    *,
    archive_dir: Path = DEFAULT_WEEKLY_ARCHIVE_DIR,
    force_resend: bool = False,
    dry_run: bool = False,
    revision_reason: str | None = None,
) -> WeeklyDeliveryResult:
    from scripts.weekly_finance_newsletter import weekly_window

    window = weekly_window(week_ending)
    archive_path, manifest_path, snapshot_dir = _paths(archive_dir, window.week_ending)
    revisions = _read_revisions(manifest_path)
    published = [entry for entry in revisions if entry.get("status") == "published"]
    previous = published[-1] if published else None
    recovered = next(
        (entry for entry in published if revision_reason and entry.get("revision_reason") == revision_reason),
        None,
    )
    if recovered and not dry_run:
        return WeeklyDeliveryResult(
            window.week_ending,
            "noop",
            archive_path,
            manifest_path,
            str(recovered.get("content_sha256") or ""),
            False,
            dict(recovered.get("source_status") or {}),
        )
    if previous and not force_resend and not dry_run:
        return WeeklyDeliveryResult(
            window.week_ending,
            "noop",
            archive_path,
            manifest_path,
            str(previous.get("content_sha256") or ""),
            False,
            dict(previous.get("source_status") or {}),
        )
    result = generate_weekly_dry_run(
        window.week_ending,
        archive_dir=Path(os.getenv("OBSIDIAN_FINANCE_NEWSLETTER_DIR", str(DEFAULT_ARCHIVE_DIR))),
        include_calendar=True,
        snapshot_dir=snapshot_dir,
    )
    content_hash = _sha256(result.markdown)

    if previous and previous.get("content_sha256") == content_hash and not force_resend:
        return WeeklyDeliveryResult(
            window.week_ending,
            "noop",
            archive_path,
            manifest_path,
            content_hash,
            False,
            result.source_status,
        )
    if previous and previous.get("content_sha256") != content_hash and not force_resend:
        raise WeeklyDeliveryError("published content changed; use --force-resend explicitly")

    if dry_run:
        return WeeklyDeliveryResult(
            window.week_ending,
            "dry_run",
            archive_path,
            manifest_path,
            content_hash,
            False,
            result.source_status,
        )

    archive_dir.mkdir(parents=True, exist_ok=True)
    pending_path = archive_path.with_name(f".{archive_path.name}.pending")
    pending_path.write_text(result.markdown, encoding="utf-8")
    try:
        feishu_sent = _send_to_feishu(result.markdown, archive_path)
        pending_path.replace(archive_path)
    except Exception as exc:
        pending_path.unlink(missing_ok=True)
        failed = {
            "status": "failed",
            "week_ending": window.week_ending.isoformat(),
            "content_sha256": content_hash,
            "source_status": result.source_status,
            "snapshot_paths": [str(path) for path in result.snapshot_paths],
            "error": str(exc)[:500],
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        _write_json_atomic(manifest_path, revisions + [failed])
        raise WeeklyDeliveryError(str(exc)) from exc

    entry = {
        "status": "published",
        "week_ending": window.week_ending.isoformat(),
        "content_sha256": content_hash,
        "model": result.provider,
        "source_status": result.source_status,
        "snapshot_paths": [str(path) for path in result.snapshot_paths],
        "archive_path": str(archive_path),
        "feishu_sent": feishu_sent,
        "website_status": "not_attempted",
        "revision_reason": revision_reason,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    _write_json_atomic(manifest_path, revisions + [entry])
    return WeeklyDeliveryResult(
        window.week_ending,
        "published",
        archive_path,
        manifest_path,
        content_hash,
        feishu_sent,
        result.source_status,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish Weekly Finance Newsletter")
    parser.add_argument("--week-ending", required=True, help="Sunday in YYYY-MM-DD")
    parser.add_argument("--archive-dir", type=Path, default=DEFAULT_WEEKLY_ARCHIVE_DIR)
    parser.add_argument("--force-resend", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        result = publish_weekly_finance_newsletter(
            args.week_ending,
            archive_dir=args.archive_dir,
            force_resend=args.force_resend,
            dry_run=args.dry_run,
        )
    except (WeeklyDeliveryError, WeeklyGenerationError) as exc:
        parser.error(str(exc))
    print(
        f"weekly_delivery: {result.status} week_ending={result.week_ending} "
        f"archive={result.archive_path} manifest={result.manifest_path} "
        f"feishu_sent={result.feishu_sent}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
