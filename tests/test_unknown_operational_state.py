"""Unknown is an operational health state with one evidence-triggered revisit."""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from db.models import Article, Base, SourceRegistry


def _article(source_id, source, title, when, *, bucket="noise", status="complete"):
    return Article(
        source=source,
        source_id=source_id,
        title=title,
        content=title,
        collection_lane="realtime",
        triage_status=status,
        triage_bucket=bucket if status == "complete" else None,
        triage_direction="unclear",
        triage_rationale="Insufficient information." if bucket == "unknown" else "Routine.",
        triage_assets="[]",
        triage_watch_for="[]",
        triaged_at=when if status == "complete" else None,
        published_at=when,
        collected_at=when,
    )


def test_realtime_api_reports_unknown_as_complete_window_health_signal(monkeypatch):
    import api.ui_routes as ui

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
    ))
    now = datetime.utcnow()
    session.add_all([
        _article(
            f"complete-{index}", "cls_telegraph",
            f"Unique completed headline {index}", now - timedelta(seconds=index),
            bucket="unknown" if index == 0 else "noise",
        )
        for index in range(10)
    ])
    session.add(_article(
        "pending-one", "cls_telegraph", "Pending headline", now, status=None,
    ))
    session.commit()
    monkeypatch.setattr(ui, "get_session", lambda: session)

    response = ui.get_realtime_feed(window="24h", limit=5)

    assert response["operational"]["unknown"] == {
        "count": 1,
        "complete_count": 10,
        "rate": 0.1,
        "alert_threshold": 0.1,
        "alert": True,
    }
    assert response["operational"]["pending"] == 1
    assert response["operational"]["failed"] == 0
    assert set(response["buckets"]) == {"high_impact", "watch", "noise"}
    session.close()


def test_rate_rounding_cannot_trigger_false_ten_percent_alert(monkeypatch):
    import api.ui_routes as ui

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime.utcnow()
    session.add_all([
        _article(
            f"unknown-{index}", "cls_telegraph", f"Unknown {index}", now,
            bucket="unknown",
        )
        for index in range(200)
    ] + [
        _article(
            f"noise-{index}", "cls_telegraph", f"Noise {index}", now,
            bucket="noise",
        )
        for index in range(1801)
    ])
    session.commit()
    monkeypatch.setattr(ui, "get_session", lambda: session)

    result = ui.get_realtime_feed(window="24h", limit=1)

    assert result["operational"]["unknown"]["rate"] == 0.1
    assert result["operational"]["unknown"]["alert"] is False
    session.close()


def test_unknown_evidence_never_makes_combined_event_look_like_noise(monkeypatch):
    import api.ui_routes as ui

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime.utcnow()
    session.add_all([
        _article(
            "unknown-report", "cls_telegraph", "同一事件等待更多信息", now,
            bucket="unknown",
        ),
        _article(
            "noise-report", "eastmoney_global_news", "同一事件等待更多信息。", now,
            bucket="noise",
        ),
    ])
    session.commit()
    monkeypatch.setattr(ui, "get_session", lambda: session)

    result = ui.get_realtime_feed(window="24h", limit=20)

    assert result["buckets"]["noise"] == []
    assert result["stats"]["operational_events_hidden"] == 1
    assert result["operational"]["unknown"]["count"] == 1
    session.close()


def test_later_cross_source_evidence_requeues_unknown_at_most_once():
    from triage.revisit import requeue_unknown_with_new_evidence

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime.utcnow()
    unknown = _article(
        "unknown-a", "cls_telegraph",
        "欧盟批准德国最高达350亿欧元的容量机制保障电力供应",
        now - timedelta(minutes=10), bucket="unknown",
    )
    unrelated = _article(
        "unknown-b", "cls_telegraph", "某公司发布常规人事任命",
        now - timedelta(minutes=10), bucket="unknown",
    )
    session.add_all([unknown, unrelated])
    session.commit()
    unknown_id = unknown.id
    unrelated_id = unrelated.id
    session.add_all([
        _article(
            "evidence-east", "eastmoney_global_news",
            "【快讯】欧盟批准德国最高达350亿欧元的容量机制，以保障电力供应",
            now, bucket="watch",
        ),
        _article(
            "same-source-repeat", "cls_telegraph", unknown.title,
            now, bucket="watch",
        ),
    ])
    session.commit()

    requeued = requeue_unknown_with_new_evidence(session, now=now)

    session.expire_all()
    unknown = session.get(Article, unknown_id)
    unrelated = session.get(Article, unrelated_id)
    assert requeued == [unknown_id]
    assert unknown.triage_status is None
    assert unknown.triage_bucket is None
    assert unknown.triage_rescan_count == 1
    assert unknown.triage_rescan_after is not None
    assert unrelated.triage_status == "complete"

    unknown.triage_status = "complete"
    unknown.triage_bucket = "unknown"
    session.commit()
    assert requeue_unknown_with_new_evidence(session, now=now) == []
    assert unknown.triage_rescan_count == 1
    session.close()


