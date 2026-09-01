"""Contract tests for the dual-run measurement receipt."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import Article, Base, CollectorRun, SourceRegistry


def _seed_fixture() -> tuple[Session, datetime, datetime]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    end = datetime(2026, 9, 1, 9, 0, 0)
    start = end - timedelta(hours=1)

    session.add_all([
        SourceRegistry(
            source_key="rss:fixture",
            source_type="rss",
            display_name="Fixture RSS",
            config_json="{}",
            lane="hourly",
            schedule_hours=1,
            expected_freshness_hours=2.0,
        ),
        SourceRegistry(
            source_key="cls_telegraph:main",
            source_type="cls_telegraph",
            display_name="CLS Telegraph",
            config_json="{}",
            lane="realtime",
            schedule_seconds=60,
            expected_freshness_hours=0.1,
        ),
        SourceRegistry(
            source_key="eastmoney_global_news:main",
            source_type="eastmoney_global_news",
            display_name="Eastmoney 7x24",
            config_json="{}",
            lane="realtime",
            schedule_seconds=60,
            expected_freshness_hours=0.1,
        ),
    ])

    published = end - timedelta(minutes=45)
    collected = end - timedelta(minutes=40)
    session.add_all([
        Article(
            source="rss",
            source_id="rss:fixture:1",
            title="Central bank holds rates",
            content="fixture",
            url="https://example.test/hourly/1",
            published_at=published,
            collected_at=collected,
            collection_lane="hourly",
        ),
        Article(
            source="cls_telegraph",
            source_id="cls_telegraph:1",
            title="Central bank holds rates",
            content="fixture",
            url="https://example.test/cls/1",
            published_at=published,
            collected_at=end - timedelta(minutes=42),
            collection_lane="realtime",
        ),
        Article(
            source="cls_telegraph",
            source_id="cls_telegraph:2",
            title="Un-timestamped market note",
            content="fixture",
            url="https://example.test/cls/2",
            published_at=None,
            collected_at=end - timedelta(minutes=10),
            collection_lane="realtime",
        ),
    ])
    session.add_all([
        CollectorRun(
            source_type="rss",
            source_key="rss:fixture",
            status="ok",
            articles_fetched=3,
            articles_saved=1,
            articles_duplicate=2,
            duration_ms=200,
            completed_at=end - timedelta(minutes=35),
        ),
        CollectorRun(
            source_type="cls_telegraph",
            source_key="cls_telegraph:main",
            status="ok",
            articles_fetched=3,
            articles_saved=2,
            articles_duplicate=1,
            duration_ms=100,
            completed_at=end - timedelta(minutes=9),
        ),
        CollectorRun(
            source_type="eastmoney_global_news",
            source_key="eastmoney_global_news:main",
            status="error",
            articles_fetched=0,
            articles_saved=0,
            duration_ms=1000,
            error_message="upstream timeout",
            error_category="transient",
            completed_at=end - timedelta(minutes=8),
        ),
    ])
    session.commit()
    return session, start, end


def test_receipt_reports_each_lane_and_does_not_claim_convergence():
    from dual_run.receipt import build_dual_run_receipt

    session, start, end = _seed_fixture()
    try:
        receipt = build_dual_run_receipt(session, window_start=start, window_end=end)
    finally:
        session.close()

    assert receipt["state"] == "dual_run"
    assert receipt["convergence"]["eligible"] is False

    hourly = receipt["lanes"]["hourly"]
    assert hourly["raw_rows"] == 3
    assert hourly["new_rows"] == 1
    assert hourly["duplicate_rows"] == 2
    assert hourly["source_failures"] == 0

    realtime = receipt["lanes"]["realtime"]
    assert realtime["raw_rows"] == 3
    assert realtime["unique_rows"] == 2
    assert realtime["new_rows"] == 2
    assert realtime["duplicate_rows"] == 1
    assert realtime["source_failures"] == 1
    assert realtime["missing_timestamps"] == 1
    assert realtime["timestamp_completeness"] == 0.5
    assert realtime["latency"]["count"] == 1

    comparison = receipt["comparison"]
    assert comparison["cross_lane_overlap_count"] == 1
    assert comparison["independent_event_count"] == 2
    assert comparison["overlap_items"][0]["lanes"] == ["hourly", "realtime"]

    eastmoney = next(
        item for item in receipt["source_health"]
        if item["source_type"] == "eastmoney_global_news"
    )
    assert eastmoney["status"] == "failed"


def test_live_smoke_is_failure_isolated_and_sanitized():
    from dual_run.receipt import run_live_smoke

    def _good_fetcher():
        return [{
            "source": "cls_telegraph",
            "source_id": "cls_telegraph:1",
            "title": "A live-looking item",
            "url": "https://example.test/1",
            "published_at": datetime.now(timezone.utc).replace(tzinfo=None),
        }]

    def _bad_fetcher():
        raise TimeoutError("provider timed out")

    smoke = run_live_smoke({
        "cls_telegraph": _good_fetcher,
        "eastmoney_global_news": _bad_fetcher,
    })

    assert smoke["status"] == "partial_failure"
    assert smoke["sources"]["cls_telegraph"]["status"] == "ok"
    assert smoke["sources"]["cls_telegraph"]["rows"] == 1
    assert smoke["sources"]["eastmoney_global_news"]["status"] == "failed"
    assert smoke["sources"]["eastmoney_global_news"]["error_type"] == "TimeoutError"
    assert "provider timed out" not in str(smoke)


def test_live_smoke_does_not_treat_empty_provider_response_as_success():
    from dual_run.receipt import run_live_smoke

    smoke = run_live_smoke({"cls_telegraph": lambda: []})

    assert smoke["status"] == "failed"
    assert smoke["sources"]["cls_telegraph"]["status"] == "empty"
    assert smoke["sources"]["cls_telegraph"]["error_type"] == "EmptyResponse"
