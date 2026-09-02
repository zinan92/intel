"""Official BlockBeats Pro API collector for realtime newsflashes."""

from __future__ import annotations

import hashlib
from html import unescape
from html.parser import HTMLParser
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import requests

from sources.errors import SourceBlockedError, SourceConfigurationError

BLOCKBEATS_NEWSFLASH_URL = "https://api-pro.theblockbeats.info/v1/newsflash"


class _TextExtractor(HTMLParser):
    _BLOCK_TAGS = frozenset({
        "br", "div", "li", "ol", "p", "section", "table", "td", "th", "tr", "ul",
    })
    _SUPPRESSED_TAGS = frozenset({"script", "style"})

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.suppressed_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SUPPRESSED_TAGS:
            self.suppressed_depth += 1
        elif tag in self._BLOCK_TAGS and self.suppressed_depth == 0:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SUPPRESSED_TAGS:
            self.suppressed_depth = max(self.suppressed_depth - 1, 0)
        elif tag in self._BLOCK_TAGS and self.suppressed_depth == 0:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self.suppressed_depth == 0:
            self.parts.append(data)


def _plain_text(value: Any) -> str:
    parser = _TextExtractor()
    parser.feed(str(value or ""))
    return " ".join(unescape("".join(parser.parts)).split())


def _published_at(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    raw = str(value).strip()
    try:
        if raw.replace(".", "", 1).isdigit():
            return datetime.fromtimestamp(float(raw), tz=timezone.utc).replace(tzinfo=None)
        local = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        return local.replace(tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(
            timezone.utc
        ).replace(tzinfo=None)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _fallback_id(title: str, link: str | None, published_at: datetime | None) -> str:
    material = "|".join((
        " ".join(title.lower().split()),
        (link or "").strip().lower(),
        published_at.isoformat() if published_at else "",
    ))
    digest = hashlib.sha256(material.encode()).hexdigest()[:24]
    return f"blockbeats_newsflash:sha256:{digest}"


def _api_key() -> str:
    value = os.getenv("BLOCKBEATS_API_KEY", "").strip()
    if value:
        return value
    key_file = os.getenv("BLOCKBEATS_API_KEY_FILE", "").strip()
    if key_file:
        try:
            value = Path(key_file).expanduser().read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise SourceConfigurationError(
                "BLOCKBEATS_API_KEY_FILE cannot be read"
            ) from exc
        if value:
            return value
    raise SourceConfigurationError("BLOCKBEATS_API_KEY is required")


def blockbeats_key_available() -> bool:
    try:
        _api_key()
    except SourceConfigurationError:
        return False
    return True


def _safe_url(value: Any, *, blockbeats_only: bool = False) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return None
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not hostname:
        return None
    if blockbeats_only and (
        parsed.scheme != "https"
        or not (
            hostname == "theblockbeats.info"
            or hostname.endswith(".theblockbeats.info")
        )
    ):
        return None
    return raw


def _rows(payload: dict[str, Any]) -> list[Any]:
    status = payload["status"]
    message = str(payload.get("message") or "BlockBeats provider failure")
    if status == 100:
        raise SourceConfigurationError(f"BlockBeats: {message}")
    if status in {101, 102}:
        raise SourceBlockedError(f"BlockBeats authentication failed: {message}")
    if status != 0:
        raise RuntimeError(f"BlockBeats provider status {status}: {message}")

    data = payload["data"]
    if isinstance(data, dict):
        data = data.get("data")
    if not isinstance(data, list):
        raise TypeError("BlockBeats data must be a list")
    return data


def fetch_blockbeats_newsflash(
    *,
    page_size: int = 50,
    lang: str = "cn",
) -> list[dict[str, Any]]:
    """Fetch the latest official BlockBeats Pro newsflash window."""
    response = requests.get(
        BLOCKBEATS_NEWSFLASH_URL,
        params={"page": 1, "size": page_size, "lang": lang},
        headers={"api-key": _api_key()},
        timeout=10,
    )
    if response.status_code in {401, 403, 429, 451}:
        raise SourceBlockedError(
            f"blockbeats_newsflash provider blocked HTTP {response.status_code}"
        )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError("BlockBeats response must be an object")

    provider_rows = _rows(payload)
    normalized: list[dict[str, Any]] = []
    for row in provider_rows:
        if not isinstance(row, dict):
            continue
        title = _plain_text(row.get("title"))
        if not title:
            continue
        content = _plain_text(row.get("content")) or title
        item_id = str(row.get("id") or row.get("guid") or "").strip()
        link = _safe_url(row.get("link"), blockbeats_only=True)
        if link is None and item_id:
            link = f"https://m.theblockbeats.info/flash/{item_id}"
        upstream_url = _safe_url(row.get("url"))
        upstream_attribution = str(
            row.get("source") or row.get("source_name") or ""
        ).strip() or None
        raw_time = row.get("create_time")
        published_at = _published_at(raw_time)
        timestamp_status = (
            "missing" if raw_time in (None, "")
            else "valid" if published_at else "invalid"
        )
        source_id = (
            f"blockbeats_newsflash:{item_id}"
            if item_id
            else _fallback_id(title, link, published_at)
        )
        normalized.append({
            "source": "blockbeats_newsflash",
            "source_id": source_id,
            "author": "BlockBeats",
            "title": title,
            "content": content[:4000],
            "url": link,
            "upstream_url": upstream_url,
            "upstream_attribution": upstream_attribution,
            "tags": ["crypto-news", "blockbeats"],
            "score": 0,
            "published_at": published_at,
            "collection_lane": "realtime",
            "source_authority": "secondary",
            "corroboration_state": "unconfirmed",
            "pin_eligibility": "requires_independent_confirmation",
            "review_state": "needs_review",
            "_timestamp_status": timestamp_status,
            "_provider_cursor": item_id or source_id,
        })
    if provider_rows and not normalized:
        raise TypeError("BlockBeats payload contained no valid newsflash rows")
    return normalized
