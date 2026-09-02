"""Core API contract: imported historical filings never masquerade as current."""

from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.models import Article, Base, SourceRegistry


def test_core_recent_source_apis_exclude_sec_backfill_without_deleting_archive():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    now = datetime.utcnow()
    session = factory()
    session.add(SourceRegistry(
        source_key="sec_edgar:watchlist",
        source_type="sec_edgar",
        display_name="SEC EDGAR Watchlist",
        config_json="{}",
        is_active=1,
        lane="realtime",
        schedule_seconds=60,
    ))
    session.add_all([
        Article(
            source="sec_edgar",
            source_id=f"sec-current-{index}",
            title=f"SEC filing current {index}",
            content="SEC filing",
            collected_at=now - timedelta(minutes=index),
            published_at=now - timedelta(minutes=index),
            collection_lane="realtime",
            is_backfill=False,
        )
        for index in range(3)
    ])
    session.add_all([
        Article(
            source="sec_edgar",
            source_id=f"sec-backfill-{index}",
            title=f"SEC filing historical {index}",
            content="SEC filing",
            collected_at=now,
            published_at=datetime(2010, 1, 1),
            collection_lane="realtime",
            triage_bucket="high_impact" if index < 94 else None,
            is_backfill=True,
            backfill_reason="historical import",
        )
        for index in range(2935)
    ])
    session.commit()
    session.close()

    def get_test_session():
        return factory()

    with patch("main.init_db", return_value=None), \
         patch("api.routes.get_session", side_effect=get_test_session):
        from main import app
        with TestClient(app) as client:
            health = client.get("/api/health").json()
            latest = client.get(
                "/api/articles/latest?source=sec_edgar&limit=200"
            ).json()
            search = client.get(
                "/api/articles/search?q=SEC%20filing&source=sec_edgar&days=30&limit=200"
            ).json()
            sources = client.get("/api/articles/sources").json()

    sec = next(item for item in sources if item["source"] == "sec_edgar")
    assert health["sources"]["sec_edgar"]["count"] == 3
    assert len(latest) == 3
    assert len(search) == 3
    assert sec["count"] == 2938
    assert sec["backfill_count"] == 2935
    assert sec["articles_last_24h"] == 3
    assert sec["latest_published_at"].startswith(now.date().isoformat())
