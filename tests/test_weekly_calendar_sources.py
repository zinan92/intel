"""Tests for retained discovery snapshots and official event verification."""

import json
from datetime import date


def _fake_nasdaq_response(url):
    if "economic-events" in url:
        return {
            "data": {
                "rows": [
                    {
                        "gmt": "13:30",
                        "country": "United States",
                        "eventName": "GDP",
                        "consensus": "1.5%",
                        "previous": "1.4%",
                        "description": "Growth release.",
                    }
                ]
            }
        }
    return {
        "data": {
            "rows": [
                {
                    "symbol": "NVDA",
                    "name": "NVIDIA Corporation",
                    "time": "time-after-hours",
                    "epsForecast": "$2.01",
                    "marketCap": "$1000000000000",
                }
            ]
        }
    }


def test_collect_calendar_persists_snapshots_and_stable_candidates(tmp_path):
    from scripts.weekly_calendar_sources import collect_calendar_bundle, weekly_window

    bundle = collect_calendar_bundle(
        weekly_window(date(2026, 8, 23)),
        tmp_path,
        fetch_json=_fake_nasdaq_response,
    )

    assert len(bundle.snapshots) == 14
    assert len(list(tmp_path.glob("*.json"))) == 14
    assert any(event.event_id.startswith("nasdaq:macro:") for event in bundle.events)
    assert any(event.event_id == "nasdaq:earnings:2026-08-24:NVDA" for event in bundle.events)
    snapshot = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert snapshot["provider"] == "nasdaq"
    assert snapshot["response_sha256"]


def test_verification_overrides_discovery_date_and_time():
    from scripts.weekly_calendar_sources import (
        CalendarEvent,
        VerifiedSchedule,
        verify_calendar_events,
    )

    candidate = CalendarEvent(
        event_id="nasdaq:macro:2026-08-27:United States:GDP",
        kind="macro",
        event_date=date(2026, 8, 27),
        time_gmt="13:30",
        country="United States",
        name="GDP",
        consensus="1.5%",
        previous="1.4%",
        provider="nasdaq",
    )
    verified = verify_calendar_events(
        (candidate,),
        (
            VerifiedSchedule(
                source="BEA",
                event_date=date(2026, 8, 26),
                time_gmt="12:30",
                name="GDP (Second Estimate)",
            ),
        ),
    )[0]

    assert verified.verification_state == "verified"
    assert verified.verified_date == date(2026, 8, 26)
    assert verified.verified_time_gmt == "12:30"
    assert verified.verification_source == "BEA"


def test_unmatched_discovery_event_cannot_claim_exact_time():
    from scripts.weekly_calendar_sources import CalendarEvent, verify_calendar_events

    candidate = CalendarEvent(
        event_id="nasdaq:macro:2026-08-28:Japan:Tokyo CPI",
        kind="macro",
        event_date=date(2026, 8, 28),
        time_gmt="19:30",
        country="Japan",
        name="Tokyo CPI",
        consensus="1.8%",
        previous="1.7%",
        provider="nasdaq",
    )

    result = verify_calendar_events((candidate,), ())[0]

    assert result.verification_state == "discovery_only"
    assert result.verified_time_gmt is None


def test_official_schedule_parsers_capture_bea_and_fed_events():
    from scripts.weekly_calendar_sources import parse_bea_schedules, parse_federal_reserve_schedules

    bea = """
    <table><tr><td class='scheduled-date'><div>August 26</div><small>8:30 AM</small></td>
    <td class='release-title'>GDP (Second Estimate) and Corporate Profits</td></tr></table>
    """
    fed = """
    <div class='row'><div class='col-xs-2'><p>10:00 a.m.</p></div>
    <div class='col-xs-7'><p>Speech - Chairman Kevin Warsh</p>
    <p>At the 2026 Jackson Hole Economic Policy Symposium</p></div>
    <div class='col-xs-3'><p>28</p></div></div>
    """

    bea_events = parse_bea_schedules(bea, 2026)
    fed_events = parse_federal_reserve_schedules(fed, 2026, 8)

    assert bea_events[0].event_date == date(2026, 8, 26)
    assert bea_events[0].time_gmt == "12:30"
    assert fed_events[0].event_date == date(2026, 8, 28)
    assert fed_events[0].time_gmt == "14:00"


def test_official_schedule_fills_a_discovery_source_gap():
    from scripts.weekly_calendar_sources import VerifiedSchedule, merge_verified_schedules

    result = merge_verified_schedules(
        (),
        (VerifiedSchedule("BEA", date(2026, 8, 26), "12:30", "GDP (Second Estimate)"),),
    )

    assert len(result) == 1
    assert result[0].event_id.startswith("official:BEA:")
    assert result[0].verification_state == "verified"
