"""Deterministic exposure gate for the Park target registry."""

import json
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import Article, Base


EXPECTED_KEYS = {
    "dxy", "sp500", "nasdaq", "us_dividend", "vix",
    "bitcoin", "ethereum", "hype",
    "shanghai", "star50", "china_dividend", "nikkei", "kospi",
    "wti", "gold", "silver",
}


def test_approved_universe_is_exactly_16_assets():
    from triage.exposure import APPROVED_ASSET_KEYS

    assert set(APPROVED_ASSET_KEYS) == EXPECTED_KEYS
    assert len(APPROVED_ASSET_KEYS) == 16


@pytest.mark.parametrize(("title", "tickers", "expected"), [
    ("美元指数走强", [], {"dxy"}),
    ("S&P 500 与纳斯达克100反弹", [], {"sp500", "nasdaq"}),
    ("NVIDIA 发布数据中心更新", ["NVDA"], {"sp500", "nasdaq"}),
    ("美国8月非农明晚公布", [], {
        "dxy", "sp500", "nasdaq", "vix", "gold", "silver",
        "bitcoin", "ethereum", "hype",
    }),
    ("OPEC+可能维持原油产量配额", [], {"wti"}),
    ("日本央行准备调整政策", [], {"nikkei"}),
    ("黄金期货上涨", ["GC=F"], {"gold"}),
    ("Micro silver contract", ["SILZ26.CMX"], {"silver"}),
    ("科创50和中证红利走强", [], {"star50", "china_dividend"}),
])
def test_exposure_matcher_returns_canonical_assets(title, tickers, expected):
    from triage.exposure import match_article_exposure

    match = match_article_exposure(title, "", tickers)

    assert match.status == "matched"
    assert set(match.asset_keys) == expected


def test_exposure_matcher_deduplicates_aliases_and_rejects_common_word_false_positive():
    from triage.exposure import match_article_exposure

    assert match_article_exposure(
        "BTC Bitcoin 比特币", "", ["BTC", "BTC"],
    ).asset_keys == ("bitcoin",)
    assert match_article_exposure("spyware software update", "", []).status == "unmatched"
    assert match_article_exposure("ethernet hardware update", "", []).status == "unmatched"
    assert match_article_exposure("公司签署1.66亿美元海外工程合同", "", []).status == "unmatched"
    assert match_article_exposure("海南农业进入黄金窗口期", "", []).status == "unmatched"
    assert set(match_article_exposure("NVIDIA earnings", "", []).asset_keys) == {"sp500", "nasdaq"}


def test_realtime_api_excludes_unmatched_articles_but_can_show_audit_view():
    import api.ui_routes as ui
    import scheduler

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add_all([
        Article(
            source="cls_telegraph", source_id="matched", title="BTC move",
            content="crypto", collection_lane="realtime", exposure_status="matched",
            exposure_assets=json.dumps(["bitcoin"]), exposure_reason="direct_symbol",
            triage_status="complete", triage_bucket="watch", triage_direction="unclear",
            triage_assets=json.dumps([{"symbol": "BTC", "impact": "unclear"}]),
            triage_watch_for=json.dumps(["confirmation"]), collected_at=datetime.utcnow(),
        ),
        Article(
            source="cls_telegraph", source_id="unmatched", title="Unrelated item",
            content="software", collection_lane="realtime", exposure_status="unmatched",
            exposure_assets="[]", exposure_reason="no_approved_exposure",
            triage_status="complete", triage_bucket="noise", triage_direction="unclear",
            triage_assets="[]", triage_watch_for="[]", collected_at=datetime.utcnow(),
        ),
    ])
    session.commit()
    with patch.object(ui, "get_session", return_value=session), \
         patch.object(scheduler, "get_last_results", return_value={}):
        visible = ui.get_realtime_feed(window="24h", limit=20)
        audit = ui.get_realtime_feed(window="24h", limit=20, include_unmatched=True)

    assert [item["title"] for item in visible["items"]] == ["BTC move"]
    assert {target["id"] for target in visible["items"][0]["exposure_targets"]} >= {"bitcoin"}
    assert visible["stats"]["exposure_excluded"] == 1
    assert len(audit["items"]) == 2
    session.close()


def test_scheduler_only_sends_matched_articles_to_realtime_ai():
    import scheduler

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add_all([
        Article(
            source="cls_telegraph", source_id="queue-matched", title="BTC move",
            content="crypto", collection_lane="realtime", exposure_status="matched",
            exposure_assets=json.dumps(["bitcoin"]), exposure_reason="direct_symbol",
        ),
        Article(
            source="cls_telegraph", source_id="queue-unmatched", title="Unrelated item",
            content="software", collection_lane="realtime", exposure_status="unmatched",
        ),
    ])
    session.commit()
    seen = []

    class FakeTriage:
        model_name = "test-model"

        def __init__(self, **_kwargs):
            pass

        def triage_batch(self, articles):
            seen.extend(articles)
            return [{
                "id": articles[0]["id"], "bucket": "watch", "direction": "unclear",
                "rationale": "Watch for confirmation.",
                "affected_assets": [{"symbol": "BTC", "impact": "unclear"}],
                "watch_for": ["confirmation"],
            }]

    with patch("db.database.get_session", return_value=session), \
         patch.object(scheduler, "_realtime_lane_enabled", return_value=True), \
         patch("triage.realtime.RealtimeTriage", FakeTriage):
        scheduler._run_realtime_triage()

    assert len(seen) == 1
    assert seen[0]["exposure_assets"] == ["bitcoin"]
    assert seen[0]["exposure_targets"] == []
    assert session.query(Article).filter_by(source_id="queue-matched").one().triage_status == "complete"
    assert session.query(Article).filter_by(source_id="queue-unmatched").one().triage_status is None
    session.close()


def test_realtime_collector_persists_exposure_match_before_triage(monkeypatch):
    from collectors.base import BaseCollector

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    monkeypatch.setattr("collectors.base.init_db", lambda: None)
    monkeypatch.setattr("collectors.base.get_session", lambda: session)

    class FakeCollector(BaseCollector):
        source = "cls_telegraph"

        def collect(self):
            return []

    FakeCollector().save([
        {
            "source": "cls_telegraph",
            "source_id": "collector-exposure-1",
            "title": "BTC market move",
            "content": "Bitcoin price moves.",
            "collection_lane": "realtime",
        },
    ])

    saved = session.query(Article).filter_by(source_id="collector-exposure-1").one()
    assert saved.exposure_status == "matched"
    assert json.loads(saved.exposure_assets) == ["bitcoin"]
    targets = json.loads(saved.exposure_targets)
    assert {target["id"] for target in targets} >= {"bitcoin"}
    assert saved.exposure_reason.startswith("asset:bitcoin") or "text:bitcoin" in saved.exposure_reason
    session.close()
