"""Tests for Finance Daily Newsletter delivery."""
from datetime import datetime, timedelta, timezone
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
        created_at=datetime(2026, 6, 27, 10, 0, 0),
    )

    path = save_to_obsidian(brief, "- RSS/媒体源: 正常")

    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "brief_id: 12" in content
    assert "provider: codex-cli" in content
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

    with patch.object(mod, "generate_brief", return_value=None), \
         patch.object(mod, "get_session", return_value=session), \
         patch.object(mod, "save_to_obsidian") as save:
        result = mod.publish_finance_daily_newsletter(generate=True)

    assert result is None
    save.assert_not_called()
