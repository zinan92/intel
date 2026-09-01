"""Collectors for high-cadence market-news feeds.

The realtime lane deliberately returns the same normalized article shape as
the existing hourly collectors. That lets the existing Article persistence,
deduplication, tagging, and API read models be reused while the lane is
validated in parallel with the hourly lane.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger(__name__)

CLS_ROLL_URL = "https://www.cls.cn/v1/roll/get_roll_list"
CLS_REFERER = "https://www.cls.cn/"
EASTMONEY_FAST_NEWS_URL = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
EASTMONEY_REFERER = "https://kuaixun.eastmoney.com/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
_EASTMONEY_REQUEST_LOCK = Lock()
_LAST_EASTMONEY_REQUEST_AT: float | None = None
_EASTMONEY_MIN_INTERVAL_SECONDS = 1.0


def _cls_sign(params: dict[str, Any]) -> str:
    """Build the signature used by CLS's public web rolling-news endpoint."""
    query = "&".join(f"{key}={params[key]}" for key in sorted(params))
    return hashlib.md5(hashlib.sha1(query.encode()).hexdigest().encode()).hexdigest()


def _utc_naive_from_unix(value: Any) -> datetime | None:
    """Convert a Unix timestamp to the project's UTC-naive datetime format."""
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).replace(tzinfo=None)
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


def _wait_for_eastmoney_request() -> None:
    """Serialize Eastmoney requests and keep a small anti-rate-limit gap."""
    global _LAST_EASTMONEY_REQUEST_AT
    with _EASTMONEY_REQUEST_LOCK:
        now = time.monotonic()
        if _LAST_EASTMONEY_REQUEST_AT is not None:
            remaining = _EASTMONEY_MIN_INTERVAL_SECONDS - (now - _LAST_EASTMONEY_REQUEST_AT)
            if remaining > 0:
                time.sleep(remaining)
        _LAST_EASTMONEY_REQUEST_AT = time.monotonic()


def _eastmoney_ticker(raw: Any) -> str | None:
    """Map Eastmoney market.code values (for example 0.300765) to symbols."""
    if not isinstance(raw, str) or "." not in raw:
        return None
    market, code = raw.split(".", 1)
    if not code.isdigit() or not code:
        return None
    exchange = {"0": "SZ", "1": "SH", "2": "SZ", "6": "SH"}.get(market)
    return f"{code}.{exchange}" if exchange else code


def fetch_eastmoney_global_news(*, page_size: int = 50) -> list[dict[str, Any]]:
    """Fetch and normalize Eastmoney's public 7x24 fast-news stream."""
    params: dict[str, Any] = {
        "client": "web",
        "biz": "web_724",
        "fastColumn": 102,
        "sortEnd": "",
        "pageSize": page_size,
        "req_trace": str(uuid.uuid4()),
    }
    _wait_for_eastmoney_request()
    response = requests.get(
        EASTMONEY_FAST_NEWS_URL,
        params=params,
        headers={"User-Agent": USER_AGENT, "Referer": EASTMONEY_REFERER},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload["data"]["fastNewsList"]
    if not isinstance(rows, list):
        raise TypeError("Eastmoney fastNewsList must be a list")

    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("code") or "").strip()
        title = str(row.get("title") or "").strip()
        if not item_id or not title:
            continue

        published_at: datetime | None = None
        show_time = row.get("showTime")
        if show_time:
            try:
                localized = datetime.strptime(str(show_time), "%Y-%m-%d %H:%M:%S")
                published_at = localized.replace(tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(
                    ZoneInfo("UTC")
                ).replace(tzinfo=None)
            except (TypeError, ValueError):
                logger.warning("Eastmoney row %s has invalid showTime %r", item_id, show_time)

        tickers = []
        for raw_ticker in row.get("stockList") or []:
            ticker = _eastmoney_ticker(raw_ticker)
            if ticker and ticker not in tickers:
                tickers.append(ticker)

        normalized.append({
            "source": "eastmoney_global_news",
            "source_id": f"eastmoney_global_news:{item_id}",
            "author": "",
            "title": title,
            "content": str(row.get("summary") or title).strip()[:4000],
            "url": "https://kuaixun.eastmoney.com/",
            "tags": ["cn-market-news"],
            "tickers": tickers,
            "score": 0,
            "published_at": published_at,
            "collection_lane": "realtime",
        })
    return normalized
