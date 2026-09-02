"""Authorized Telegram MTProto channel collector for the realtime lane."""

from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import BASE_DIR
from sources.errors import SourceBlockedError, SourceConfigurationError

APPROVED_CHANNEL_NAMES = (
    "BRICS News",
    "BlockBeats",
    "Global News Monitor",
    "Intel Slava",
    "Disclose.tv",
    "Watcher Guru",
    "Solid Intel",
)
LOWER_TRUST_CHANNEL_NAMES = frozenset({
    "Global News Monitor",
    "Intel Slava",
    "Solid Intel",
})


def resolve_approved_channel_ids(
    joined_channels: list[tuple[str, int]],
) -> dict[str, int]:
    """Resolve display-name hints to one immutable numeric ID each."""
    resolved: dict[str, int] = {}
    for expected_name in APPROVED_CHANNEL_NAMES:
        matches = [
            int(channel_id)
            for channel_name, channel_id in joined_channels
            if channel_name == expected_name
        ]
        if len(matches) != 1:
            raise SourceConfigurationError(
                f"Telegram joined-channel name must resolve exactly once: {expected_name}"
            )
        resolved[expected_name] = matches[0]
    if len(set(resolved.values())) != len(resolved):
        raise SourceConfigurationError("Telegram numeric channel IDs must be unique")
    return resolved


def _credentials() -> tuple[int, str, str]:
    raw_api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    session_path = os.getenv("TELEGRAM_SESSION_PATH", "").strip()
    if not raw_api_id or not api_hash or not session_path:
        raise SourceConfigurationError(
            "TELEGRAM_API_ID, TELEGRAM_API_HASH and TELEGRAM_SESSION_PATH are required"
        )
    try:
        api_id = int(raw_api_id)
    except ValueError as exc:
        raise SourceConfigurationError("TELEGRAM_API_ID must be an integer") from exc
    path = Path(session_path).expanduser()
    if not path.is_absolute():
        raise SourceConfigurationError("TELEGRAM_SESSION_PATH must be absolute")
    if path == BASE_DIR or BASE_DIR in path.parents:
        raise SourceConfigurationError("Telegram session material must stay outside the repo")
    return api_id, api_hash, str(path)


def _build_client() -> Any:
    try:
        from telethon import TelegramClient
    except ImportError as exc:
        raise SourceConfigurationError("Telethon is not installed") from exc
    api_id, api_hash, session_path = _credentials()
    return TelegramClient(
        session_path,
        api_id,
        api_hash,
        receive_updates=False,
        flood_sleep_threshold=0,
    )


def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _version(edit_at: datetime | None) -> str:
    return edit_at.strftime("%Y%m%dT%H%M%S%f") if edit_at else "original"


def _canonical_peer_id(entity: Any) -> int:
    test_peer_id = getattr(entity, "peer_id", None)
    if test_peer_id is not None:
        return int(test_peer_id)
    from telethon import utils

    return int(utils.get_peer_id(entity))


def _normalize_message(
    entity: Any,
    message: Any,
    channel_name: str,
    channel_id: int,
) -> dict[str, Any] | None:
    content = str(getattr(message, "message", "") or "").strip()
    if not content:
        return None
    message_id = int(message.id)
    published_at = _utc_naive(getattr(message, "date", None))
    edit_at = _utc_naive(getattr(message, "edit_date", None))
    username = str(getattr(entity, "username", "") or "").strip()
    title = next((line.strip() for line in content.splitlines() if line.strip()), content)
    return {
        "source": "telegram_mtproto",
        "source_id": (
            f"telegram_mtproto:{channel_id}:{message_id}:{_version(edit_at)}"
        ),
        "author": channel_name,
        "title": title[:240],
        "content": content[:4000],
        "url": f"https://t.me/{username}/{message_id}" if username else None,
        "tags": ["telegram", _slug(channel_name)],
        "score": 0,
        "published_at": published_at,
        "collection_lane": "realtime",
        "source_authority": "secondary",
        "corroboration_state": "unconfirmed",
        "pin_eligibility": "requires_independent_confirmation",
        "review_state": (
            "needs_review"
            if channel_name in LOWER_TRUST_CHANNEL_NAMES
            else "confirmation_required"
        ),
        "provider_channel_id": str(channel_id),
        "provider_message_id": str(message_id),
        "provider_edit_at": edit_at,
        "_timestamp_status": "valid" if published_at else "missing",
    }


async def _fetch_async(
    channel_ids: dict[str, int],
    *,
    message_limit: int,
) -> list[dict[str, Any]]:
    client = _build_client()
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise SourceConfigurationError(
                "Telegram session is not authorized; run the human setup command"
            )
        rows: list[dict[str, Any]] = []
        for expected_name, channel_id in channel_ids.items():
            entity = await client.get_entity(int(channel_id))
            if _canonical_peer_id(entity) != int(channel_id):
                raise SourceConfigurationError(
                    f"Telegram channel pin mismatch: {expected_name} ({channel_id})"
                )
            async for message in client.iter_messages(entity, limit=message_limit):
                normalized = _normalize_message(
                    entity,
                    message,
                    expected_name,
                    int(channel_id),
                )
                if normalized is not None:
                    rows.append(normalized)
        return rows
    except Exception as exc:
        if type(exc).__name__ == "FloodWaitError":
            raise SourceBlockedError(
                "telegram_mtproto provider blocked by FloodWait"
            ) from exc
        raise
    finally:
        await client.disconnect()


def fetch_telegram_messages(
    *,
    channel_ids: dict[str, int],
    message_limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch a bounded recovery window for the pinned channel allowlist."""
    if not isinstance(channel_ids, dict) or not channel_ids:
        raise SourceConfigurationError("Telegram numeric channel allowlist is required")
    if set(channel_ids) != set(APPROVED_CHANNEL_NAMES):
        raise SourceConfigurationError(
            "Telegram channel allowlist must contain exactly the approved seven names"
        )
    try:
        numeric_ids = {name: int(channel_ids[name]) for name in APPROVED_CHANNEL_NAMES}
    except (TypeError, ValueError) as exc:
        raise SourceConfigurationError("Telegram channel IDs must be integers") from exc
    if len(set(numeric_ids.values())) != len(numeric_ids):
        raise SourceConfigurationError("Telegram numeric channel IDs must be unique")
    if message_limit < 1 or message_limit > 200:
        raise SourceConfigurationError("Telegram message_limit must be between 1 and 200")
    return asyncio.run(_fetch_async(numeric_ids, message_limit=message_limit))
