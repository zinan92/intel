"""Behavioral tests for the v6 Park Exposure Registry seam."""

import json
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import Article, Base
from triage.exposure import match_article_exposure


def _target_ids(match):
    return {target["id"] for target in match.targets}


def _target(match, target_id):
    return next(target for target in match.targets if target["id"] == target_id)


def test_ai_entity_and_theme_news_are_retained_with_identity():
    match = match_article_exposure(
        "OpenAI 将开发人形机器人，GPU 云需求继续上升",
        "",
        [],
    )

    assert match.status == "matched"
    assert {"openai", "ai-development", "ai-compute", "embodied-ai"} <= _target_ids(match)


def test_unlisted_ai_company_has_no_fabricated_market_code():
    match = match_article_exposure("Anthropic 发布 Claude 新模型", "", [])

    anthropic = _target(match, "anthropic")
    assert anthropic["type"] == "company"
    assert anthropic["listed"] is False
    assert "market" not in anthropic


def test_listed_hk_ai_company_keeps_market_identity():
    match = match_article_exposure("MiniMax 发布新模型并扩大 API 服务", "", [])

    minimax = _target(match, "00100")
    assert minimax["type"] == "company"
    assert minimax["listed"] is True
    assert minimax["market"] == "HK"


def test_cn_company_keeps_entity_id_and_ticker_separate():
    match = match_article_exposure("中际旭创发布光通信订单进展", "", [])

    target = _target(match, "中际旭创")
    assert target["id"] == "中际旭创"
    assert target["ticker"] == "300308"
    assert target["market"] == "CN"


def test_proxy_terms_retain_gpu_mlcc_and_optical_news():
    gpu = match_article_exposure("Ilya 警告 GPU 云可能被 AI 失控模型占用", "", [])
    mlcc = match_article_exposure("MLCC 巨头订单已锁定到 2027 年底", "", [])
    optical = match_article_exposure(
        "Sivers 扩建 InP 产能，AI 光通信市场或迎百亿美元级空间",
        "",
        [],
    )

    assert {"ai-development", "ai-compute"} <= _target_ids(gpu)
    assert "electronic-components" in _target_ids(mlcc)
    assert "optical-communication" in _target_ids(optical)
    assert all(target.get("listed") is not True for target in optical.targets)


def test_geopolitical_proxy_keeps_hormuz_identity():
    match = match_article_exposure("沙特一船只在霍尔木兹海峡发生事故，2人遇难", "", [])

    assert match.status == "matched"
    assert {"hormuz-strait", "geopolitical-crisis"} <= _target_ids(match)
    hormuz = _target(match, "hormuz-strait")
    assert hormuz["links_assets"] == ["WTI"]


def test_power_generation_and_equipment_themes_are_distinct():
    generation = match_article_exposure("某 IPP 与 Meta 签署 20 年核电 PPA", "", [])
    equipment = match_article_exposure("变压器、UPS、开关柜订单大增", "", [])

    assert "ai-generation" in _target_ids(generation)
    assert "power-equipment" not in _target_ids(generation)
    assert "power-equipment" in _target_ids(equipment)
    assert "ai-generation" not in _target_ids(equipment)


def test_unrelated_climate_and_housing_news_remain_filtered():
    assert match_article_exposure("1—8月全国二手房交易网签面积同比增长10.6%", "", []).status == "unmatched"
    assert match_article_exposure("国家气候中心：青藏高原冰川加速消融", "", []).status == "unmatched"


def test_exposure_backfill_updates_operational_realtime_only(monkeypatch):
    from scripts import backfill_realtime_exposure as backfill

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    operational = Article(
        source="cls_telegraph", source_id="operational", title="OpenAI model update",
        content="", collection_lane="realtime", is_backfill=False,
        exposure_status="unmatched", exposure_assets="[]", exposure_reason="no_approved_exposure",
        collected_at=datetime.utcnow(),
    )
    archived = Article(
        source="sec_edgar", source_id="archived", title="OpenAI model update",
        content="", collection_lane="realtime", is_backfill=True,
        exposure_status="matched", exposure_assets="[]", exposure_reason="archive",
        collected_at=datetime.utcnow(),
    )
    session.add_all([operational, archived])
    session.commit()
    monkeypatch.setattr(backfill, "init_db", lambda: None)
    monkeypatch.setattr(backfill, "get_session", lambda: session)

    counts = backfill.classify_realtime_exposure(apply=True)

    assert counts == {"matched": 1}
    refreshed_operational = session.query(Article).filter_by(source_id="operational").one()
    refreshed_archived = session.query(Article).filter_by(source_id="archived").one()
    assert json.loads(refreshed_operational.exposure_targets)[0]["id"] == "openai"
    assert refreshed_archived.exposure_targets is None
    session.close()
