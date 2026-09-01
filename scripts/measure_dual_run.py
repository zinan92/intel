#!/usr/bin/env python3
"""Print or write a bounded hourly/realtime dual-run evidence receipt."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import get_session
from dual_run.receipt import build_dual_run_receipt, run_live_smoke


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=float, default=1.0, help="Receipt window length (default: 1h)")
    parser.add_argument("--start", type=_parse_datetime, help="UTC/ISO window start")
    parser.add_argument("--end", type=_parse_datetime, help="UTC/ISO window end (default: now)")
    parser.add_argument("--live-smoke", action="store_true", help="Call CLS and Eastmoney once without saving responses")
    parser.add_argument("--output", type=Path, help="Write JSON receipt to this path")
    args = parser.parse_args()

    end = args.end or datetime.now(timezone.utc)
    start = args.start or (end - timedelta(hours=args.hours))
    session = get_session()
    try:
        receipt = build_dual_run_receipt(session, window_start=start, window_end=end)
    finally:
        session.close()
    if args.live_smoke:
        receipt["live_smoke"] = run_live_smoke()

    rendered = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
