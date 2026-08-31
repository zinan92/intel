"""Tests for narrative signal brief generation."""
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from briefs.models import Brief
from db.models import Article, Base, SourceRegistry


VALID_BRIEF = """
🎯 Daily Trader Brief — 2026-06-27 09:00 UTC
覆盖窗口：2026-06-26 09:00 UTC - 2026-06-27 09:00 UTC

## 今日交易地图
- AI算力：方向 偏多；相关标的 光模块/服务器；置信度 高；交易含义是关注订单兑现。
- Crypto：方向 偏空；相关标的 BTC/山寨币；置信度 中；交易含义是避免追高高 beta。

## 过去24小时发生了什么
1. **国产服务器订单加速落地** | 高 确信度 | 1-3个月
   → 光模块/服务器: 运营商服务器订单和出口数据同步走强，说明算力硬件链仍在兑现。
   → 交易含义: 今天看光模块和服务器链是否继续放量，确认资金是否还在硬件端。
   → 证据性质: 公司公告/订单数据。
2. **加密资产风险偏好回落** | 中 确信度 | 短期
   → BTC/山寨币: 高 beta 资产承压，资金更偏向有订单的 AI 硬件。
   → 交易含义: 降低纯投机资产权重，等待重新站回关键位。
   → 证据性质: 价格动作/市场情绪。

## A股映射
- AI算力需求 → 光模块、服务器、电子布：看成交额和涨停扩散。

## 今天不该追的东西
- 纯直播标题和无描述项目：缺少交易证据，降权。

⚡️ 跨叙事关联
• 算力、存储、光模块共同指向硬件供给紧张。
• Crypto 回调和 AI 硬件走强形成资金跷跷板。

## Source Health
- 核心来源覆盖正常，低质量聚合源已降权。
"""


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_articles(session, count=6):
    now = datetime.utcnow()
    for idx in range(count):
        session.add(Article(
            source="rss",
            source_id=f"fresh_{idx}",
            title=f"Fresh market article {idx}",
            content="Important market-moving detail " * 10,
            relevance_score=4,
            published_at=now - timedelta(hours=idx + 1),
            collected_at=now - timedelta(hours=idx + 1),
        ))
    session.commit()


def test_current_brief_window_is_rolling_24h():
    from scripts.generate_narrative_signal import current_brief_window

    now = datetime(2026, 6, 27, 9, 0, 0)
    start, end, slot = current_brief_window(now)

    assert slot == "rolling_24h"
    assert end == now
    assert start == now - timedelta(hours=24)


def test_deepseek_reads_api_key_from_configured_secret_file(tmp_path, monkeypatch):
    from scripts.generate_narrative_signal import _deepseek_api_key

    test_key = "sk-" + "test-key"
    secret_file = tmp_path / "deepseek.md"
    secret_file.write_text(f"DEEPSEEK_API_KEY={test_key}", encoding="utf-8")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY_FILE", str(secret_file))

    assert _deepseek_api_key() == test_key


def test_call_deepseek_uses_expected_request_shape(monkeypatch):
    from scripts import generate_narrative_signal as mod

    test_key = "sk-" + "test-key"
    monkeypatch.setenv("DEEPSEEK_API_KEY", test_key)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)

    with patch.object(mod.requests, "post") as post:
        post.return_value.json.return_value = {
            "model": "deepseek-v4-flash",
            "choices": [{"message": {"content": "generated brief"}}],
        }
        content, model = mod._call_deepseek("write a brief")

    assert (content, model) == ("generated brief", "deepseek-v4-flash")
    assert post.call_args.kwargs["json"]["model"] == "deepseek-v4-flash"
    assert post.call_args.kwargs["json"]["thinking"] == {"type": "disabled"}
    assert post.call_args.kwargs["headers"]["Authorization"] == f"Bearer {test_key}"
    post.return_value.raise_for_status.assert_called_once()


def test_call_deepseek_rejects_malformed_response(monkeypatch):
    from scripts import generate_narrative_signal as mod

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-" + "test-key")
    with patch.object(mod.requests, "post") as post:
        post.return_value.json.return_value = {"choices": []}
        assert mod._call_deepseek("write a brief") == (None, None)


def test_call_llm_falls_back_to_codex_after_deepseek_failure(monkeypatch):
    from scripts import generate_narrative_signal as mod

    def fail_deepseek(_prompt):
        mod._last_deepseek_failure = "http_402"
        return None, None

    monkeypatch.setattr(mod, "_call_deepseek", fail_deepseek)
    monkeypatch.setattr(mod, "_call_codex", lambda _prompt: ("codex brief", "codex-cli"))

    assert mod._call_llm("write a brief") == ("codex brief", "codex-cli")


def test_call_llm_reports_both_provider_failure_without_content(monkeypatch, caplog):
    from scripts import generate_narrative_signal as mod

    def fail_deepseek(_prompt):
        mod._last_deepseek_failure = "http_402"
        return None, None

    def fail_codex(_prompt):
        mod._last_codex_failure = "timeout"
        return None, None

    monkeypatch.setattr(mod, "_call_deepseek", fail_deepseek)
    monkeypatch.setattr(mod, "_call_codex", fail_codex)

    assert mod._call_llm("write a brief") == (None, None)
    assert "Both DeepSeek and Codex CLI failed" in caplog.text
    assert "deepseek=http_402" in caplog.text
    assert "codex=timeout" in caplog.text