def test_delayed_collection_can_trigger_revisit_when_event_time_still_matches():
    from triage.revisit import requeue_unknown_with_new_evidence

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime.utcnow()
    unknown = _article(
        "delayed-unknown", "cls_telegraph", "美联储宣布维持利率不变",
        now - timedelta(hours=2), bucket="unknown",
    )
    unknown.triaged_at = now - timedelta(hours=1, minutes=50)
    evidence = _article(
        "delayed-evidence", "eastmoney_global_news", "美联储宣布维持利率不变。",
        now, bucket="watch",
    )
    evidence.published_at = unknown.published_at + timedelta(minutes=2)
    session.add_all([unknown, evidence])
    session.commit()

    assert requeue_unknown_with_new_evidence(session, now=now) == [unknown.id]
    session.close()


def test_later_completed_unknown_can_be_evidence_for_earlier_unknown():
    from triage.revisit import requeue_unknown_with_new_evidence

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime.utcnow()
    earlier = _article(
        "unknown-earlier", "cls_telegraph", "同一政策事件等待细节",
        now - timedelta(minutes=20), bucket="unknown",
    )
    later = _article(
        "unknown-later", "eastmoney_global_news", "同一政策事件等待细节。",
        now - timedelta(minutes=5), bucket="unknown",
    )
    later.triaged_at = now - timedelta(minutes=1)
    session.add_all([earlier, later])
    session.commit()

    assert requeue_unknown_with_new_evidence(session, now=now) == [earlier.id]
    session.close()


def test_triggering_evidence_is_retained_for_retriage_context():
    from triage.revisit import related_evidence_for, requeue_unknown_with_new_evidence

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime.utcnow()
    unknown = _article(
        "context-unknown", "cls_telegraph", "欧盟批准德国容量机制",
        now - timedelta(minutes=20), bucket="unknown",
    )
    unknown.triaged_at = now - timedelta(minutes=10)
    session.add(unknown)
    session.commit()
    for index in range(3):
        old = _article(
            f"old-evidence-{index}", "source-old-" + str(index),
            "欧盟批准德国容量机制。", now - timedelta(minutes=15 - index),
            bucket="watch",
        )
        old.collected_at = now - timedelta(minutes=15 - index)
        session.add(old)
    trigger = _article(
        "new-trigger", "blockbeats_newsflash", "欧盟批准德国容量机制。",
        now, bucket="watch",
    )
    session.add(trigger)
    session.commit()

    assert requeue_unknown_with_new_evidence(session, now=now) == [unknown.id]
    session.refresh(unknown)
    evidence = related_evidence_for(session, unknown)
    assert [item["article_id"] for item in evidence] == [trigger.id]
    session.close()


def test_scheduler_uses_rescan_baseline_and_includes_triggering_evidence(monkeypatch):
    from unittest.mock import patch

    from scheduler import _run_realtime_triage

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime.utcnow()
    baseline = now - timedelta(minutes=10)
    unknown = _article(
        "scheduler-unknown", "cls_telegraph", "欧盟批准德国容量机制",
        now - timedelta(minutes=20), status=None,
    )
    unknown.triage_rescan_count = 1
    unknown.triage_rescan_after = baseline
    session.add(unknown)
    for index in range(3):
        old = _article(
            f"scheduler-old-{index}", f"old-source-{index}",
            "欧盟批准德国容量机制。", now - timedelta(minutes=15 - index),
            bucket="watch",
        )
        old.collected_at = baseline - timedelta(minutes=index + 1)
        session.add(old)
    trigger = _article(
        "scheduler-trigger", "blockbeats_newsflash", "欧盟批准德国容量机制。",
        now, bucket="watch",
    )
    session.add(trigger)
    session.commit()
    trigger_id = trigger.id
    seen = []

    class FakeTriage:
        model_name = "test-model"

        def __init__(self, **_kwargs):
            pass

        def triage_batch(self, articles):
            seen.extend(articles)
            return [{
                "id": articles[0]["id"],
                "bucket": "watch",
                "direction": "unclear",
                "rationale": "New evidence adds context.",
                "affected_assets": [{
                    "symbol": "", "name": "German power producers", "impact": "unclear",
                }],
                "watch_for": ["implementation timetable"],
            }]

    with patch("db.database.get_session", return_value=session), \
         patch("scheduler._realtime_lane_enabled", return_value=True), \
         patch("triage.realtime.RealtimeTriage", FakeTriage):
        _run_realtime_triage()

    assert [item["article_id"] for item in seen[0]["related_evidence"]] == [trigger_id]
    session.close()


