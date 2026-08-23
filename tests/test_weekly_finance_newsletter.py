"""Acceptance tests for the Weekly Finance retrospective dry-run seam."""

import json
from datetime import date

import pytest


def _write_daily_archive(directory, day: str, body: str = ""):
    path = directory / f"{day}-finance-daily-newsletter.md"
    path.write_text(
        f"---\ntitle: 财经日报 {day}\nbrief_id: daily-{day}\n---\n\n"
        f"## 今日交易地图\n\n{body or '## 过去24小时发生了什么\n\n市场观察。'}\n",
        encoding="utf-8",
    )
    return path


def _seed_week(directory, missing=()):
    for day in range(17, 24):
        value = f"## 过去24小时发生了什么\n\n黄金约 $4,500；AI Cloud 增长 45%。"
        if f"2026-08-{day:02d}" not in missing:
            _write_daily_archive(directory, f"2026-08-{day:02d}", value)


def _valid_model_response():
    return json.dumps(
        {
            "lookback_themes": [
                {
                    "title": "硬资产重估",
                    "summary": "黄金约 $4,500，AI Cloud 增长 45%。",
                    "causal_chain": "美元走弱推动硬资产重估。",
                    "affected_assets": ["Gold", "BTC"],
                    "confirmation_signal": "黄金守住 $4,500。",
                    "invalidation_signal": "美元反弹。",
                    "source_refs": ["daily:2026-08-17"],
                },
                {
                    "title": "AI 商业化",
                    "summary": "AI Cloud 增长 45%，但安全风险上升。",
                    "causal_chain": "需求增长与安全风险并行。",
                    "affected_assets": ["NVDA"],
                    "confirmation_signal": "订单指引继续上修。",
                    "invalidation_signal": "监管实质收紧。",
                    "source_refs": ["daily:2026-08-18"],
                },
            ],
            "source_health": "Daily archive coverage is complete.",
        }
    )


def test_weekly_window_requires_sunday_and_sets_adjacent_windows():
    from scripts.weekly_finance_newsletter import weekly_window

    window = weekly_window(date(2026, 8, 23))

    assert window.lookback_start == date(2026, 8, 17)
    assert window.lookback_end == date(2026, 8, 23)
    assert window.watch_start == date(2026, 8, 24)
    assert window.watch_end == date(2026, 8, 30)

    with pytest.raises(ValueError, match="Sunday"):
        weekly_window(date(2026, 8, 24))


def test_weekly_dry_run_renders_from_seven_archives_without_side_effects(tmp_path, monkeypatch):
    from scripts import weekly_finance_newsletter as mod

    _seed_week(tmp_path)
    monkeypatch.setattr(mod, "_call_deepseek", lambda prompt: (_valid_model_response(), "deepseek-v4-flash"))

    result = mod.generate_weekly_dry_run(date(2026, 8, 23), tmp_path)

    assert result.coverage_status == "complete"
    assert result.daily_count == 7
    assert "What happened last week" in result.markdown
    assert "Things to watch for next week" in result.markdown
    assert "Source Status" in result.markdown
    assert "Calendar discovery is not connected" in result.markdown
    assert not list(tmp_path.glob("*weekly*"))


def test_weekly_coverage_degrades_and_fails_closed(tmp_path):
    from scripts import weekly_finance_newsletter as mod

    degraded_dir = tmp_path / "degraded"
    degraded_dir.mkdir()
    _seed_week(degraded_dir, missing=("2026-08-23",))
    result = mod.load_weekly_archives(date(2026, 8, 23), degraded_dir)
    assert result.coverage_status == "degraded"
    assert result.daily_count == 6

    insufficient_dir = tmp_path / "insufficient"
    insufficient_dir.mkdir()
    _seed_week(insufficient_dir, missing=("2026-08-18", "2026-08-19", "2026-08-20"))
    result = mod.load_weekly_archives(date(2026, 8, 23), insufficient_dir)
    assert result.coverage_status == "insufficient"
    assert result.daily_count == 4


def test_weekly_quality_rejects_unreferenced_claims():
    from scripts.weekly_finance_newsletter import validate_weekly_draft

    draft = json.loads(_valid_model_response())
    draft["lookback_themes"][0]["source_refs"] = ["daily:missing"]

    result = validate_weekly_draft(draft, {"daily:2026-08-17": "黄金约 $4,500"})

    assert not result.passed
    assert any("source" in issue for issue in result.issues)


def test_weekly_quality_rejects_altered_numeric_claims():
    from scripts.weekly_finance_newsletter import validate_weekly_draft

    draft = json.loads(_valid_model_response())
    draft["lookback_themes"][0]["summary"] = "黄金约 $4,700。"

    result = validate_weekly_draft(draft, {"daily:2026-08-17": "黄金约 $4,500"})

    assert not result.passed
    assert any("numeric" in issue for issue in result.issues)


def test_weekly_numeric_grounding_handles_suffixes_and_sentence_punctuation():
    from scripts.weekly_finance_newsletter import validate_weekly_draft

    draft = json.loads(_valid_model_response())
    draft["lookback_themes"][0]["summary"] = "黄金约 $4,500."
    draft["lookback_themes"][1]["summary"] = "AI Cloud 增长 45%。"

    result = validate_weekly_draft(
        draft,
        {"daily:2026-08-17": "黄金约 $4,500。", "daily:2026-08-18": "AI Cloud 增长 45%。"},
    )

    assert result.passed