def test_call_llm_does_not_fallback_for_non_quota_deepseek_failure(monkeypatch, caplog):
    from scripts import generate_narrative_signal as mod

    calls = []

    def fail_deepseek(_prompt):
        mod._last_deepseek_failure = "transport_error"
        return None, None

    monkeypatch.setattr(mod, "_call_deepseek", fail_deepseek)
    monkeypatch.setattr(mod, "_call_codex", lambda _prompt: calls.append(True) or ("unexpected", "codex-cli"))

    assert mod._call_llm("write a brief") == (None, None)
    assert calls == []
    assert "Codex fallback is not allowed (transport_error)" in caplog.text


def test_call_deepseek_records_http_402(monkeypatch):
    from scripts import generate_narrative_signal as mod

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-" + "test-key")
    response = type("Response", (), {"status_code": 402})()
    with patch.object(mod.requests, "post") as post:
        post.return_value.raise_for_status.side_effect = mod.requests.HTTPError(response=response)

        assert mod._call_deepseek("write a brief") == (None, None)

    assert mod._last_deepseek_failure == "http_402"


def test_call_codex_uses_isolated_stdin_prompt(monkeypatch):
    from scripts import generate_narrative_signal as mod

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        output_path = command[command.index("--output-last-message") + 1]
        Path(output_path).write_text("codex brief", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(mod, "_resolve_codex_executable", lambda: "/opt/homebrew/bin/codex")
    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    assert mod._call_codex("frozen prompt") == ("codex brief", "codex-cli")
    assert captured["command"][-1] == "-"
    assert "--ignore-user-config" in captured["command"]
    assert "frozen prompt" in captured["kwargs"]["input"]


def test_select_publishable_articles_filters_stale_noise_and_dedups():
    from scripts.generate_narrative_signal import _select_publishable_articles

    now = datetime.utcnow()
    fresh_low = Article(
        source="rss", source_id="a", title="Same Market Story",
        relevance_score=2, published_at=now - timedelta(hours=2), collected_at=now - timedelta(hours=2),
    )
    fresh_high = Article(
        source="google_news", source_id="b", title="Same Market Story - Outlet",
        relevance_score=5, published_at=now - timedelta(hours=1), collected_at=now - timedelta(hours=1),
    )
    stale = Article(
        source="google_news", source_id="c", title="Old Story",
        relevance_score=5, published_at=now - timedelta(days=10), collected_at=now - timedelta(hours=1),
    )
    noise = Article(
        source="github_trending", source_id="d", title="AI - No description available",
        relevance_score=5, published_at=now - timedelta(hours=1), collected_at=now - timedelta(hours=1),
    )

    selected = _select_publishable_articles(
        [fresh_low, fresh_high, stale, noise],
        now - timedelta(hours=24),
        now,
        10,
    )

    assert selected == [fresh_high]


def test_source_health_summary_surfaces_disabled_trade_sources():
    from scripts import generate_narrative_signal as mod

    session = _session()
    now = datetime.utcnow()
    session.add_all([
        SourceRegistry(
            source_key="xueqiu:main",
            source_type="xueqiu",
            display_name="Xueqiu",
            config_json="{}",
            is_active=0,
        ),
        SourceRegistry(
            source_key="social_kol:curated-stream",
            source_type="social_kol",
            display_name="Curated Social KOL",
            config_json="{}",
            is_active=0,
        ),
        SourceRegistry(
            source_key="rss:test",
            source_type="rss",
            display_name="RSS",
            config_json="{}",
            is_active=1,
        ),
    ])
    session.add(Article(
        source="rss",
        source_id="fresh",
        title="Fresh market article",
        content="Important market-moving detail",
        relevance_score=4,
        published_at=now - timedelta(hours=1),
        collected_at=now - timedelta(hours=1),
    ))
    session.commit()

    summary = mod._source_health_summary(session, now - timedelta(hours=24), now)

    assert "A股社交" in summary
    assert "全球KOL" in summary
    assert "未启用" in summary
    assert "xueqiu" not in summary
    assert "social_kol" not in summary


def test_generate_brief_rejects_invalid_output_without_publishing():
    from scripts import generate_narrative_signal as mod

    session = _session()
    _seed_articles(session)

    with patch.object(mod, "init_db", return_value=None), \
         patch.object(mod, "get_session", return_value=session), \
         patch.object(mod, "_call_llm", return_value=("数据源: rss\n[score=5] tags: ai\n", "test")):
        brief_id = mod.generate_brief(limit=10)

    assert brief_id is None
    rows = session.query(Brief).all()
    assert len(rows) == 1
    assert rows[0].status == "rejected"


def test_generate_brief_publishes_only_after_quality_passes():
    from scripts import generate_narrative_signal as mod

    session = _session()
    _seed_articles(session)
    session.add(Brief(content=VALID_BRIEF, article_count=1, signal_count=1, status="published"))
    session.commit()

    with patch.object(mod, "init_db", return_value=None), \
         patch.object(mod, "get_session", return_value=session), \
         patch.object(mod, "_call_llm", return_value=(VALID_BRIEF, "test")):
        brief_id = mod.generate_brief(limit=10)

    assert brief_id is not None
    rows = session.query(Brief).order_by(Brief.id).all()
    assert [row.status for row in rows] == ["archived", "published"]
    assert rows[1].provider == "test"