def test_rescan_claim_is_atomic_across_stale_sessions():
    from triage.revisit import claim_unknown_for_rescan

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    seed = Session(engine)
    now = datetime.utcnow()
    unknown = _article(
        "atomic-unknown", "cls_telegraph", "Atomic event", now,
        bucket="unknown",
    )
    seed.add(unknown)
    seed.commit()
    article_id = unknown.id
    seed.close()
    first = Session(engine)
    second = Session(engine)
    first.get(Article, article_id)
    second.get(Article, article_id)

    assert claim_unknown_for_rescan(first, article_id, baseline=now) is True
    assert claim_unknown_for_rescan(second, article_id, baseline=now) is False
    second.expire_all()
    assert second.get(Article, article_id).triage_rescan_count == 1
    first.close()
    second.close()


def test_related_evidence_for_batch_uses_one_bounded_query():
    from sqlalchemy import event

    from triage.revisit import related_evidence_map

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime.utcnow()
    unknowns = [
        _article(
            f"batch-unknown-{index}", "cls_telegraph",
            f"Shared event headline {index}", now, bucket="unknown",
        )
        for index in range(10)
    ]
    evidence = [
        _article(
            f"batch-evidence-{index}", "eastmoney_global_news",
            f"Shared event headline {index}.", now, bucket="watch",
        )
        for index in range(10)
    ]
    session.add_all(unknowns + evidence)
    session.commit()
    unknowns = session.query(Article).filter(
        Article.source_id.like("batch-unknown-%"),
    ).all()
    selects = []

    def count_select(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(engine, "before_cursor_execute", count_select)
    result = related_evidence_map(session, unknowns)
    event.remove(engine, "before_cursor_execute", count_select)

    assert len(selects) == 1
    assert all(len(result[article.id]) == 1 for article in unknowns)
    session.close()


def test_related_evidence_is_included_in_retriage_prompt():
    from triage.realtime import RealtimeTriage

    client = MagicMock()
    client.complete.return_value = json.dumps({"results": [{
        "id": 77,
        "bucket": "watch",
        "direction": "unclear",
        "rationale": "A second source adds useful confirmation.",
        "affected_assets": [{
            "symbol": "", "name": "German power producers", "impact": "unclear",
        }],
        "watch_for": ["implementation timetable"],
    }]})

    RealtimeTriage(client=client).triage_batch([{
        "id": 77,
        "source": "cls_telegraph",
        "title": "Initial incomplete report",
        "content": "Few details.",
        "related_evidence": [{
            "source": "eastmoney_global_news",
            "title": "Supplemental policy details",
            "content": "The later report adds implementation details.",
        }],
    }])

    prompt = client.complete.call_args.args[0]
    assert "Supplemental evidence" in prompt
    assert "Supplemental policy details" in prompt


def test_unknown_rescan_count_column_is_durable():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("articles")}
    assert {"triage_rescan_count", "triage_rescan_after"}.issubset(columns)


def test_unknown_rescan_columns_migrate_on_old_database():
    from sqlalchemy import text

    from db.migrations import run_migrations

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE articles ("
            "id INTEGER PRIMARY KEY, source TEXT, collected_at DATETIME)"
        ))
    run_migrations(engine)
    columns = {column["name"]: column for column in inspect(engine).get_columns("articles")}
    assert columns["triage_rescan_count"]["nullable"] is False
    assert "triage_rescan_after" in columns


def test_scheduler_registers_unknown_rescan_with_realtime_lane(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from scheduler import CollectorScheduler

    monkeypatch.setenv("REALTIME_LANE_ENABLED", "1")
    source = SimpleNamespace(
        source_type="cls_telegraph",
        schedule_hours=None,
        lane="realtime",
        schedule_seconds=60,
    )
    fake_session = MagicMock()
    with patch("db.database.get_session", return_value=fake_session), \
         patch("sources.registry.list_active_sources", return_value=[source]):
        scheduler = CollectorScheduler()
        scheduler._register_jobs()

    jobs = {job.id: job for job in scheduler._scheduler.get_jobs()}
    assert jobs["realtime-unknown-rescan"].trigger.interval.total_seconds() == 300
