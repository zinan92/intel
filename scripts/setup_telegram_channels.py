#!/usr/bin/env python3
"""Human-operated Telegram authorization and numeric channel-ID pinning."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.telegram_mtproto import (  # noqa: E402
    _credentials,
    resolve_approved_channel_ids,
)


async def _discover_joined_channels() -> dict[str, int]:
    from telethon import TelegramClient
    from telethon.tl.types import Channel

    api_id, api_hash, session_path = _credentials()
    client = TelegramClient(session_path, api_id, api_hash, receive_updates=False)
    await client.start()
    try:
        account = await client.get_me()
        if getattr(account, "bot", False):
            raise RuntimeError("Telegram setup requires a user account, not a bot")
        joined: list[tuple[str, int]] = []
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if isinstance(entity, Channel):
                joined.append((str(entity.title or "").strip(), int(entity.id)))
        return resolve_approved_channel_ids(joined)
    finally:
        await client.disconnect()


def _persist_channel_ids(channel_ids: dict[str, int]) -> None:
    from db.database import get_session, init_db
    from sources.registry import get_source_by_key

    init_db()
    session = get_session()
    try:
        source = get_source_by_key(session, "telegram_mtproto:approved-channels")
        if source is None:
            raise RuntimeError("Telegram source registry row is missing")
        config = json.loads(source.config_json)
        config["channel_ids"] = channel_ids
        source.config_json = json.dumps(config, ensure_ascii=False, sort_keys=True)
        source.is_active = 1
        session.commit()
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--approve",
        action="store_true",
        help="Persist the displayed numeric-ID mapping after operator inspection",
    )
    args = parser.parse_args()
    channel_ids = asyncio.run(_discover_joined_channels())
    print(json.dumps(channel_ids, ensure_ascii=False, indent=2))
    if not args.approve:
        print("Mapping not saved. Inspect it, then rerun with --approve.")
        return
    _persist_channel_ids(channel_ids)
    print(
        "Approved Telegram numeric channel allowlist saved. "
        "Restart park-intel to register the source job."
    )


if __name__ == "__main__":
    main()
