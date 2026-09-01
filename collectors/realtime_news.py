"""Collectors for high-cadence market-news feeds.

The realtime lane deliberately returns the same normalized article shape as
the existing hourly collectors. That lets the existing Article persistence,
deduplication, tagging, and API read models be reused while the lane is
validated in parallel with the hourly lane.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any

import requests

logger = logging.getLogger(__name__)

CLS_ROLL_URL = "https://www.cls.cn/v1/roll/get_roll_list"
CLS_REFERER = "https://www.cls.cn/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)


def _cls_sign(params: dict[str, Any]) -> str:
    """Build the signature used by CLS's public web rolling-news endpoint."""
    query = "&".join(f"{key}={params[key]}" for key in sorted(params))
    return hashlib.md5(hashlib.sha1(query.encode()).hexdigest().encode()).hexdigest()


def _utc_naive_from_unix(value: Any) -> datetime | None:
    """Convert a Unix timestamp to the project's UTC-naive datetime format."""
    if value in (None, ""):
        return None
    try:
        return datetime.utcfromtimestamp(float(value))
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def fetch_cls_telegraph(*, page_size: int = 50) -> list[dict[str, Any]]:
    """Fetch and normalize CLS Telegraph rolling news.

    HTTP, status, JSON, and schema failures are intentionally raised to the
    adapter layer, where the existing retry and CollectorResult machinery
    records the failure. Advertisements and malformed rows are skipped as
    non-news data.
    """
    params: dict[str, Any] = {
        "appName": "CailianpressWeb",
        "os": "web",
        "sv": "7.7.5",
        "last_time": "",
        "refresh_type": 1,
        "rn": page_size,
    }
    url = f"{CLS_ROLL_URL}?{'&'.join(f'{key}={params[key]}' for key in params)}&sign={_cls_sign(params)}"
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Referer": CLS_REFERER},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload["data"]["roll_data"]
    if not isinstance(rows, list):
        raise TypeError("CLS roll_data must be a list")

    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("is_ad"):
            continue

        item_id = row.get("id")
        title = str(row.get("title") or row.get("brief") or row.get("content") or "").strip()
        content = str(row.get("content") or row.get("brief") or title).strip()
        if item_id in (None, "") or not title:
            continue

        normalized.append({
            "source": "cls_telegraph",
            "source_id": f"cls_telegraph:{item_id}",
            "author": str(row.get("author") or "").strip(),
            "title": title,
            "content": content[:4000],
            "url": str(row.get("shareurl") or f"https://www.cls.cn/detail/{item_id}"),
            "tags": ["market-news"],
            "score": 0,
            "published_at": _utc_naive_from_unix(row.get("ctime")),
            "collection_lane": "realtime",
        })
    return normalized
