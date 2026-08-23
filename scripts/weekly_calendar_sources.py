"""No-key Weekly calendar discovery snapshots and first-party verification."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from scripts.weekly_finance_newsletter import WeeklyWindow, weekly_window


NASDAQ_BASE = "https://api.nasdaq.com/api/calendar"
_IMPORTANT_MACRO = re.compile(
    r"FOMC|Fed |Federal Reserve|Jackson Hole|CPI|PCE|GDP|Payroll|Employment|"
    r"Unemployment|Jobless|Retail Sales|PMI|Confidence|Durable Goods|Interest Rate|"
    r"Inflation|Trade Balance|Industrial Production|BoJ|ECB|Bank of England|PPI",
    re.I,
)


@dataclass(frozen=True)
class CalendarEvent:
    event_id: str
    kind: str
    event_date: date
    time_gmt: str | None
    country: str | None
    name: str
    provider: str
    consensus: str | None = None
    previous: str | None = None
    description: str | None = None
    symbol: str | None = None
    eps_forecast: str | None = None
    market_cap: float | None = None
    verification_state: str = "discovery_only"
    verified_date: date | None = None
    verified_time_gmt: str | None = None
    verification_source: str | None = None


@dataclass(frozen=True)
class VerifiedSchedule:
    source: str
    event_date: date
    time_gmt: str | None
    name: str


@dataclass(frozen=True)
class CalendarSnapshot:
    provider: str
    kind: str
    requested_date: date
    retrieved_at: str
    response_sha256: str | None
    status: str
    path: Path
    error: str | None = None


@dataclass(frozen=True)
class CalendarBundle:
    events: tuple[CalendarEvent, ...]
    snapshots: tuple[CalendarSnapshot, ...]
    source_status: dict[str, str]


def _response_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _write_snapshot(
    snapshot_dir: Path,
    kind: str,
    requested_date: date,
    payload: Any,
    status: str,
    error: str | None = None,
) -> CalendarSnapshot:
    retrieved_at = datetime.now().astimezone().isoformat(timespec="seconds")
    digest = _response_hash(payload) if status == "ok" else None
    path = snapshot_dir / f"{requested_date.isoformat()}-nasdaq-{kind}.json"
    path.write_text(
        json.dumps(
            {
                "provider": "nasdaq",
                "kind": kind,
                "requested_date": requested_date.isoformat(),
                "retrieved_at": retrieved_at,
                "response_sha256": digest,
                "status": status,
                "error": error,
                "payload": payload,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return CalendarSnapshot("nasdaq", kind, requested_date, retrieved_at, digest, status, path, error)


def _default_fetch_json(url: str) -> dict[str, Any]:
    try:
        response = requests.get(
            url,
            headers={"Accept": "application/json", "User-Agent": "Park-Intel/weekly-finance"},
            timeout=8,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as first_error:
        result = subprocess.run(
            [
                "/usr/bin/curl",
                "--http1.1",
                "-L",
                "--max-time",
                "8",
                "-sS",
                "-A",
                "Park-Intel/weekly-finance",
                "-H",
                "Accept: application/json",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise first_error
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            raise first_error


def _market_cap(value: Any) -> float | None:
    try:
        return float(str(value or "").replace("$", "").replace(",", ""))
    except ValueError:
        return None


def _macro_score(name: str) -> int:
    name = name.lower()
    if re.search(r"fomc|fed |pce|cpi|gdp|interest rate|jackson hole", name):
        return 5
    if re.search(r"payroll|employment|unemployment|inflation|bo[j]?|ecb|pmi", name):
        return 4
    return 2


def _normalize_macro(day: date, row: dict[str, Any]) -> CalendarEvent | None:
    name = str(row.get("eventName") or "").strip()
    country = str(row.get("country") or "").strip() or None
    if not name or not _IMPORTANT_MACRO.search(name):
        return None
    event_id = f"nasdaq:macro:{day.isoformat()}:{country or 'unknown'}:{name}"
    return CalendarEvent(
        event_id=event_id,
        kind="macro",
        event_date=day,
        time_gmt=str(row.get("gmt") or "").strip() or None,
        country=country,
        name=name,
        provider="nasdaq",
        consensus=str(row.get("consensus") or "").strip() or None,
        previous=str(row.get("previous") or "").strip() or None,
        description=str(row.get("description") or "").strip() or None,
    )


def _normalize_earnings(day: date, row: dict[str, Any]) -> CalendarEvent | None:
    symbol = str(row.get("symbol") or "").strip().upper()
    if not symbol:
        return None
    market_cap = _market_cap(row.get("marketCap"))
    if market_cap is None or market_cap < 10_000_000_000:
        return None
    event_id = f"nasdaq:earnings:{day.isoformat()}:{symbol}"
    return CalendarEvent(
        event_id=event_id,
        kind="earnings",
        event_date=day,
        time_gmt=str(row.get("time") or "").strip() or None,
        country=None,
        name=str(row.get("name") or symbol).strip(),
        provider="nasdaq",
        symbol=symbol,
        eps_forecast=str(row.get("epsForecast") or "").strip() or None,
        market_cap=market_cap,
    )


def collect_calendar_bundle(
    window: WeeklyWindow,
    snapshot_dir: Path,
    fetch_json: Callable[[str], dict[str, Any]] | None = None,
) -> CalendarBundle:
    """Fetch the next-week discovery sources and retain every response."""
    fetch = fetch_json or _default_fetch_json
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshots: list[CalendarSnapshot] = []
    macro: dict[str, CalendarEvent] = {}
    earnings: dict[str, CalendarEvent] = {}
    status: dict[str, str] = {"nasdaq:macro": "ok", "nasdaq:earnings": "ok"}
    tasks = [
        (window.watch_start + timedelta(days=offset), kind, normalizer)
        for offset in range(7)
        for kind, normalizer in (("economic-events", _normalize_macro), ("earnings", _normalize_earnings))
    ]

    def fetch_one(task):
        day, kind, normalizer = task
        try:
            return task, fetch(f"{NASDAQ_BASE}/{kind}?date={day.isoformat()}"), None
        except Exception as exc:
            return task, {}, str(exc)[:240]

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(fetch_one, tasks))

    for (day, kind, normalizer), payload, error in results:
        if error is not None:
            source_key = "nasdaq:macro" if kind == "economic-events" else "nasdaq:earnings"
            status[source_key] = "error"
            snapshots.append(_write_snapshot(snapshot_dir, kind, day, payload, "error", error))
            continue
        snapshots.append(_write_snapshot(snapshot_dir, kind, day, payload, "ok"))
        rows = ((payload.get("data") or {}).get("rows")) or []
        target = macro if kind == "economic-events" else earnings
        for row in rows:
            event = normalizer(day, row)
            if event is not None:
                target[event.event_id] = event

    macro_events = sorted(macro.values(), key=lambda event: (-_macro_score(event.name), event.event_date, event.name))[:20]
    earnings_events = sorted(earnings.values(), key=lambda event: (-(event.market_cap or 0), event.event_date, event.symbol or ""))[:20]
    return CalendarBundle(tuple(macro_events + earnings_events), tuple(snapshots), status)


def _name_tokens(name: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", name.lower()) if len(token) >= 3}


def verify_calendar_events(
    events: tuple[CalendarEvent, ...],
    schedules: tuple[VerifiedSchedule, ...],
) -> tuple[CalendarEvent, ...]:
    """Attach first-party verification without trusting discovery dates."""
    verified: list[CalendarEvent] = []
    for event in events:
        event_tokens = _name_tokens(event.name)
        match = next(
            (
                schedule
                for schedule in schedules
                if event_tokens & _name_tokens(schedule.name)
                and abs((schedule.event_date - event.event_date).days) <= 2
            ),
            None,
        )
        if match is None:
            verified.append(replace(event, verification_state="discovery_only", verified_date=None, verified_time_gmt=None, verification_source=None))
        else:
            verified.append(
                replace(
                    event,
                    verification_state="verified",
                    verified_date=match.event_date,
                    verified_time_gmt=match.time_gmt,
                    verification_source=match.source,
                )
            )
    return tuple(verified)


def merge_verified_schedules(
    events: tuple[CalendarEvent, ...],
    schedules: tuple[VerifiedSchedule, ...],
) -> tuple[CalendarEvent, ...]:
    """Add official events that discovery failed to return."""
    output = list(events)
    for schedule in schedules:
        tokens = _name_tokens(schedule.name)
        already_present = any(
            event.kind == "macro"
            and tokens & _name_tokens(event.name)
            and abs((event.event_date - schedule.event_date).days) <= 2
            for event in output
        )
        if already_present:
            continue
        event_id = f"official:{schedule.source}:{schedule.event_date.isoformat()}:{schedule.name}"
        output.append(
            CalendarEvent(
                event_id=event_id,
                kind="macro",
                event_date=schedule.event_date,
                time_gmt=None,
                country="United States" if schedule.source in {"BEA", "Federal Reserve"} else None,
                name=schedule.name,
                provider=schedule.source,
                verification_state="verified",
                verified_date=schedule.event_date,
                verified_time_gmt=schedule.time_gmt,
                verification_source=schedule.source,
            )
        )
    return tuple(output)


def _default_fetch_text(url: str) -> str:
    result = subprocess.run(
        [
            "/usr/bin/curl",
            "--http1.1",
            "-L",
            "--max-time",
            "8",
            "-sS",
            "-A",
            "Park-Intel/weekly-finance",
            "-H",
            "Cache-Control: no-cache",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Park-Intel/weekly-finance"},
            timeout=8,
        )
        response.raise_for_status()
        return response.text
    except requests.RequestException as first_error:
        raise first_error


def _gmt_time(local_time: str, day: date, timezone: str) -> str | None:
    match = re.search(r"(\d{1,2}):(\d{2})\s*([AP])\.?M\.?", local_time, re.I)
    if not match:
        return None
    hour = int(match.group(1)) % 12
    if match.group(3).upper() == "P":
        hour += 12
    local = datetime(day.year, day.month, day.day, hour, int(match.group(2)), tzinfo=ZoneInfo(timezone))
    return local.astimezone(ZoneInfo("UTC")).strftime("%H:%M")


def parse_bea_schedules(html: str, year: int) -> tuple[VerifiedSchedule, ...]:
    soup = BeautifulSoup(html, "html.parser")
    schedules: list[VerifiedSchedule] = []
    for row in soup.select("tr"):
        date_node = row.select_one(".scheduled-date")
        title_node = row.select_one(".release-title")
        if not date_node or not title_node:
            continue
        date_match = re.search(r"([A-Z][a-z]+)\s+(\d{1,2})", date_node.get_text(" ", strip=True))
        if not date_match:
            continue
        try:
            event_day = date(year, datetime.strptime(date_match.group(1), "%B").month, int(date_match.group(2)))
        except ValueError:
            continue
        time_text = date_node.get_text(" ", strip=True)
        schedules.append(
            VerifiedSchedule(
                source="BEA",
                event_date=event_day,
                time_gmt=_gmt_time(time_text, event_day, "America/New_York"),
                name=title_node.get_text(" ", strip=True),
            )
        )
    return tuple(schedules)


def parse_federal_reserve_schedules(html: str, year: int, month: int) -> tuple[VerifiedSchedule, ...]:
    schedules: list[VerifiedSchedule] = []
    row_pattern = re.compile(
        r'<div class=["\']col-xs-2["\']>\s*<p>(?P<time>[^<]+)</p>.*?'
        r'<div class=["\']col-xs-7["\']>(?P<body>.*?)</div>\s*'
        r'<div class=["\']col-xs-3["\']>\s*<p>(?P<day>\d{1,2})</p>',
        re.I | re.S,
    )
    for match in row_pattern.finditer(html):
        body = BeautifulSoup(match.group("body"), "html.parser").get_text(" ", strip=True)
        if "Jackson Hole" not in body and "FOMC" not in body:
            continue
        event_day = date(year, month, int(match.group("day")))
        schedules.append(
            VerifiedSchedule(
                source="Federal Reserve",
                event_date=event_day,
                time_gmt=_gmt_time(match.group("time"), event_day, "America/New_York"),
                name=body,
            )
        )
    return tuple(schedules)


def fetch_official_schedules(
    window: WeeklyWindow,
    fetch_text: Callable[[str], str] | None = None,
) -> tuple[tuple[VerifiedSchedule, ...], dict[str, str]]:
    fetch = fetch_text or _default_fetch_text
    schedules: list[VerifiedSchedule] = []
    status: dict[str, str] = {}
    try:
        schedules.extend(parse_bea_schedules(fetch("https://www.bea.gov/news/schedule"), window.watch_start.year))
        status["official:bea"] = "ok"
    except Exception:
        status["official:bea"] = "error"
    try:
        month_url = f"https://www.federalreserve.gov/newsevents/{window.watch_start.year}-{window.watch_start.month:02d}.htm"
        fed_html = fetch(month_url)
        fed_schedules = parse_federal_reserve_schedules(fed_html, window.watch_start.year, window.watch_start.month)
        if not fed_schedules and fetch_text is None:
            fed_schedules = parse_federal_reserve_schedules(
                _default_fetch_text(month_url), window.watch_start.year, window.watch_start.month
            )
        schedules.extend(fed_schedules)
        status["official:federal_reserve"] = "ok" if fed_schedules else "no_data"
    except Exception:
        status["official:federal_reserve"] = "error"
    schedules = [
        schedule
        for schedule in schedules
        if window.watch_start <= schedule.event_date <= window.watch_end
    ]
    return tuple(schedules), status
