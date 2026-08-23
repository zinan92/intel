"""Tests for Weekly Obsidian/Feishu publication and idempotency."""

import json
from datetime import date
from types import SimpleNamespace

import pytest


def _result(markdown="# Weekly Finance Newsletter | 2026-08-23\n"):
    return SimpleNamespace(
        markdown=markdown,
        provider="deepseek-v4-flash",
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
    assert manifest[0]["website_status"] == "not_attempted"


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


def test_weekly_publish_changed_hash_requires_force_resend(tmp_path, monkeypatch):
    from scripts import publish_weekly_finance_newsletter as mod

    responses = [_result("# Weekly Finance Newsletter | v1\n"), _result("# Weekly Finance Newsletter | v2\n")]
    monkeypatch.setattr(mod, "generate_weekly_dry_run", lambda *args, **kwargs: responses.pop(0))
    monkeypatch.setattr(mod, "_send_to_feishu", lambda markdown, archive_path: True)

    mod.publish_weekly_finance_newsletter(date(2026, 8, 23), archive_dir=tmp_path)
    with pytest.raises(mod.WeeklyDeliveryError, match="force-resend"):
        mod.publish_weekly_finance_newsletter(date(2026, 8, 23), archive_dir=tmp_path)


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
