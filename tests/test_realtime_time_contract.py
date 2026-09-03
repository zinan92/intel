"""Realtime product time semantics: UTC on the wire, received time in order."""

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import Article, Base, CollectorRun, SourceRegistry


def test_realtime_api_uses_utc_rfc3339_and_orders_by_received_time(monkeypatch):
    import api.ui_routes as ui
    import scheduler

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(SourceRegistry(
        source_key="cls_telegraph:main",
        source_type="cls_telegraph",
        display_name="CLS",
        config_json="{}",
        is_active=1,
        lane="realtime",
        schedule_seconds=60,
        expected_freshness_hours=1.0,
    ))
    session.add(CollectorRun(
        source_type="cls_telegraph",
        source_key="cls_telegraph:main",
        status="ok",
        articles_fetched=2,
        articles_saved=2,
        duration_ms=100,
        completed_at=datetime(2026, 9, 3, 3, 40, 5),
    ))
    later_received = Article(
        source="cls_telegraph",
        source_id="received-later",
        title="Published earlier but received later",
        content="fixture",
        collection_lane="realtime",
        triage_status="complete",
        triage_bucket="watch",
        triage_direction="unclear",
        triage_rationale="Watch for confirmation.",
        triage_assets=json.dumps([{
            "symbol": "", "name": "Risk assets", "impact": "unclear",
        }]),
        triage_watch_for=json.dumps(["confirmation"]),
        published_at=datetime(2026, 9, 3, 3, 11, 0),
        collected_at=datetime(2026, 9, 3, 3, 40, 0),
        triaged_at=datetime(2026, 9, 3, 3, 40, 3),
        provider_edit_at=datetime(2026, 9, 3, 3, 12, 0),
    )
    earlier_received = Article(
        source="cls_telegraph",
        source_id="received-earlier",
        title="Published later but received earlier",
        content="fixture",
        collection_lane="realtime",
        triage_status="complete",
        triage_bucket="noise",
        triage_direction="unclear",
        triage_rationale="Routine.",
        triage_assets="[]",
        triage_watch_for="[]",
        published_at=datetime(2026, 9, 3, 3, 38, 0),
        collected_at=datetime(2026, 9, 3, 3, 39, 0),
        triaged_at=datetime(2026, 9, 3, 3, 39, 3),
    )
    session.add_all([later_received, earlier_received])
    session.commit()
    monkeypatch.setattr(ui, "get_session", lambda: session)
    monkeypatch.setattr(scheduler, "get_last_results", lambda: {})

    result = ui.get_realtime_feed(window="24h", limit=20)

    assert [item["title"] for item in result["items"]] == [
        "Published earlier but received later",
        "Published later but received earlier",
    ]
    first = result["items"][0]
    assert first["collected_at"] == "2026-09-03T03:40:00Z"
    assert first["published_at"] == "2026-09-03T03:11:00Z"
    assert first["provider_edit_at"] == "2026-09-03T03:12:00Z"
    assert first["triage"]["triaged_at"] == "2026-09-03T03:40:03Z"
    assert result["stats"]["last_collected_at"] == "2026-09-03T03:40:00Z"
    assert result["stats"]["last_triaged_at"] == "2026-09-03T03:40:03Z"
    assert result["stats"]["refreshed_at"].endswith("Z")
    assert result["source_health"][0]["last_seen_at"] == "2026-09-03T03:40:00Z"
    assert result["source_health"][0]["last_attempt_at"] == "2026-09-03T03:40:05Z"
    evidence = result["buckets"]["watch"][0]["event"]["evidence"][0]
    assert result["buckets"]["watch"][0]["event"]["latest_collected_at"] == (
        "2026-09-03T03:40:00Z"
    )
    assert evidence["published_at"] == "2026-09-03T03:11:00Z"
    assert evidence["collected_at"] == "2026-09-03T03:40:00Z"
    session.close()


def test_utc_rfc3339_converts_aware_values_to_z():
    from api.time_contract import utc_rfc3339

    shanghai = timezone(timedelta(hours=8))
    assert utc_rfc3339(
        datetime(2026, 9, 3, 11, 7, 21, tzinfo=shanghai),
    ) == "2026-09-03T03:07:21Z"
