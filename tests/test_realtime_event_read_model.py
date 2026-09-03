"""Realtime UI groups duplicate source reports without mutating raw Articles."""

import json
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import Article, Base, SourceRegistry


def _article(
    source_id: str,
    source: str,
    title: str,
    when: datetime,
    *,
    bucket: str = "high_impact",
) -> Article:
    return Article(
        source=source,
        source_id=source_id,
        title=title,
        content=title,
        url=f"https://example.com/{source_id}",
        collection_lane="realtime",
        exposure_status="matched",
        exposure_assets=json.dumps(["sp500"]),
        exposure_reason="test_fixture",
        triage_status="complete",
        triage_bucket=bucket,
        triage_direction="bearish" if bucket == "high_impact" else "unclear",
        triage_rationale="Market repricing.",
        triage_assets=json.dumps([{
            "symbol": "DAX",
            "name": "German equities",
            "impact": "down",
        }]),
        triage_watch_for=json.dumps(["implementation details"]),
        published_at=when,
        collected_at=when,
    )


def test_realtime_buckets_group_only_cross_source_near_duplicates_in_window(
    monkeypatch,
):
    import api.ui_routes as ui

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    for source in ("cls_telegraph", "eastmoney_global_news", "blockbeats_newsflash"):
        session.add(SourceRegistry(
            source_key=f"{source}:main",
            source_type=source,
            display_name=source,
            config_json="{}",
            is_active=1,
            lane="realtime",
            schedule_seconds=60,
        ))
    now = datetime.utcnow()
    session.add_all([
        _article(
            "cls-a",
            "cls_telegraph",
            "欧盟批准德国最高达350亿欧元的容量机制以保障电力供应",
            now,
        ),
        _article(
            "east-a",
            "eastmoney_global_news",
            "【快讯】欧盟批准德国最高达350亿欧元容量机制，以保障电力供应",
            now - timedelta(minutes=2),
            bucket="watch",
        ),
        _article(
            "cls-distinct",
            "cls_telegraph",
            "欧盟批准法国新能源补贴计划",
            now - timedelta(minutes=3),
        ),
        _article(
            "block-old",
            "blockbeats_newsflash",
            "欧盟批准德国最高达350亿欧元的容量机制以保障电力供应",
            now - timedelta(hours=2),
        ),
        _article(
            "cls-update",
            "cls_telegraph",
            "欧盟批准德国最高达350亿欧元的容量机制以保障电力供应",
            now - timedelta(minutes=5),
        ),
    ])
    session.commit()
    raw_ids = {article.id for article in session.query(Article).all()}
    monkeypatch.setattr(ui, "get_session", lambda: session)

    response = ui.get_realtime_feed(window="24h", limit=20)

    assert {item["id"] for item in response["items"]} == raw_ids
    assert response["stats"]["returned"] == 5
    assert response["stats"]["displayed_events"] == 4
    assert len(response["buckets"]["high_impact"]) == 4
    assert response["buckets"]["watch"] == []

    merged = next(
        item for item in response["buckets"]["high_impact"]
        if item["event"]["evidence_count"] == 2
    )
    assert merged["event"]["event_id"] == (
        f"realtime-event:{min(evidence['article_id'] for evidence in merged['event']['evidence'])}"
    )
    assert {evidence["source"] for evidence in merged["event"]["evidence"]} == {
        "cls_telegraph",
        "eastmoney_global_news",
    }
    assert all(evidence["url"] for evidence in merged["event"]["evidence"])
    assert session.query(Article).count() == 5
    session.close()


def test_realtime_event_id_and_grouping_are_deterministic(monkeypatch):
    import api.ui_routes as ui

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime.utcnow()
    session.add_all([
        _article("cls-x", "cls_telegraph", "美联储宣布维持利率不变", now),
        _article(
            "east-x",
            "eastmoney_global_news",
            "美联储宣布维持利率不变。",
            now - timedelta(seconds=30),
        ),
    ])
    session.commit()
    monkeypatch.setattr(ui, "get_session", lambda: session)

    first = ui.get_realtime_feed(window="24h", limit=20)
    second = ui.get_realtime_feed(window="24h", limit=20)

    first_event = first["buckets"]["high_impact"][0]["event"]
    second_event = second["buckets"]["high_impact"][0]["event"]
    assert first_event == second_event
    assert first_event["evidence_count"] == 2
    session.close()
