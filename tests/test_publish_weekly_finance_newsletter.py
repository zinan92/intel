"""Tests for Weekly Obsidian/Feishu publication and idempotency."""

import json
from datetime import date
from types import SimpleNamespace

import pytest


def _result(markdown="# Weekly Finance Newsletter | 2026-08-23\n", provider="deepseek-v4-flash"):
    return SimpleNamespace(
        markdown=markdown,
        provider=provider,
        source_status={"nasdaq:macro": "ok"},
        snapshot_paths=(),
    )


def test_weekly_publish_archives_writes_manifest_and_sends(tmp_path, monkeypatch):
    from scripts import publish_weekly_finance_newsletter as mod

    monkeypatch.setattr(mod, "generate_weekly_dry_run", lambda *args, **kwargs: _result())
    monkeypatch.setattr(mod, "_send_to_feishu", lambda markdown, archive_path: True)

    result = mod.publish_weekly_finance_newsletter(date(2026, 8, 23), archive_dir=tmp_path)

    assert result.status == "published"
    assert result.feishu_sent is True
    assert result.archive_path.exists()
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest[0]["status"] == "published"
    assert manifest[0]["content_sha256"] == result.content_sha256
    assert manifest[0]["model"] == "deepseek-v4-flash"
    assert manifest[0]["website_status"] == "not_attempted"


def test_weekly_publish_records_codex_fallback_provider(tmp_path, monkeypatch):
    from scripts import publish_weekly_finance_newsletter as mod

    monkeypatch.setattr(
        mod,
        "generate_weekly_dry_run",
        lambda *args, **kwargs: _result(provider="codex-cli"),
    )
    monkeypatch.setattr(mod, "_send_to_feishu", lambda markdown, archive_path: True)

    mod.publish_weekly_finance_newsletter(date(2026, 8, 23), archive_dir=tmp_path)

    manifest = json.loads(next(tmp_path.glob(".delivery-manifests/*.json")).read_text(encoding="utf-8"))
    assert manifest[0]["model"] == "codex-cli"


def test_weekly_publish_same_hash_is_noop(tmp_path, monkeypatch):
    from scripts import publish_weekly_finance_newsletter as mod

    monkeypatch.setattr(mod, "generate_weekly_dry_run", lambda *args, **kwargs: _result())
    sends = []
    monkeypatch.setattr(mod, "_send_to_feishu", lambda markdown, archive_path: sends.append(1) or True)

    first = mod.publish_weekly_finance_newsletter(date(2026, 8, 23), archive_dir=tmp_path)
    second = mod.publish_weekly_finance_newsletter(date(2026, 8, 23), archive_dir=tmp_path)

    assert first.status == "published"
    assert second.status == "noop"
    assert len(sends) == 1


def test_weekly_publish_existing_week_noops_without_regenerating(tmp_path, monkeypatch):
    from scripts import publish_weekly_finance_newsletter as mod

    calls = []
    monkeypatch.setattr(mod, "generate_weekly_dry_run", lambda *args, **kwargs: calls.append(1) or _result("# Weekly Finance Newsletter | v1\n"))
    monkeypatch.setattr(mod, "_send_to_feishu", lambda markdown, archive_path: True)

    mod.publish_weekly_finance_newsletter(date(2026, 8, 23), archive_dir=tmp_path)
    result = mod.publish_weekly_finance_newsletter(date(2026, 8, 23), archive_dir=tmp_path)

    assert result.status == "noop"
    assert calls == [1]


def test_weekly_publish_force_resend_creates_a_new_revision(tmp_path, monkeypatch):
    from scripts import publish_weekly_finance_newsletter as mod

    responses = [_result("# Weekly Finance Newsletter | v1\n"), _result("# Weekly Finance Newsletter | v2\n")]
    monkeypatch.setattr(mod, "generate_weekly_dry_run", lambda *args, **kwargs: responses.pop(0))
    sends = []
    monkeypatch.setattr(mod, "_send_to_feishu", lambda markdown, archive_path: sends.append(markdown) or True)

    mod.publish_weekly_finance_newsletter(date(2026, 8, 23), archive_dir=tmp_path)
    result = mod.publish_weekly_finance_newsletter(
        date(2026, 8, 23), archive_dir=tmp_path, force_resend=True
    )

    assert result.status == "published"
    assert len(sends) == 2
    revisions = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert len(revisions) == 2
    assert revisions[0]["content_sha256"] != revisions[1]["content_sha256"]


def test_weekly_recovery_revision_is_idempotent(tmp_path, monkeypatch):
    from scripts import publish_weekly_finance_newsletter as mod

    responses = [_result("# Weekly Finance Newsletter | bad\n"), _result("# Weekly Finance Newsletter | recovered\n")]
    monkeypatch.setattr(mod, "generate_weekly_dry_run", lambda *args, **kwargs: responses.pop(0))
    sends = []
    monkeypatch.setattr(mod, "_send_to_feishu", lambda markdown, archive_path: sends.append(markdown) or True)

    mod.publish_weekly_finance_newsletter(date(2026, 8, 30), archive_dir=tmp_path)
    recovered = mod.publish_weekly_finance_newsletter(
        date(2026, 8, 30),
        archive_dir=tmp_path,
        force_resend=True,
        revision_reason="score-coverage-recovery-94",
    )
    replay = mod.publish_weekly_finance_newsletter(
        date(2026, 8, 30),
        archive_dir=tmp_path,
        force_resend=True,
        revision_reason="score-coverage-recovery-94",
    )

    assert recovered.status == "published"
    assert replay.status == "noop"
    assert len(sends) == 2
    revisions = json.loads(recovered.manifest_path.read_text(encoding="utf-8"))
    assert revisions[-1]["revision_reason"] == "score-coverage-recovery-94"


def test_weekly_publish_feishu_failure_does_not_leave_published_archive(tmp_path, monkeypatch):
    from scripts import publish_weekly_finance_newsletter as mod

    monkeypatch.setattr(mod, "generate_weekly_dry_run", lambda *args, **kwargs: _result())
    monkeypatch.setattr(mod, "_send_to_feishu", lambda markdown, archive_path: (_ for _ in ()).throw(RuntimeError("transport down")))

    with pytest.raises(mod.WeeklyDeliveryError, match="transport down"):
        mod.publish_weekly_finance_newsletter(date(2026, 8, 23), archive_dir=tmp_path)

    assert not list(tmp_path.glob("*finance-weekly-newsletter.md"))
    manifest = next(tmp_path.glob(".delivery-manifests/*.json"))
    assert json.loads(manifest.read_text(encoding="utf-8"))[0]["status"] == "failed"


def test_weekly_publish_dry_run_has_no_user_facing_side_effects(tmp_path, monkeypatch):
    from scripts import publish_weekly_finance_newsletter as mod

    monkeypatch.setattr(mod, "generate_weekly_dry_run", lambda *args, **kwargs: _result())
    monkeypatch.setattr(mod, "_send_to_feishu", lambda markdown, archive_path: (_ for _ in ()).throw(AssertionError("must not send")))

    result = mod.publish_weekly_finance_newsletter(date(2026, 8, 23), archive_dir=tmp_path, dry_run=True)

    assert result.status == "dry_run"
    assert not list(tmp_path.glob("*finance-weekly-newsletter.md"))
    assert not list(tmp_path.glob(".delivery-manifests/*"))
