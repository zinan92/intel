"""Tests for Finance Daily Newsletter delivery."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from briefs.models import Brief
from db.models import Base, CollectorRun, SourceRegistry


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_save_to_obsidian_writes_markdown(tmp_path, monkeypatch):
    from scripts.publish_finance_daily_newsletter import save_to_obsidian

    monkeypatch.setenv("OBSIDIAN_FINANCE_NEWSLETTER_DIR", str(tmp_path))
    brief = Brief(
        id=12,
        content="## 今日交易地图\n- 交易含义: test\n\n## Source Health\n- ok",
        article_count=100,
        signal_count=3,
        status="published",
        provider="codex-cli",
        candidate_article_count=100,
        scored_article_count=100,
        scoring_coverage=1.0,
        created_at=datetime(2026, 6, 27, 10, 0, 0),
    )

    path = save_to_obsidian(brief, "- RSS/媒体源: 正常")

    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "brief_id: 12" in content
    assert "provider: codex-cli" in content
    assert "scoring_coverage: 100.0%" in content
    assert "## Source Status" in content
    assert "RSS/媒体源" in content
    assert "今日交易地图" in content


def test_source_health_lines_are_grouped_by_type():
    from scripts.publish_finance_daily_newsletter import _source_health_lines

    session = _session()
    now = datetime.now(timezone.utc)
    session.add_all([
        SourceRegistry(
            source_key="rss:a",
            source_type="rss",
            display_name="RSS A",
            config_json="{}",
            is_active=1,
            expected_freshness_hours=2,
        ),
        SourceRegistry(
            source_key="rss:b",
            source_type="rss",
            display_name="RSS B",
            config_json="{}",
            is_active=0,
            expected_freshness_hours=2,
        ),
        SourceRegistry(
            source_key="xueqiu:main",
            source_type="xueqiu",
            display_name="Xueqiu",
            config_json="{}",
            is_active=0,
            expected_freshness_hours=4,
        ),
    ])
    session.add(CollectorRun(
        source_type="rss",
        source_key="rss:a",
        status="ok",
        articles_fetched=8,
        articles_saved=8,
        duration_ms=100,
        completed_at=now - timedelta(minutes=20),
    ))
    session.commit()

    lines = _source_health_lines(session)
    text = "\n".join(lines)

    assert "RSS/媒体源: 正常" in text
    assert "1 active" in text
    assert "1 inactive" in text
    assert "雪球/A股社交: 未启用" in text


def test_source_health_text_separates_collection_scoring_and_events():
    from scripts.publish_finance_daily_newsletter import _source_health_text

    session = _session()
    now = datetime.now(timezone.utc)
    session.add_all([
        CollectorRun(
            source_type="llm_tagger",
            source_key="llm_tagger:hourly",
            status="ok",
            articles_fetched=20,
            articles_saved=20,
            provider="codex-cli",
            completed_at=now,
        ),
        CollectorRun(
            source_type="event_aggregation",
            source_key="event_aggregation:hourly",
            status="degraded",
            articles_fetched=20,
            articles_saved=0,
            articles_duplicate=0,
            articles_failed=20,
            error_message="zero usable tags",
            completed_at=now,
        ),
    ])
    session.commit()

    text = _source_health_text(session)

    assert "Source health unavailable" in text
    assert "Article scoring: 正常; scored 20/20; provider=codex-cli" in text
    assert "Event aggregation: 降级; usable 0/20; events updated 0" in text


def test_send_to_feishu_can_be_skipped(monkeypatch):
    from scripts.publish_finance_daily_newsletter import send_to_feishu

    monkeypatch.setenv("PARK_INTEL_SKIP_FEISHU", "1")
    brief = Brief(
        id=1,
        content="brief",
        article_count=1,
        signal_count=1,
        created_at=datetime(2026, 6, 27, 10, 0, 0),
    )

    with patch("scripts.publish_finance_daily_newsletter.requests.post") as post:
        sent = send_to_feishu(brief, Path("/tmp/test.md"), "- ok")

    assert sent is False
    post.assert_not_called()


def test_publish_skips_delivery_when_generation_fails(monkeypatch):
    from scripts import publish_finance_daily_newsletter as mod

    session = _session()
    session.add(Brief(
        id=1,
        content="old",
        article_count=1,
        signal_count=1,
        status="published",
        created_at=datetime(2026, 6, 27, 10, 0, 0),
    ))
    session.commit()
    monkeypatch.setenv("PARK_INTEL_SKIP_FEISHU", "1")
    # A failed generation is recorded, but the previous Brief is not archived.
    # Keep this test's manifest outside the real Obsidian vault.
    import tempfile
    manifest_dir = tempfile.TemporaryDirectory()
    monkeypatch.setenv("OBSIDIAN_FINANCE_NEWSLETTER_DIR", manifest_dir.name)

    with patch.object(mod, "generate_brief", return_value=None), \
         patch.object(mod, "get_session", return_value=session), \
         patch.object(mod, "save_to_obsidian") as save:
        result = mod.publish_finance_daily_newsletter(generate=True)

    assert result is None
    save.assert_not_called()
    report_date = datetime.now(mod.BRIEF_TIMEZONE).date().isoformat()
    assert (Path(manifest_dir.name) / ".delivery-manifests" / f"{report_date}-daily.json").exists()
    manifest_dir.cleanup()


def test_generation_failure_without_previous_brief_still_writes_manifest(monkeypatch):
    from scripts import publish_finance_daily_newsletter as mod

    import tempfile
    manifest_dir = tempfile.TemporaryDirectory()
    monkeypatch.setenv("OBSIDIAN_FINANCE_NEWSLETTER_DIR", manifest_dir.name)
    monkeypatch.setenv("PARK_INTEL_SKIP_FEISHU", "1")
    with patch.object(mod, "generate_brief", return_value=None), \
         patch.object(mod, "get_session", return_value=_session()):
        assert mod.publish_finance_daily_newsletter() is None

    report_date = datetime.now(mod.BRIEF_TIMEZONE).date().isoformat()
    assert (Path(manifest_dir.name) / ".delivery-manifests" / f"{report_date}-daily.json").exists()
    manifest_dir.cleanup()


def test_current_publish_runs_scoring_preflight_then_retries_same_window(monkeypatch):
    from scripts import publish_finance_daily_newsletter as mod
    from scripts.generate_narrative_signal import ScoringCoverageError

    session = _session()
    session.add(Brief(
        id=42,
        content="new brief",
        article_count=100,
        signal_count=3,
        status="published",
        provider="codex-cli",
        candidate_article_count=300,
        scored_article_count=300,
        scoring_coverage=1.0,
        created_at=datetime(2026, 9, 4, 0, 0, 0),
    ))
    session.commit()
    failure = ScoringCoverageError(
        eligible_count=276,
        scored_count=174,
        window_start=datetime(2026, 9, 3, 0, 0),
        window_end=datetime(2026, 9, 4, 0, 0),
    )
    generate_calls = []

    def fake_generate(**kwargs):
        generate_calls.append(kwargs)
        if len(generate_calls) == 1:
            raise failure
        return 42

    with patch.object(mod, "generate_brief", side_effect=fake_generate), \
         patch.object(mod, "current_brief_window", return_value=(failure.window_start, failure.window_end, "rolling_24h")), \
         patch.object(mod, "run_tagger") as tagger, \
         patch.object(mod, "get_session", return_value=session), \
         patch.object(mod, "save_to_obsidian", return_value=Path("/tmp/today.md")), \
         patch.object(mod, "send_to_feishu", return_value=False):
        result = mod.publish_finance_daily_newsletter()

    assert result is not None
    assert result.brief_id == 42
    assert len(generate_calls) == 2
    assert generate_calls[0]["window_end"] == failure.window_end
    assert generate_calls[1]["window_end"] == failure.window_end
    assert tagger.call_args.kwargs["window_start"] == failure.window_start
    assert tagger.call_args.kwargs["window_end"] == failure.window_end


def test_current_publish_exposes_scoring_preflight_failure(tmp_path, monkeypatch):
    from scripts import publish_finance_daily_newsletter as mod
    from scripts.generate_narrative_signal import ScoringCoverageError

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 4, 8, 0, tzinfo=tz)

    monkeypatch.setattr(mod, 'datetime', Clock)

    monkeypatch.setenv("OBSIDIAN_FINANCE_NEWSLETTER_DIR", str(tmp_path))
    monkeypatch.setenv("PARK_INTEL_SKIP_FEISHU", "1")
    failure = ScoringCoverageError(
        eligible_count=276,
        scored_count=174,
        window_start=datetime(2026, 9, 3, 0, 0),
        window_end=datetime(2026, 9, 4, 0, 0),
    )
    with patch.object(mod, "generate_brief", side_effect=failure), \
         patch.object(mod, "run_tagger", side_effect=RuntimeError("tagger unavailable")):
        assert mod.publish_finance_daily_newsletter() is None

    manifest = json.loads(
        (tmp_path / ".delivery-manifests" / "2026-09-04-daily.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "generation_failed"
    assert manifest["failure_type"] == "RuntimeError"


def test_successful_delivery_marks_previous_failure_manifest_resolved(tmp_path, monkeypatch):
    from scripts import publish_finance_daily_newsletter as mod

    monkeypatch.setenv("OBSIDIAN_FINANCE_NEWSLETTER_DIR", str(tmp_path))
    manifest_dir = tmp_path / ".delivery-manifests"
    manifest_dir.mkdir()
    (manifest_dir / "2026-09-04-daily.json").write_text(
        json.dumps({
            "report": "finance_daily_newsletter",
            "report_date": "2026-09-04",
            "status": "blocked_scoring_coverage",
            "alert_sent": True,
        }),
        encoding="utf-8",
    )
    session = _session()
    session.add(Brief(
        id=43,
        content="new brief",
        article_count=100,
        signal_count=3,
        status="published",
        provider="codex-cli",
        candidate_article_count=300,
        scored_article_count=300,
        scoring_coverage=1.0,
        created_at=datetime(2026, 9, 4, 0, 0, 0),
    ))
    session.commit()

    with patch.object(mod, "generate_brief", return_value=43), \
         patch.object(mod, "current_brief_window", return_value=(
             datetime(2026, 9, 3, 0, 0), datetime(2026, 9, 4, 0, 0), "rolling_24h",
         )), \
         patch.object(mod, "get_session", return_value=session), \
         patch.object(mod, "save_to_obsidian", return_value=Path("/tmp/today.md")), \
         patch.object(mod, "send_to_feishu", return_value=True):
        result = mod.publish_finance_daily_newsletter()

    assert result is not None
    payload = json.loads((manifest_dir / "2026-09-04-daily.json").read_text(encoding="utf-8"))
    assert payload["status"] == "published"
    assert payload["resolved"] is True
    assert payload["previous_failure_status"] == "blocked_scoring_coverage"
    assert payload["resolved_brief_id"] == 43


def test_generation_failure_writes_manifest_and_alerts_once(tmp_path, monkeypatch):
    from scripts import publish_finance_daily_newsletter as mod

    monkeypatch.setenv("OBSIDIAN_FINANCE_NEWSLETTER_DIR", str(tmp_path))
    failure = RuntimeError("provider unavailable")
    with patch.object(mod, "generate_brief", side_effect=failure), \
         patch.object(mod, "_send_feishu_status") as alert, \
         patch.object(mod, "get_session", return_value=_session()):
        assert mod.publish_finance_daily_newsletter() is None
        assert mod.publish_finance_daily_newsletter() is None

    alert.assert_called_once()
    report_date = datetime.now(mod.BRIEF_TIMEZONE).date().isoformat()
    payload = json.loads(
        (tmp_path / ".delivery-manifests" / f"{report_date}-daily.json").read_text(encoding="utf-8")
    )
    assert payload["status"] == "generation_failed"
    assert payload["alert_sent"] is True


def test_scoring_failure_writes_manifest_and_alerts_once(tmp_path, monkeypatch):
    from scripts import publish_finance_daily_newsletter as mod
    from scripts.generate_narrative_signal import ScoringCoverageError

    monkeypatch.setenv("OBSIDIAN_FINANCE_NEWSLETTER_DIR", str(tmp_path))
    failure = ScoringCoverageError(
        eligible_count=100,
        scored_count=0,
        window_start=datetime(2026, 9, 2, 0, 0, 0),
        window_end=datetime(2026, 9, 3, 0, 0, 0),
    )

    with patch.object(mod, "generate_brief", side_effect=failure), \
         patch.object(mod, "_send_feishu_status") as alert, \
         patch.object(mod, "save_to_obsidian") as save:
        first = mod.publish_finance_daily_newsletter()
        second = mod.publish_finance_daily_newsletter()

    assert first is None
    assert second is None
    save.assert_not_called()
    alert.assert_called_once()
    manifest = tmp_path / ".delivery-manifests" / "2026-09-03-daily.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked_scoring_coverage"
    assert payload["eligible_count"] == 100
    assert payload["scored_count"] == 0
    assert payload["scoring_coverage"] == 0.0
    assert payload["alert_sent"] is True


def test_backfill_archives_historical_brief_without_sending_feishu(monkeypatch):
    from scripts import publish_finance_daily_newsletter as mod

    session = _session()
    historical = Brief(
        id=12,
        content="brief",
        article_count=6,
        signal_count=1,
        status="archived",
        provider="codex-cli",
        created_at=datetime(2026, 8, 26, 0, 0, 0),
    )
    session.add(historical)
    session.commit()

    with patch.object(mod, "generate_brief", return_value=12) as generate, \
         patch.object(mod, "get_session", return_value=session), \
         patch.object(mod, "save_to_obsidian", return_value=Path("/tmp/backfill.md")), \
         patch.object(mod, "send_to_feishu") as send:
        result = mod.publish_finance_daily_newsletter(archive_date=date(2026, 8, 26))

    assert result is not None
    assert result.feishu_sent is False
    assert generate.call_args.kwargs["publish_current"] is False
    assert generate.call_args.kwargs["window_end"] == datetime(2026, 8, 26, 0, 0, 0)
    send.assert_not_called()


def test_recovery_replaces_canonical_archive_after_preserving_backup(tmp_path, monkeypatch):
    from scripts.publish_finance_daily_newsletter import save_to_obsidian

    monkeypatch.setenv("OBSIDIAN_FINANCE_NEWSLETTER_DIR", str(tmp_path))
    canonical = tmp_path / "2026-08-26-finance-daily-newsletter.md"
    canonical.write_text("old unscored archive", encoding="utf-8")
    brief = Brief(
        id=99,
        content="recovered",
        article_count=100,
        signal_count=3,
        provider="codex-cli",
        candidate_article_count=300,
        scored_article_count=300,
        scoring_coverage=1.0,
        created_at=datetime(2026, 8, 26, 0, 0, 0),
    )

    path = save_to_obsidian(brief, "- recovered", replace_existing=True)

    assert path == canonical
    assert "brief_id: 99" in canonical.read_text(encoding="utf-8")
    backups = list((tmp_path / ".recovery-backups").glob("2026-08-26-*.md"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "old unscored archive"
