"""Tests for user-facing brief quality gates."""

from scripts.brief_quality import validate_published_brief


VALID_BRIEF = """
🎯 Daily Trader Brief — 2026-06-27 09:00 UTC
覆盖窗口：2026-06-26 09:00 UTC - 2026-06-27 09:00 UTC

## 今日交易地图
- AI算力：方向 偏多；相关标的 光模块/服务器；置信度 高；交易含义是关注订单兑现。

## 过去24小时发生了什么
1. **国产服务器订单加速落地** | 高 确信度 | 1-3个月
   → 光模块/服务器: 运营商服务器订单和出口数据同步走强。
   → 交易含义: 今天看光模块和服务器链是否继续放量，如果板块只高开低走，就说明资金已经提前反应。
   → 证据性质: 公司公告/订单数据。
2. **高 beta 资产风险偏好回落** | 中 确信度 | 短期
   → BTC/山寨币: 风险资产承压，资金更偏向有订单、有业绩支撑的硬件方向。
   → 交易含义: 不追纯情绪反弹，等待重新站回关键位后再看右侧确认。
   → 证据性质: 价格动作/市场情绪。

## A股映射
- AI算力需求 → 光模块、服务器、电子布：看成交额和涨停扩散。
- 存储涨价 → 国内存储链：看是否从龙头扩散到材料和设备。

## 今天不该追的东西
- 纯直播标题和无描述项目：缺少交易证据，降权。

⚡️ 跨叙事关联
• 算力、存储、光模块共同指向硬件供给紧张。

## Source Health
- 核心来源覆盖正常，单个低质量聚合源已降权。
"""


def test_validate_published_brief_accepts_trader_facing_contract():
    result = validate_published_brief(VALID_BRIEF)
    assert result.passed


def test_validate_published_brief_rejects_internal_fields():
    content = VALID_BRIEF + "\n数据源: rss, google_news | 信号比: 4/6\n[score=5] tags: ai narrative: ai-capex\nrolling_24h\n"
    result = validate_published_brief(content)
    assert not result.passed
    assert any("internal" in issue or "source plumbing" in issue for issue in result.issues)


def test_validate_published_brief_rejects_stale_gold_breakout_fact():
    content = VALID_BRIEF + "\n2. **黄金突破5,000美元创record high** | 高 确信度 | 即时\n"
    result = validate_published_brief(content)
    assert not result.passed
    assert any("gold" in issue for issue in result.issues)


def test_validate_published_brief_requires_trader_sections():
    result = validate_published_brief("Only a short summary without sections.")
    assert not result.passed
    assert any("missing trader-facing sections" in issue for issue in result.issues)
