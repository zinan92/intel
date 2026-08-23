"""Tests for Sunday Weekly scheduling and Monday catch-up selection."""

from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo


def test_scheduled_week_ending_targets_sunday_and_monday_only():
    from scripts.run_scheduled_weekly_finance_newsletter import scheduled_week_ending

    sunday = datetime(2026, 8, 23, 8, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    monday = datetime(2026, 8, 24, 8, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    tuesday = datetime(2026, 8, 25, 8, 30, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert scheduled_week_ending(sunday) == date(2026, 8, 23)
    assert scheduled_week_ending(monday) == date(2026, 8, 23)
    assert scheduled_week_ending(tuesday) is None


def test_scheduler_calls_publisher_for_target_week(monkeypatch):
    from scripts import run_scheduled_weekly_finance_newsletter as mod

    calls = []
    monkeypatch.setattr(
        mod,
        "publish_weekly_finance_newsletter",
        lambda week: calls.append(week) or SimpleNamespace(status="published"),
    )
    now = datetime(2026, 8, 24, 8, 30, tzinfo=ZoneInfo("Asia/Shanghai"))

    result = mod.run_scheduled_weekly(now)

    assert result == "published"
    assert calls == [date(2026, 8, 23)]


def test_scheduler_noops_outside_sunday_or_monday(monkeypatch):
    from scripts import run_scheduled_weekly_finance_newsletter as mod

    monkeypatch.setattr(mod, "publish_weekly_finance_newsletter", lambda week: (_ for _ in ()).throw(AssertionError()))
    now = datetime(2026, 8, 25, 8, 30, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert mod.run_scheduled_weekly(now) == "noop"
