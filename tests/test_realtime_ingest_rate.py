"""Authoritative Rolling News ingest-rate metric contract."""

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import Article, Base


def _article(
    source_id: str,
    *,
    collected_at: datetime,
    lane: str = "realtime",
    is_backfill: bool = False,
    exposure_status: str = "unmatched",
) -> Article:
    return Article(
        source="cls_telegraph",
        source_id=source_id,
        title=source_id,
        content="fixture",
        collection_lane=lane,
        is_backfill=is_backfill,
        exposure_status=exposure_status,
        collected_at=collected_at,
    )


def test_realtime_ingest_rate_counts_all_operational_arrivals_in_ten_minutes(
    monkeypatch,
):
    import api.ui_routes as ui
    import scheduler

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime.utcnow()
    session.add_all([
        _article("matched-now", collected_at=now, exposure_status="matched"),
        _article("unmatched-5m", collected_at=now - timedelta(minutes=5)),
        _article("unclassified-9m", collected_at=now - timedelta(minutes=9), exposure_status=None),
        _article("too-old", collected_at=now - timedelta(minutes=11)),
        _article("backfill", collected_at=now, is_backfill=True),
        _article("hourly", collected_at=now, lane="hourly"),
    ])
    session.commit()
    monkeypatch.setattr(ui, "get_session", lambda: session)
    monkeypatch.setattr(scheduler, "get_last_results", lambda: {})

    response = ui.get_realtime_feed(window="24h", limit=20)

    metric = response["stats"]["ingest_rate"]
    assert metric["status"] == "ok"
    assert metric["window_minutes"] == 10
    assert metric["article_count"] == 3
    assert metric["headlines_per_minute"] == 0.3
    assert metric["window_started_at"].endswith("Z")
    assert metric["window_ended_at"].endswith("Z")


def test_realtime_ingest_rate_reports_true_zero_as_available(monkeypatch):
    import api.ui_routes as ui
    import scheduler

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    monkeypatch.setattr(ui, "get_session", lambda: session)
    monkeypatch.setattr(scheduler, "get_last_results", lambda: {})

    response = ui.get_realtime_feed(window="24h", limit=20)
    metric = response["stats"]["ingest_rate"]

    assert metric["status"] == "ok"
    assert metric["article_count"] == 0
    assert metric["headlines_per_minute"] == 0.0
