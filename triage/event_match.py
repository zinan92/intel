"""Shared deterministic matcher for realtime reports about the same event."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Mapping

EVENT_WINDOW = timedelta(minutes=45)
HEADLINE_SIMILARITY_THRESHOLD = 0.90


def normalize_headline(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower().strip()
    text = re.sub(r"^【[^】]{1,20}】", "", text)
    text = re.sub(r"^财联社\d{1,2}月\d{1,2}日电[，,:：\s]*", "", text)
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE)


def _report_time(report: Mapping[str, Any]) -> datetime | None:
    value = report.get("published_at") or report.get("collected_at")
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def reports_match(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    window: timedelta = EVENT_WINDOW,
) -> bool:
    """Return whether two cross-source, time-bounded headlines report one event."""
    if left.get("source") == right.get("source"):
        return False
    left_time = _report_time(left)
    right_time = _report_time(right)
    if left_time is None or right_time is None or abs(left_time - right_time) > window:
        return False
    left_title = normalize_headline(left.get("title"))
    right_title = normalize_headline(right.get("title"))
    if not left_title or not right_title:
        return False
    if left_title == right_title:
        return True
    left_numbers = set(re.findall(r"\d+(?:\.\d+)?", str(left.get("title") or "")))
    right_numbers = set(re.findall(r"\d+(?:\.\d+)?", str(right.get("title") or "")))
    if left_numbers and right_numbers and left_numbers != right_numbers:
        return False
    if SequenceMatcher(None, left_title, right_title).ratio() >= HEADLINE_SIMILARITY_THRESHOLD:
        return True
    shorter, longer = sorted((left_title, right_title), key=len)
    return shorter in longer and len(shorter) / max(len(longer), 1) >= 0.80