def test_weekly_dry_run_repairs_a_bad_model_draft_once(tmp_path, monkeypatch):
    from scripts import weekly_finance_newsletter as mod

    _seed_week(tmp_path)
    invalid = json.loads(_valid_model_response())
    invalid["lookback_themes"][0]["summary"] = "黄金约 $4,700。"
    responses = [json.dumps(invalid), _valid_model_response()]
    calls = []

    def fake_call(prompt):
        calls.append(prompt)
        return responses.pop(0), "deepseek-v4-flash"

    monkeypatch.setattr(mod, "_call_deepseek", fake_call)

    result = mod.generate_weekly_dry_run(date(2026, 8, 23), tmp_path)

    assert result.coverage_status == "complete"
    assert len(calls) == 2
    assert "numeric" in calls[1]


def test_weekly_dry_run_repairs_an_oversized_model_draft_once(tmp_path, monkeypatch):
    from scripts import weekly_finance_newsletter as mod

    _seed_week(tmp_path)
    oversized = json.loads(_valid_model_response())
    oversized["lookback_themes"][0]["summary"] = "x" * 5000
    responses = [json.dumps(oversized), _valid_model_response()]
    calls = []

    def fake_call(prompt):
        calls.append(prompt)
        return responses.pop(0), "deepseek-v4-flash"

    monkeypatch.setattr(mod, "_call_deepseek", fake_call)

    result = mod.generate_weekly_dry_run(date(2026, 8, 23), tmp_path)

    assert len(result.markdown) <= mod.MAX_WEEKLY_MARKDOWN_CHARS
    assert len(calls) == 2
    assert "length" in calls[1]


def test_weekly_dry_run_renders_verified_and_discovery_watchlists(tmp_path, monkeypatch):
    from scripts import weekly_finance_newsletter as mod
    from scripts.weekly_calendar_sources import CalendarBundle, CalendarEvent

    _seed_week(tmp_path)
    macro = CalendarEvent(
        event_id="nasdaq:macro:2026-08-26:United States:GDP",
        kind="macro",
        event_date=date(2026, 8, 26),
        time_gmt="12:30",
        country="United States",
        name="GDP (Second Estimate)",
        consensus="1.5%",
        previous="1.4%",
        provider="nasdaq",
        verification_state="verified",
        verified_date=date(2026, 8, 26),
        verified_time_gmt="12:30",
        verification_source="BEA",
    )
    earnings = CalendarEvent(
        event_id="nasdaq:earnings:2026-08-26:NVDA",
        kind="earnings",
        event_date=date(2026, 8, 26),
        time_gmt=None,
        country=None,
        name="NVIDIA Corporation",
        symbol="NVDA",
        eps_forecast="$2.01",
        provider="nasdaq",
    )
    bundle = CalendarBundle(
        events=(macro, earnings),
        snapshots=(),
        source_status={"nasdaq": "ok"},
    )
    draft = json.loads(_valid_model_response())
    draft["watchlist"] = [
        {
            "title": "美国 GDP",
            "why_it_matters": "验证增长与利率路径。",
            "affected_assets": ["USD", "Gold"],
            "surprise_upside": "高于预期推升收益率。",
            "surprise_downside": "低于预期利好长债。",
            "source_refs": [macro.event_id],
        }
    ]
    draft["earnings"] = [
        {
            "title": "NVDA 财报",
            "why_it_matters": "验证 AI capex。",
            "affected_assets": ["NVDA"],
            "surprise_upside": "指引上修。",
            "surprise_downside": "需求指引转弱。",
            "source_refs": [earnings.event_id],
        }
    ]
    monkeypatch.setattr(mod, "_call_deepseek", lambda prompt: (json.dumps(draft), "deepseek-v4-flash"))

    result = mod.generate_weekly_dry_run(date(2026, 8, 23), tmp_path, calendar_bundle=bundle)

    assert "GDP (Second Estimate)" in result.markdown
    assert "verified" in result.markdown
    assert "NVDA" in result.markdown
    assert len(result.markdown) <= mod.MAX_WEEKLY_MARKDOWN_CHARS
    assert "NVIDIA Corporation" not in result.markdown.split("### Major earnings")[0]


def test_weekly_quality_rejects_earnings_in_macro_watchlist():
    from scripts import weekly_finance_newsletter as mod
    from scripts.weekly_calendar_sources import CalendarEvent

    draft = json.loads(_valid_model_response())
    earnings = CalendarEvent(
        event_id="nasdaq:earnings:2026-08-26:NVDA",
        kind="earnings",
        event_date=date(2026, 8, 26),
        time_gmt="time-after-hours",
        country=None,
        name="NVIDIA Corporation",
        provider="nasdaq",
        symbol="NVDA",
    )
    draft["watchlist"] = [{
        "title": "NVDA",
        "why_it_matters": "财报验证 AI capex。",
        "affected_assets": ["NVDA"],
        "surprise_upside": "指引上修。",
        "surprise_downside": "指引转弱。",
        "source_refs": [earnings.event_id],
    }]
    draft["earnings"] = []

    result = mod.validate_weekly_draft(
        draft,
        {"daily:2026-08-17": "黄金约 $4,500"},
        (earnings,),
    )

    assert not result.passed
    assert any("wrong event kind" in issue for issue in result.issues)
