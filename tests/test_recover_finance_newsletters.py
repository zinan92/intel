"""Tests for bounded Finance Daily/Weekly recovery orchestration."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace


def test_recovery_rescores_only_affected_days_and_replay_is_noop(tmp_path, monkeypatch):
    from scripts import recover_finance_newsletters as mod

    monkeypatch.setenv("OBSIDIAN_FINANCE_NEWSLETTER_DIR", str(tmp_path / "vault"))
    tagged_days = []
    daily_days = []
    weekly_calls = []
    monkeypatch.setattr(mod, "backup_database", lambda _path: tmp_path / "backup.db")
    monkeypatch.setattr(mod, "init_db", lambda: None)

    def fake_tagger(**kwargs):
        tagged_days.append(kwargs["window_end"].date())
        return SimpleNamespace(
            status="ok",
            attempted=300,
            scored=300,
            provider="codex-cli",
            fallback_reason="DeepSeekError",
        )

    def fake_daily(*, archive_date, replace_archive):
        assert replace_archive is True
        daily_days.append(archive_date)
        return SimpleNamespace(
            brief_id=len(daily_days),
            obsidian_path=tmp_path / f"{archive_date}.md",
            feishu_sent=False,
        )

    def fake_weekly(*args, **kwargs):
        weekly_calls.append(kwargs)
        status = "published" if len(weekly_calls) == 1 else "noop"
        return SimpleNamespace(
            status=status,
            archive_path=Path("weekly.md"),
            manifest_path=Path("manifest.json"),
            content_sha256="abc",
            feishu_sent=status == "published",
            source_status={"calendar": "ok"},
        )

    monkeypatch.setattr(mod, "run_tagger", fake_tagger)
    monkeypatch.setattr(mod, "publish_finance_daily_newsletter", fake_daily)
    monkeypatch.setattr(mod, "publish_weekly_finance_newsletter", fake_weekly)
    monkeypatch.setattr(mod, "_brief_metadata", lambda _brief_id: {
        "synthesis_provider": "codex-cli",
        "candidate_articles": 300,
        "scored_articles": 300,
        "scoring_coverage": 1.0,
    })

    receipt_path = tmp_path / "receipt.json"
    receipt = mod.recover_finance_newsletters(
        week_ending=date(2026, 8, 30),
        affected_start=date(2026, 8, 26),
        receipt_path=receipt_path,
    )

    assert tagged_days == [date(2026, 8, day) for day in range(26, 31)]
    assert daily_days == [date(2026, 8, day) for day in range(26, 31)]
    assert all(row["feishu_sent"] is False for row in receipt["daily"])
    assert weekly_calls[0]["revision_reason"] == mod.RECOVERY_REASON
    assert weekly_calls[1]["revision_reason"] == mod.RECOVERY_REASON
    assert receipt["weekly"]["feishu_sent"] is True
    assert receipt["replay_status"] == "noop"
    assert receipt["status"] == "complete"
    assert receipt_path.exists()


def test_recovery_uses_complete_canonical_archives_when_receipt_is_missing(tmp_path, monkeypatch):
    from scripts import recover_finance_newsletters as mod

    monkeypatch.setenv("OBSIDIAN_FINANCE_NEWSLETTER_DIR", str(tmp_path))
    for day in range(26, 31):
        (tmp_path / f"2026-08-{day}-finance-daily-newsletter.md").write_text(
            "---\nbrief_id: 9\nprovider: codex-cli\nscoring_coverage: 100.0%\n"
            "scored_articles: 280/280\n---\n\narchive\n",
            encoding="utf-8",
        )
    monkeypatch.setattr(mod, "backup_database", lambda _path: tmp_path / "backup.db")
    monkeypatch.setattr(mod, "init_db", lambda: None)
    monkeypatch.setattr(mod, "run_tagger", lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not rescore")))
    monkeypatch.setattr(mod, "publish_finance_daily_newsletter", lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not rebuild")))
    monkeypatch.setattr(mod, "publish_weekly_finance_newsletter", lambda *args, **kwargs: SimpleNamespace(
        status="noop", archive_path=Path("weekly.md"), manifest_path=Path("manifest.json"),
        content_sha256="hash", feishu_sent=False, source_status={},
    ))
    monkeypatch.setattr(mod, "_residual_gaps", lambda: [])

    receipt = mod.recover_finance_newsletters(
        week_ending=date(2026, 8, 30),
        affected_start=date(2026, 8, 26),
        receipt_path=tmp_path / "missing-receipt.json",
    )

    assert receipt["status"] == "complete"
    assert [row["tagger_status"] for row in receipt["daily"]] == ["preserved_existing"] * 5
