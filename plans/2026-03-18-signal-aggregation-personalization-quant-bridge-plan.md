# Signal Aggregation, User Personalization & Quant Bridge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add cross-source event clustering with signal scoring, per-user topic weight personalization, and ticker extraction with quant-data-pipeline price impact integration.

**Architecture:** Three features built sequentially. Feature 1 (events) adds a new `events` module with aggregation logic + scheduler job + API. Feature 2 (users) adds a `users` module with profiles + feed personalization. Feature 3 (bridge) extends the keyword tagger with ticker extraction and adds a `bridge` module for quant API calls.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, SQLite, httpx (new), React 18, TypeScript, TanStack Query

**Spec:** `plans/2026-03-18-signal-aggregation-personalization-quant-bridge-design.md`

---

## File Map

### New Files
| File | Purpose |
|------|---------|
| `events/__init__.py` | Package init |
| `events/models.py` | Event + EventArticle SQLAlchemy models |
| `events/aggregator.py` | Core aggregation logic (48h window, signal scoring) |
| `api/event_routes.py` | `/api/events/active`, `/api/events/{id}` endpoints |
| `users/__init__.py` | Package init |
| `users/models.py` | UserProfile SQLAlchemy model |
| `users/service.py` | User CRUD + weight validation |
| `api/user_routes.py` | `/api/users` CRUD endpoints |
| `bridge/__init__.py` | Package init |
| `bridge/quant.py` | Async price snapshot fetcher (httpx) |
| `tagging/tickers.py` | Ticker extraction logic (cashtag + alias + yahoo) |
| `scripts/backfill_tickers.py` | One-time backfill for existing articles |
| `frontend/src/pages/SettingsPage.tsx` | User weight configuration UI |
| `tests/test_event_models.py` | Event model tests |
| `tests/test_event_aggregation.py` | Aggregation logic tests |
| `tests/test_event_api.py` | Event API endpoint tests |
| `tests/test_user_profiles.py` | User CRUD + weight validation tests |
| `tests/test_personalized_feed.py` | Personalized feed ranking tests |
| `tests/test_ticker_extraction.py` | Ticker extraction tests |
| `tests/test_quant_bridge.py` | Bridge module tests |

### Modified Files
| File | Changes |
|------|---------|
| `db/models.py:40-66` | Add `tickers` field to Article |
| `db/migrations.py:62-85` | Add `tickers` column migration + events/user_profiles table creation |
| `db/database.py:43-51` | Import new models so `create_all` picks them up |
| `main.py:12-69` | Register event_routes + user_routes routers |
| `scheduler.py:197-249` | Add hourly aggregation job |
| `tagging/__init__.py` | Export `extract_tickers` |
| `tagging/keywords.py` | No changes (ticker logic in separate file) |
| `collectors/base.py:31-72` | Call `extract_tickers()` in `save()`, write to `tickers` field |
| `collectors/yahoo_finance.py:79-93` | Pass ticker symbol in article dict |
| `config.py` | Add `TICKER_ALIASES`, `QUANT_API_BASE_URL` |
| `api/ui_routes.py:273-342` | Add `user` param to feed, add `top_events` to context |
| `frontend/src/types/api.ts` | Add Event, UserProfile, PriceImpact types |
| `frontend/src/api/client.ts` | Add event, user, settings API methods |
| `frontend/src/App.tsx` | Add `/settings` route |
| `frontend/src/components/Sidebar.tsx` | Add user selector dropdown |
| `frontend/src/components/ContextRail.tsx` | Add top events section |
| `requirements.txt` | Add `httpx>=0.27` |

---

## Task 1: Event + EventArticle Models & Migration

**Files:**
- Create: `events/__init__.py`
- Create: `events/models.py`
- Create: `tests/test_event_models.py`
- Modify: `db/migrations.py:62-85`
- Modify: `db/database.py:43-51`

- [ ] **Step 1: Write failing test for Event model**

```python
# tests/test_event_models.py
"""Tests for Event and EventArticle models."""
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base, Article
from events.models import Event, EventArticle


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_create_event(db_session: Session):
    now = datetime.utcnow()
    event = Event(
        narrative_tag="nvidia-earnings-beat",
        window_start=now,
        window_end=now + timedelta(hours=48),
        source_count=3,
        article_count=10,
        signal_score=12.0,
        avg_relevance=4.0,
        status="active",
    )
    db_session.add(event)
    db_session.commit()

    loaded = db_session.query(Event).first()
    assert loaded is not None
    assert loaded.narrative_tag == "nvidia-earnings-beat"
    assert loaded.signal_score == 12.0
    assert loaded.status == "active"


def test_event_article_link(db_session: Session):
    now = datetime.utcnow()
    article = Article(
        source="hackernews",
        source_id="hn_test_1",
        title="NVIDIA earnings",
        collected_at=now,
    )
    db_session.add(article)
    db_session.commit()

    event = Event(
        narrative_tag="nvidia-earnings-beat",
        window_start=now,
        window_end=now + timedelta(hours=48),
    )
    db_session.add(event)
    db_session.commit()

    link = EventArticle(event_id=event.id, article_id=article.id)
    db_session.add(link)
    db_session.commit()

    links = db_session.query(EventArticle).all()
    assert len(links) == 1
    assert links[0].event_id == event.id
    assert links[0].article_id == article.id


def test_event_article_unique_constraint(db_session: Session):
    """Duplicate event-article links should raise IntegrityError."""
    from sqlalchemy.exc import IntegrityError

    now = datetime.utcnow()
    article = Article(source="rss", source_id="rss_1", collected_at=now)
    db_session.add(article)
    db_session.commit()

    event = Event(
        narrative_tag="test-tag",
        window_start=now,
        window_end=now + timedelta(hours=48),
    )
    db_session.add(event)
    db_session.commit()

    db_session.add(EventArticle(event_id=event.id, article_id=article.id))
    db_session.commit()

    db_session.add(EventArticle(event_id=event.id, article_id=article.id))
    with pytest.raises(IntegrityError):
        db_session.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/wendy/work/trading-co/park-intel && python -m pytest tests/test_event_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'events'`

- [ ] **Step 3: Create Event + EventArticle models**

```python
# events/__init__.py
```

```python
# events/models.py
"""SQLAlchemy models for event aggregation."""
from datetime import datetime

from sqlalchemy import (
    DateTime, Float, Integer, String, Text,
    Index, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.models import Base


class Event(Base):
    """Aggregated event from cross-source narrative tag clustering."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    narrative_tag: Mapped[str] = mapped_column(String, nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    article_count: Mapped[int] = mapped_column(Integer, default=0)
    signal_score: Mapped[float] = mapped_column(Float, default=0.0)
    avg_relevance: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("idx_events_tag", "narrative_tag"),
        Index("idx_events_status", "status"),
        Index("idx_events_score", "signal_score"),
    )


class EventArticle(Base):
    """Many-to-many link between events and articles."""

    __tablename__ = "event_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(Integer, nullable=False)
    article_id: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("event_id", "article_id", name="uq_event_article"),
    )
```

- [ ] **Step 4: Update db/database.py to import new models**

Add after `from db.models import Base` (line 8):

```python
import events.models  # noqa: F401 — register Event/EventArticle with Base.metadata
```

- [ ] **Step 5: Update db/migrations.py — add events table creation**

Add to `run_migrations()` after the source_registry block (after line 84):

```python
    # Event aggregation tables
    if not _table_exists(engine, "events"):
        logger.info("Creating events table via migration")
        from events.models import Event
        Event.__table__.create(engine)
        logger.info("events table created")

    if not _table_exists(engine, "event_articles"):
        logger.info("Creating event_articles table via migration")
        from events.models import EventArticle
        EventArticle.__table__.create(engine)
        logger.info("event_articles table created")

    # Partial unique index: prevent duplicate active events for same tag
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_events_tag_active "
            "ON events (narrative_tag) WHERE status = 'active'"
        ))
        conn.commit()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/wendy/work/trading-co/park-intel && python -m pytest tests/test_event_models.py -v`
Expected: 3 tests PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add events/__init__.py events/models.py tests/test_event_models.py db/database.py db/migrations.py
git commit -m "feat: add Event and EventArticle models with migration"
```

---

## Task 2: Event Aggregation Logic

**Files:**
- Create: `events/aggregator.py`
- Create: `tests/test_event_aggregation.py`

- [ ] **Step 1: Write failing test for aggregation**

```python
# tests/test_event_aggregation.py
"""Tests for event aggregation logic."""
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base, Article
from events.models import Event, EventArticle


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _make_article(
    session: Session,
    source: str,
    narrative_tags: list[str],
    relevance: int = 3,
    hours_ago: float = 1.0,
) -> Article:
    now = datetime.utcnow()
    article = Article(
        source=source,
        source_id=f"{source}_{id(narrative_tags)}_{hours_ago}",
        title=f"Test {source}",
        narrative_tags=json.dumps(narrative_tags),
        relevance_score=relevance,
        published_at=now - timedelta(hours=hours_ago),
        collected_at=now - timedelta(hours=hours_ago),
    )
    session.add(article)
    session.commit()
    return article


def test_aggregate_creates_event(db_session: Session):
    from events.aggregator import run_aggregation

    _make_article(db_session, "hackernews", ["nvidia-earnings"], relevance=4, hours_ago=2)
    _make_article(db_session, "reddit", ["nvidia-earnings"], relevance=5, hours_ago=1)

    run_aggregation(db_session)

    events = db_session.query(Event).all()
    assert len(events) == 1
    event = events[0]
    assert event.narrative_tag == "nvidia-earnings"
    assert event.source_count == 2
    assert event.article_count == 2
    assert event.avg_relevance == 4.5
    assert event.signal_score == 9.0  # 2 sources × 4.5 avg


def test_aggregate_updates_existing_event(db_session: Session):
    from events.aggregator import run_aggregation

    _make_article(db_session, "hackernews", ["test-tag"], relevance=4, hours_ago=2)
    run_aggregation(db_session)

    events = db_session.query(Event).all()
    assert len(events) == 1
    assert events[0].source_count == 1

    # Add another article from different source
    _make_article(db_session, "rss", ["test-tag"], relevance=2, hours_ago=0.5)
    run_aggregation(db_session)

    events = db_session.query(Event).all()
    assert len(events) == 1
    assert events[0].source_count == 2
    assert events[0].article_count == 2


def test_aggregate_closes_expired_events(db_session: Session):
    from events.aggregator import run_aggregation

    now = datetime.utcnow()
    old_event = Event(
        narrative_tag="old-event",
        window_start=now - timedelta(hours=72),
        window_end=now - timedelta(hours=24),
        status="active",
    )
    db_session.add(old_event)
    db_session.commit()

    run_aggregation(db_session)

    refreshed = db_session.query(Event).filter(Event.id == old_event.id).first()
    assert refreshed.status == "closed"


def test_aggregate_uses_collected_at_when_published_at_null(db_session: Session):
    from events.aggregator import run_aggregation

    now = datetime.utcnow()
    article = Article(
        source="social_kol",
        source_id="kol_no_pub",
        title="No publish date",
        narrative_tags=json.dumps(["test-null-pub"]),
        relevance_score=3,
        published_at=None,
        collected_at=now - timedelta(hours=1),
    )
    db_session.add(article)
    db_session.commit()

    run_aggregation(db_session)

    events = db_session.query(Event).all()
    assert len(events) == 1
    assert events[0].window_start is not None


def test_aggregate_ignores_articles_without_narrative_tags(db_session: Session):
    from events.aggregator import run_aggregation

    now = datetime.utcnow()
    article = Article(
        source="rss",
        source_id="rss_no_tags",
        title="No tags",
        narrative_tags=None,
        collected_at=now - timedelta(hours=1),
    )
    db_session.add(article)
    db_session.commit()

    run_aggregation(db_session)

    events = db_session.query(Event).all()
    assert len(events) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/wendy/work/trading-co/park-intel && python -m pytest tests/test_event_aggregation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'events.aggregator'`

- [ ] **Step 3: Implement aggregation logic**

```python
# events/aggregator.py
"""Event aggregation — clusters articles by narrative_tag within 48h windows."""
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from db.models import Article
from events.models import Event, EventArticle

logger = logging.getLogger(__name__)

_WINDOW_HOURS = 48


def _parse_narrative_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(t).strip().lower() for t in parsed if t]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _article_timestamp(article: Article) -> datetime:
    """Return best available timestamp, falling back to collected_at."""
    return article.published_at or article.collected_at


def run_aggregation(session: Session) -> None:
    """Run one aggregation cycle: cluster recent articles into events."""
    now = datetime.utcnow()
    cutoff = now - timedelta(hours=_WINDOW_HOURS)

    # 1. Fetch recent articles with narrative tags
    articles = (
        session.query(Article)
        .filter(
            Article.collected_at >= cutoff,
            Article.narrative_tags.isnot(None),
            Article.narrative_tags != "",
            Article.narrative_tags != "[]",
        )
        .all()
    )

    # 2. Group articles by tag
    tag_articles: dict[str, list[Article]] = defaultdict(list)
    for article in articles:
        for tag in _parse_narrative_tags(article.narrative_tags):
            tag_articles[tag].append(article)

    # 3. For each tag, create or update event
    for tag, tag_arts in tag_articles.items():
        active_event = (
            session.query(Event)
            .filter(
                Event.narrative_tag == tag,
                Event.status == "active",
                Event.window_end > now,
            )
            .first()
        )

        if active_event is None:
            timestamps = [_article_timestamp(a) for a in tag_arts]
            earliest = min(timestamps)
            active_event = Event(
                narrative_tag=tag,
                window_start=earliest,
                window_end=earliest + timedelta(hours=_WINDOW_HOURS),
                status="active",
            )
            session.add(active_event)
            session.flush()

        # Link articles (check-then-insert to avoid IntegrityError rollback issues)
        for article in tag_arts:
            existing = (
                session.query(EventArticle)
                .filter_by(event_id=active_event.id, article_id=article.id)
                .first()
            )
            if existing is None:
                link = EventArticle(
                    event_id=active_event.id,
                    article_id=article.id,
                )
                session.add(link)
                session.flush()

        # Recalculate stats
        linked_article_ids = [
            ea.article_id
            for ea in session.query(EventArticle)
            .filter(EventArticle.event_id == active_event.id)
            .all()
        ]
        linked_articles = (
            session.query(Article)
            .filter(Article.id.in_(linked_article_ids))
            .all()
        )

        sources = {a.source for a in linked_articles}
        relevances = [
            a.relevance_score for a in linked_articles
            if a.relevance_score is not None
        ]
        avg_rel = sum(relevances) / len(relevances) if relevances else 0.0

        active_event.source_count = len(sources)
        active_event.article_count = len(linked_articles)
        active_event.avg_relevance = round(avg_rel, 2)
        active_event.signal_score = round(len(sources) * avg_rel, 2)
        active_event.updated_at = now

    # 4. Close expired events
    expired = (
        session.query(Event)
        .filter(Event.status == "active", Event.window_end < now)
        .all()
    )
    for event in expired:
        event.status = "closed"
        event.updated_at = now

    session.commit()
    logger.info(
        "Aggregation complete: %d tags processed, %d events closed",
        len(tag_articles),
        len(expired),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/wendy/work/trading-co/park-intel && python -m pytest tests/test_event_aggregation.py -v`
Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add events/aggregator.py tests/test_event_aggregation.py
git commit -m "feat: add event aggregation logic with 48h window clustering"
```

---

## Task 3: Event API Endpoints

**Files:**
- Create: `api/event_routes.py`
- Create: `tests/test_event_api.py`
- Modify: `main.py:12-69`

- [ ] **Step 1: Write failing test for event API**

```python
# tests/test_event_api.py
"""Tests for event API endpoints."""
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from db.models import Base, Article
from events.models import Event, EventArticle


@pytest.fixture
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("config.DB_PATH", db_path)
    monkeypatch.setattr("config.DATA_DIR", tmp_path)

    from db.database import get_engine, get_session
    import db.database as db_mod
    db_mod._engine = None
    db_mod._SessionFactory = None

    from main import app
    engine = get_engine()
    Base.metadata.create_all(engine)

    # Seed test data
    session = get_session()
    now = datetime.utcnow()
    event = Event(
        narrative_tag="test-event",
        window_start=now - timedelta(hours=2),
        window_end=now + timedelta(hours=46),
        source_count=2,
        article_count=3,
        signal_score=8.0,
        avg_relevance=4.0,
        status="active",
    )
    session.add(event)
    session.commit()

    article = Article(
        source="hackernews",
        source_id="hn_test_evt",
        title="Test article for event",
        narrative_tags=json.dumps(["test-event"]),
        relevance_score=4,
        collected_at=now,
    )
    session.add(article)
    session.commit()

    link = EventArticle(event_id=event.id, article_id=article.id)
    session.add(link)
    session.commit()
    session.close()

    with TestClient(app) as c:
        yield c


def test_get_active_events(client):
    resp = client.get("/api/events/active")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert len(data["events"]) >= 1
    event = data["events"][0]
    assert event["narrative_tag"] == "test-event"
    assert "sources" in event


def test_get_event_detail(client):
    # Get event ID first
    events = client.get("/api/events/active").json()["events"]
    event_id = events[0]["id"]

    resp = client.get(f"/api/events/{event_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["event"]["narrative_tag"] == "test-event"
    assert len(data["articles"]) >= 1


def test_get_event_not_found(client):
    resp = client.get("/api/events/99999")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/wendy/work/trading-co/park-intel && python -m pytest tests/test_event_api.py -v`
Expected: FAIL — import error or 404

- [ ] **Step 3: Implement event routes**

```python
# api/event_routes.py
"""Event aggregation API endpoints."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func

from db.database import get_session
from db.models import Article
from events.models import Event, EventArticle

event_router = APIRouter(prefix="/api")


@event_router.get("/events/active")
def get_active_events(
    limit: int = Query(default=20, ge=1, le=100),
    min_score: float = Query(default=0.0, ge=0),
) -> dict[str, Any]:
    session = get_session()
    try:
        events = (
            session.query(Event)
            .filter(Event.status == "active", Event.signal_score >= min_score)
            .order_by(Event.signal_score.desc())
            .limit(limit)
            .all()
        )

        result = []
        for event in events:
            # Get distinct sources for this event
            source_rows = (
                session.query(Article.source)
                .join(EventArticle, EventArticle.article_id == Article.id)
                .filter(EventArticle.event_id == event.id)
                .distinct()
                .all()
            )
            sources = [row[0] for row in source_rows]

            result.append({
                "id": event.id,
                "narrative_tag": event.narrative_tag,
                "source_count": event.source_count,
                "article_count": event.article_count,
                "signal_score": event.signal_score,
                "avg_relevance": event.avg_relevance,
                "window_start": event.window_start.isoformat() if event.window_start else None,
                "window_end": event.window_end.isoformat() if event.window_end else None,
                "status": event.status,
                "sources": sources,
            })

        return {"events": result}
    finally:
        session.close()


@event_router.get("/events/{event_id}")
def get_event_detail(event_id: int) -> dict[str, Any]:
    session = get_session()
    try:
        event = session.query(Event).filter(Event.id == event_id).first()
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        linked = (
            session.query(Article)
            .join(EventArticle, EventArticle.article_id == Article.id)
            .filter(EventArticle.event_id == event.id)
            .order_by(Article.collected_at.desc())
            .all()
        )

        def _parse_tags(raw: str | None) -> list[str]:
            if not raw:
                return []
            try:
                parsed = json.loads(raw)
                return [str(t) for t in parsed] if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                return []

        articles = [
            {
                "id": a.id,
                "title": a.title,
                "source": a.source,
                "url": a.url,
                "relevance_score": a.relevance_score,
                "tags": _parse_tags(a.tags),
                "published_at": a.published_at.isoformat() if a.published_at else None,
                "collected_at": a.collected_at.isoformat() if a.collected_at else None,
            }
            for a in linked
        ]

        return {
            "event": {
                "id": event.id,
                "narrative_tag": event.narrative_tag,
                "source_count": event.source_count,
                "article_count": event.article_count,
                "signal_score": event.signal_score,
                "avg_relevance": event.avg_relevance,
                "window_start": event.window_start.isoformat() if event.window_start else None,
                "window_end": event.window_end.isoformat() if event.window_end else None,
                "status": event.status,
            },
            "articles": articles,
        }
    finally:
        session.close()
```

- [ ] **Step 4: Register router in main.py**

Add import (after line 13):
```python
from api.event_routes import event_router
```

Add router registration (after line 69):
```python
app.include_router(event_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/wendy/work/trading-co/park-intel && python -m pytest tests/test_event_api.py -v`
Expected: 3 tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add api/event_routes.py tests/test_event_api.py main.py
git commit -m "feat: add event API endpoints (/api/events/active, /api/events/{id})"
```

---

## Task 4: Scheduler Integration + Feed Context Rail

**Files:**
- Modify: `scheduler.py:197-249`
- Modify: `api/ui_routes.py:273-342`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/components/ContextRail.tsx`

- [ ] **Step 1: Add aggregation job to scheduler**

In `scheduler.py`, add the aggregation runner function (before `class CollectorScheduler`):

```python
def _run_event_aggregation() -> None:
    """Run event aggregation on recent articles."""
    from db.database import get_session
    from events.aggregator import run_aggregation

    session = get_session()
    try:
        run_aggregation(session)
    except Exception:
        logger.exception("Event aggregation failed")
    finally:
        session.close()
```

In `_register_jobs()` (after the LLM tagger registration, around line 249), add:

```python
        # Event aggregation (every 1 hour)
        aggregation_start = base_time + timedelta(seconds=30 * (len(jobs) + 1))
        self._scheduler.add_job(
            _run_event_aggregation,
            trigger=IntervalTrigger(hours=1),
            id="event-aggregation",
            replace_existing=True,
            next_run_time=aggregation_start,
        )
        logger.info("Registered event aggregation job (every 1h)")
```

- [ ] **Step 2: Add top_events to feed context rail**

In `api/ui_routes.py`, add a helper function (after `_build_source_health`, around line 267):

```python
def _build_top_events(session: Any) -> list[dict[str, Any]]:
    """Fetch top active events by signal score."""
    from events.models import Event

    events = (
        session.query(Event)
        .filter(Event.status == "active")
        .order_by(Event.signal_score.desc())
        .limit(5)
        .all()
    )
    return [
        {
            "id": e.id,
            "narrative_tag": e.narrative_tag,
            "signal_score": e.signal_score,
            "source_count": e.source_count,
            "article_count": e.article_count,
        }
        for e in events
    ]
```

In `get_feed()`, add `top_events` to the context dict (around line 334):

```python
            "context": {
                "rising_topics": _build_rising_topics(context_articles, now),
                "source_health": _build_source_health(session),
                "top_events": _build_top_events(session),
            },
```

- [ ] **Step 3: Update frontend types**

Add to `frontend/src/types/api.ts`:

```typescript
export interface TopEvent {
  id: number;
  narrative_tag: string;
  signal_score: number;
  source_count: number;
  article_count: number;
}
```

Update `FeedContext`:
```typescript
export interface FeedContext {
  rising_topics: RisingTopic[];
  source_health: SourceHealth[];
  top_events?: TopEvent[];
}
```

- [ ] **Step 4: Update ContextRail to show top events**

In `frontend/src/components/ContextRail.tsx`, add after the `rising` section (after the `rising.length > 0` block):

```tsx
        {context?.top_events && context.top_events.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Active Events</p>
            <ul className="space-y-1.5">
              {context.top_events.slice(0, 5).map((e) => (
                <li key={e.id} className="text-sm">
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-gray-700 truncate">{e.narrative_tag.replace(/-/g, " ")}</span>
                    <span className="text-xs text-orange-500 font-medium shrink-0">{e.signal_score.toFixed(1)}</span>
                  </div>
                  <span className="text-xs text-gray-400">{e.source_count} sources · {e.article_count} articles</span>
                </li>
              ))}
            </ul>
          </div>
        )}
```

- [ ] **Step 5: Run existing tests to verify no regression**

Run: `cd /Users/wendy/work/trading-co/park-intel && python -m pytest tests/ -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add scheduler.py api/ui_routes.py frontend/src/types/api.ts frontend/src/components/ContextRail.tsx
git commit -m "feat: integrate event aggregation into scheduler and feed context rail"
```

---

## Task 5: User Profile Model + Service

**Files:**
- Create: `users/__init__.py`
- Create: `users/models.py`
- Create: `users/service.py`
- Create: `tests/test_user_profiles.py`
- Modify: `db/database.py`
- Modify: `db/migrations.py`

- [ ] **Step 1: Write failing test for user profiles**

```python
# tests/test_user_profiles.py
"""Tests for user profile CRUD and weight validation."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base
from users.models import UserProfile


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_create_user(db_session):
    from users.service import create_user

    user = create_user(db_session, "wendy", "Wendy")
    assert user.username == "wendy"
    assert user.display_name == "Wendy"
    assert user.topic_weights == "{}"


def test_get_user(db_session):
    from users.service import create_user, get_user

    create_user(db_session, "wendy", "Wendy")
    user = get_user(db_session, "wendy")
    assert user is not None
    assert user.username == "wendy"


def test_get_user_not_found(db_session):
    from users.service import get_user

    user = get_user(db_session, "ghost")
    assert user is None


def test_update_weights_valid(db_session):
    from users.service import create_user, update_weights

    create_user(db_session, "wendy", "Wendy")
    updated = update_weights(db_session, "wendy", {"ai": 2.0, "macro": 1.5})
    assert updated is not None

    import json
    weights = json.loads(updated.topic_weights)
    assert weights["ai"] == 2.0
    assert weights["macro"] == 1.5


def test_update_weights_invalid_topic(db_session):
    from users.service import create_user, update_weights, InvalidWeightsError

    create_user(db_session, "wendy", "Wendy")
    with pytest.raises(InvalidWeightsError, match="Unknown topic"):
        update_weights(db_session, "wendy", {"fake_topic": 1.0})


def test_update_weights_out_of_range(db_session):
    from users.service import create_user, update_weights, InvalidWeightsError

    create_user(db_session, "wendy", "Wendy")
    with pytest.raises(InvalidWeightsError, match="out of range"):
        update_weights(db_session, "wendy", {"ai": 5.0})


def test_update_weights_immutability(db_session):
    """Verify that updating weights doesn't mutate the original object."""
    from users.service import create_user, update_weights

    create_user(db_session, "wendy", "Wendy")
    original = db_session.query(UserProfile).filter_by(username="wendy").first()
    original_weights = original.topic_weights

    update_weights(db_session, "wendy", {"ai": 2.5})

    # The original string should not have been mutated
    refreshed = db_session.query(UserProfile).filter_by(username="wendy").first()
    assert refreshed.topic_weights != original_weights


def test_duplicate_username_raises(db_session):
    from sqlalchemy.exc import IntegrityError
    from users.service import create_user

    create_user(db_session, "wendy", "Wendy")
    with pytest.raises(IntegrityError):
        create_user(db_session, "wendy", "Wendy 2")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/wendy/work/trading-co/park-intel && python -m pytest tests/test_user_profiles.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'users'`

- [ ] **Step 3: Create UserProfile model**

```python
# users/__init__.py
```

```python
# users/models.py
"""SQLAlchemy model for user profiles."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.models import Base


class UserProfile(Base):
    """Per-user profile with topic weight preferences."""

    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    topic_weights: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
    )
```

- [ ] **Step 4: Create user service with validation**

```python
# users/service.py
"""User profile CRUD operations with weight validation."""
import json
from sqlalchemy.orm import Session

from users.models import UserProfile

VALID_TOPICS = frozenset([
    "ai", "crypto", "macro", "geopolitics", "china-market", "us-market",
    "sector/tech", "sector/finance", "sector/energy",
    "trading", "regulation", "earnings", "commodities",
])

_WEIGHT_MIN = 0.0
_WEIGHT_MAX = 3.0


class InvalidWeightsError(ValueError):
    """Raised when topic weights fail validation."""


def create_user(session: Session, username: str, display_name: str) -> UserProfile:
    """Create a new user profile."""
    user = UserProfile(username=username, display_name=display_name)
    session.add(user)
    session.commit()
    return user


def get_user(session: Session, username: str) -> UserProfile | None:
    """Get a user profile by username."""
    return session.query(UserProfile).filter_by(username=username).first()


def list_users(session: Session) -> list[UserProfile]:
    """List all user profiles."""
    return session.query(UserProfile).order_by(UserProfile.username).all()


def update_weights(
    session: Session,
    username: str,
    weights: dict[str, float],
) -> UserProfile | None:
    """Update topic weights for a user. Creates a new JSON string (immutable pattern).

    Validates:
    - All keys must be known topic categories
    - All values must be in [0.0, 3.0]
    """
    # Validate keys
    unknown = set(weights.keys()) - VALID_TOPICS
    if unknown:
        raise InvalidWeightsError(f"Unknown topic(s): {', '.join(sorted(unknown))}")

    # Validate values
    for topic, value in weights.items():
        if not (_WEIGHT_MIN <= value <= _WEIGHT_MAX):
            raise InvalidWeightsError(
                f"Weight for '{topic}' is {value}, out of range [{_WEIGHT_MIN}, {_WEIGHT_MAX}]"
            )

    user = get_user(session, username)
    if user is None:
        return None

    # Immutable update: create new JSON string, don't mutate existing
    new_weights_json = json.dumps(weights, ensure_ascii=False)
    user.topic_weights = new_weights_json
    session.commit()
    return user
```

- [ ] **Step 5: Update db/database.py and db/migrations.py**

In `db/database.py`, add import (after existing events import):
```python
import users.models  # noqa: F401 — register UserProfile with Base.metadata
```

In `db/migrations.py`, add to `run_migrations()`:
```python
    if not _table_exists(engine, "user_profiles"):
        logger.info("Creating user_profiles table via migration")
        from users.models import UserProfile
        UserProfile.__table__.create(engine)
        logger.info("user_profiles table created")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/wendy/work/trading-co/park-intel && python -m pytest tests/test_user_profiles.py -v`
Expected: 8 tests PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add users/__init__.py users/models.py users/service.py tests/test_user_profiles.py db/database.py db/migrations.py
git commit -m "feat: add user profile model and service with weight validation"
```

---

## Task 6: User API Endpoints

**Files:**
- Create: `api/user_routes.py`
- Modify: `main.py`

- [ ] **Step 1: Implement user routes**

```python
# api/user_routes.py
"""User profile API endpoints."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from db.database import get_session
from users.service import (
    InvalidWeightsError,
    create_user,
    get_user,
    list_users,
    update_weights,
)

user_router = APIRouter(prefix="/api")


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    display_name: str = Field(..., min_length=1, max_length=100)


class UpdateWeightsRequest(BaseModel):
    weights: dict[str, float]


def _user_response(user) -> dict[str, Any]:
    return {
        "username": user.username,
        "display_name": user.display_name,
        "topic_weights": json.loads(user.topic_weights or "{}"),
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@user_router.post("/users")
def create_user_endpoint(req: CreateUserRequest) -> dict[str, Any]:
    session = get_session()
    try:
        from sqlalchemy.exc import IntegrityError
        try:
            user = create_user(session, req.username, req.display_name)
            return _user_response(user)
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=409, detail="Username already exists")
    finally:
        session.close()


@user_router.get("/users")
def list_users_endpoint() -> list[dict[str, Any]]:
    session = get_session()
    try:
        users = list_users(session)
        return [_user_response(u) for u in users]
    finally:
        session.close()


@user_router.get("/users/{username}")
def get_user_endpoint(username: str) -> dict[str, Any]:
    session = get_session()
    try:
        user = get_user(session, username)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return _user_response(user)
    finally:
        session.close()


@user_router.put("/users/{username}/weights")
def update_weights_endpoint(username: str, req: UpdateWeightsRequest) -> dict[str, Any]:
    session = get_session()
    try:
        try:
            user = update_weights(session, username, req.weights)
        except InvalidWeightsError as e:
            raise HTTPException(status_code=422, detail=str(e))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return _user_response(user)
    finally:
        session.close()
```

- [ ] **Step 2: Register router in main.py**

Add import:
```python
from api.user_routes import user_router
```

Add registration:
```python
app.include_router(user_router)
```

- [ ] **Step 3: Run all tests**

Run: `cd /Users/wendy/work/trading-co/park-intel && python -m pytest tests/ -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add api/user_routes.py main.py
git commit -m "feat: add user profile API endpoints (CRUD + weight management)"
```

---

## Task 7: Personalized Feed Ranking

**Files:**
- Create: `tests/test_personalized_feed.py`
- Modify: `api/ui_routes.py:273-342`

- [ ] **Step 1: Write failing test for personalized feed**

```python
# tests/test_personalized_feed.py
"""Tests for personalized feed ranking."""
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from db.models import Base, Article
from users.models import UserProfile


@pytest.fixture
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("config.DB_PATH", db_path)
    monkeypatch.setattr("config.DATA_DIR", tmp_path)

    import db.database as db_mod
    db_mod._engine = None
    db_mod._SessionFactory = None

    from db.database import get_engine, get_session
    from main import app
    engine = get_engine()
    Base.metadata.create_all(engine)

    session = get_session()
    now = datetime.utcnow()

    # Create user with high AI weight, zero crypto weight
    user = UserProfile(
        username="wendy",
        display_name="Wendy",
        topic_weights=json.dumps({"ai": 3.0, "crypto": 0.0}),
    )
    session.add(user)

    # AI article (should rank higher for wendy)
    session.add(Article(
        source="hackernews", source_id="hn_ai",
        title="AI breakthrough", tags=json.dumps(["ai"]),
        relevance_score=3, collected_at=now - timedelta(hours=1),
    ))
    # Crypto article (should be hidden for wendy)
    session.add(Article(
        source="reddit", source_id="reddit_crypto",
        title="BTC moon", tags=json.dumps(["crypto"]),
        relevance_score=4, collected_at=now - timedelta(hours=1),
    ))
    # Macro article (default weight 1.0)
    session.add(Article(
        source="google_news", source_id="gn_macro",
        title="Fed decision", tags=json.dumps(["macro"]),
        relevance_score=3, collected_at=now - timedelta(hours=1),
    ))

    session.commit()
    session.close()

    with TestClient(app) as c:
        yield c


def test_feed_without_user_returns_all(client):
    resp = client.get("/api/ui/feed?min_relevance=1&window=24h")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 3


def test_feed_with_user_filters_zero_weight(client):
    resp = client.get("/api/ui/feed?user=wendy&min_relevance=1&window=24h")
    assert resp.status_code == 200
    items = resp.json()["items"]
    # Crypto article should be filtered out (weight 0.0)
    sources = [i["source"] for i in items]
    assert "reddit" not in sources
    assert len(items) == 2


def test_feed_with_user_boosts_high_weight(client):
    resp = client.get("/api/ui/feed?user=wendy&min_relevance=1&window=24h")
    items = resp.json()["items"]
    # AI article (weight 3.0) should rank first
    assert items[0]["tags"] == ["ai"] or "ai" in items[0]["tags"]


def test_feed_with_unknown_user_returns_normal(client):
    resp = client.get("/api/ui/feed?user=nobody&min_relevance=1&window=24h")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/wendy/work/trading-co/park-intel && python -m pytest tests/test_personalized_feed.py -v`
Expected: FAIL — `user` param not recognized or no filtering

- [ ] **Step 3: Add personalization to get_feed()**

In `api/ui_routes.py`, modify `get_feed()`:

Add `user` parameter to function signature:
```python
    user: str | None = Query(default=None),
```

After the scoring block (`scored = [(a, _priority_score(a, now)) for a in articles]`, around line 305), add personalization:

```python
        # Personalize if user specified
        if user:
            from users.service import get_user as get_user_profile
            import json as _json

            profile = get_user_profile(session, user)
            if profile:
                user_weights = _json.loads(profile.topic_weights or "{}")
                personalized = []
                for article, base_score in scored:
                    article_tags = _parse_tags(article.tags)
                    matching_weights = [
                        user_weights[t] for t in article_tags if t in user_weights
                    ]
                    weight = max(matching_weights) if matching_weights else 1.0
                    new_score = base_score * weight
                    if new_score > 0.0 or not matching_weights:
                        personalized.append((article, round(new_score, 4)))
                    # If new_score == 0.0 AND there were matching weights, filter out
                scored = personalized
                scored.sort(key=lambda x: (-x[1], -x[0].id))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/wendy/work/trading-co/park-intel && python -m pytest tests/test_personalized_feed.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: Run all tests for regression**

Run: `cd /Users/wendy/work/trading-co/park-intel && python -m pytest tests/ -v --timeout=30`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add api/ui_routes.py tests/test_personalized_feed.py
git commit -m "feat: add personalized feed ranking with per-user topic weights"
```

---

## Task 8: Frontend — User Selector + Settings Page

**Files:**
- Create: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/pages/FeedPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add user types to api.ts**

```typescript
// Add to frontend/src/types/api.ts
export interface UserProfile {
  username: string;
  display_name: string;
  topic_weights: Record<string, number>;
  created_at: string | null;
}
```

- [ ] **Step 2: Add user API methods to client.ts**

```typescript
// Add to the api object in frontend/src/api/client.ts

  users: (): Promise<UserProfile[]> =>
    get("/api/users"),

  user: (username: string): Promise<UserProfile> =>
    get(`/api/users/${encodeURIComponent(username)}`),

  updateWeights: async (username: string, weights: Record<string, number>): Promise<UserProfile> => {
    const res = await fetch(`${BASE}/api/users/${encodeURIComponent(username)}/weights`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ weights }),
    });
    if (!res.ok) throw new Error(`API error ${res.status}`);
    return res.json();
  },
```

Add `UserProfile` to the import from types.

- [ ] **Step 3: Update FeedParams and feed function**

In `client.ts`, add `user` to `FeedParams`:
```typescript
export interface FeedParams {
  source?: string;
  topic?: string;
  min_relevance?: number;
  window?: string;
  limit?: number;
  cursor?: string;
  user?: string;
}
```

- [ ] **Step 4: Create SettingsPage**

```tsx
// frontend/src/pages/SettingsPage.tsx
import { useState, useRef, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useSearchParams } from "react-router-dom";

const TOPICS = [
  "ai", "crypto", "macro", "geopolitics", "china-market", "us-market",
  "sector/tech", "sector/finance", "sector/energy",
  "trading", "regulation", "earnings", "commodities",
];

export function SettingsPage() {
  const [params] = useSearchParams();
  const username = params.get("user") ?? "";
  const queryClient = useQueryClient();

  const { data: user, isLoading } = useQuery({
    queryKey: ["user", username],
    queryFn: () => api.user(username),
    enabled: !!username,
  });

  const mutation = useMutation({
    mutationFn: (weights: Record<string, number>) =>
      api.updateWeights(username, weights),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user", username] });
    },
  });

  // Local state for immediate slider feedback, debounced API calls
  const [localWeights, setLocalWeights] = useState<Record<string, number>>({});
  const timerRef = useRef<ReturnType<typeof setTimeout>>();
  const weights = { ...(user?.topic_weights ?? {}), ...localWeights };

  const handleChange = useCallback((topic: string, value: number) => {
    setLocalWeights((prev) => ({ ...prev, [topic]: value }));
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      const updated = { ...(user?.topic_weights ?? {}), ...localWeights, [topic]: value };
      mutation.mutate(updated);
      setLocalWeights({});
    }, 500);
  }, [user, localWeights, mutation]);

  if (!username) {
    return <div className="text-sm text-gray-500 py-8">Select a user from the sidebar to configure weights.</div>;
  }

  if (isLoading) {
    return <div className="animate-pulse space-y-3">{[...Array(5)].map((_, i) => <div key={i} className="h-8 bg-gray-100 rounded" />)}</div>;
  }

  return (
    <div className="max-w-lg">
      <h2 className="text-lg font-semibold text-gray-800 mb-1">Topic Weights</h2>
      <p className="text-sm text-gray-500 mb-4">{user?.display_name} — adjust topic importance (0 = hide, 3 = max boost)</p>
      <div className="space-y-3">
        {TOPICS.map((topic) => {
          const val = weights[topic] ?? 1.0;
          return (
            <div key={topic} className="flex items-center gap-3">
              <span className="text-sm text-gray-700 w-32 truncate">{topic}</span>
              <input
                type="range"
                min={0} max={3} step={0.5}
                value={val}
                onChange={(e) => handleChange(topic, parseFloat(e.target.value))}
                className="flex-1 accent-brand-600"
              />
              <span className="text-xs text-gray-500 w-8 text-right">{val.toFixed(1)}</span>
            </div>
          );
        })}
      </div>
      {mutation.isError && <p className="text-sm text-red-500 mt-2">Failed to save.</p>}
    </div>
  );
}
```

- [ ] **Step 5: Update Sidebar with user selector**

In `frontend/src/components/Sidebar.tsx`, add user selector. Add state at top and a `<select>` before the Feed section:

```tsx
// Add imports
import { useState } from "react";

// Inside Sidebar component, add:
const [activeUser, setActiveUser] = useState<string>("");

// Add user selector dropdown before the Feed section:
<div>
  <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">User</p>
  <select
    value={activeUser}
    onChange={(e) => setActiveUser(e.target.value)}
    className="w-full text-sm border border-gray-300 rounded px-2 py-1 bg-white text-gray-700"
  >
    <option value="">Default</option>
    <option value="wendy">Wendy</option>
    <option value="monica">Monica</option>
  </select>
</div>
```

Note: The active user state needs to be lifted to a shared context or URL params so FeedPage can read it. The simplest approach: use URL search params. Update Sidebar to navigate with `?user=xxx`:

```tsx
import { useNavigate, useSearchParams } from "react-router-dom";

// Inside component:
const navigate = useNavigate();
const [searchParams] = useSearchParams();
const activeUser = searchParams.get("user") ?? "";

// On change:
onChange={(e) => {
  const val = e.target.value;
  if (val) navigate(`/?user=${val}`);
  else navigate("/");
}}
```

- [ ] **Step 6: Update FeedPage to pass user param**

In `frontend/src/pages/FeedPage.tsx`, read user from URL and pass to API:

```tsx
import { useSearchParams } from "react-router-dom";

// Inside component:
const [searchParams] = useSearchParams();
const activeUser = searchParams.get("user") ?? undefined;

// Update queryKey and feed call:
queryKey: ["feed", minRelevance, window, activeUser],
queryFn: ({ pageParam }) =>
  api.feed({
    min_relevance: minRelevance,
    window,
    limit: 20,
    cursor: pageParam as string | undefined,
    user: activeUser,
  }),
```

- [ ] **Step 7: Update App.tsx with Settings route**

```tsx
import { SettingsPage } from "./pages/SettingsPage";

// Add route:
<Route path="/settings" element={<SettingsPage />} />
```

Add Settings link in Sidebar (after user selector):
```tsx
<Link
  to={activeUser ? `/settings?user=${activeUser}` : "/settings"}
  className="text-xs text-gray-500 hover:text-brand-600 mt-1 block"
>
  Settings
</Link>
```

- [ ] **Step 8: Build frontend**

Run: `cd /Users/wendy/work/trading-co/park-intel/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 9: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add frontend/src/
git commit -m "feat: add user selector, settings page, and personalized feed in frontend"
```

---

## Task 9: Ticker Extraction

**Files:**
- Create: `tagging/tickers.py`
- Create: `tests/test_ticker_extraction.py`
- Modify: `config.py`
- Modify: `tagging/__init__.py`
- Modify: `db/models.py:40-66`
- Modify: `db/migrations.py`
- Modify: `collectors/base.py:31-72`
- Modify: `collectors/yahoo_finance.py:79-93`

- [ ] **Step 1: Write failing test for ticker extraction**

```python
# tests/test_ticker_extraction.py
"""Tests for ticker extraction from article text."""
import pytest


def test_extract_cashtag():
    from tagging.tickers import extract_tickers
    tickers = extract_tickers("Check out $NVDA and $AAPL today", "Great earnings")
    assert "NVDA" in tickers
    assert "AAPL" in tickers


def test_extract_company_name():
    from tagging.tickers import extract_tickers
    tickers = extract_tickers("NVIDIA reports record revenue", "")
    assert "NVDA" in tickers


def test_extract_chinese_company_name():
    from tagging.tickers import extract_tickers
    tickers = extract_tickers("英伟达财报超预期", "")
    assert "NVDA" in tickers


def test_extract_case_insensitive():
    from tagging.tickers import extract_tickers
    tickers = extract_tickers("nvidia beats expectations", "")
    assert "NVDA" in tickers


def test_extract_deduplicates():
    from tagging.tickers import extract_tickers
    tickers = extract_tickers("$NVDA NVIDIA 英伟达", "NVIDIA again")
    assert tickers.count("NVDA") == 1


def test_extract_no_tickers():
    from tagging.tickers import extract_tickers
    tickers = extract_tickers("General news about nothing", "Some content")
    assert tickers == []


def test_extract_from_yahoo_source():
    from tagging.tickers import extract_tickers
    tickers = extract_tickers("Gold prices rise", "", source_tickers=["GC=F", "GLD"])
    assert "GC=F" in tickers
    assert "GLD" in tickers


def test_title_and_content_both_scanned():
    from tagging.tickers import extract_tickers
    tickers = extract_tickers("Market update", "$TSLA is up 5%")
    assert "TSLA" in tickers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/wendy/work/trading-co/park-intel && python -m pytest tests/test_ticker_extraction.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Add TICKER_ALIASES to config.py**

Add at the end of `config.py`:

```python
# --- Ticker Extraction ---
QUANT_API_BASE_URL = os.getenv("QUANT_API_BASE_URL", "http://localhost:8000")

TICKER_ALIASES: dict[str, str] = {
    # US Tech
    "NVIDIA": "NVDA", "英伟达": "NVDA",
    "APPLE": "AAPL", "苹果": "AAPL",
    "MICROSOFT": "MSFT", "微软": "MSFT",
    "GOOGLE": "GOOGL", "ALPHABET": "GOOGL", "谷歌": "GOOGL",
    "AMAZON": "AMZN", "亚马逊": "AMZN",
    "META": "META", "FACEBOOK": "META",
    "TESLA": "TSLA", "特斯拉": "TSLA",
    "NETFLIX": "NFLX",
    "AMD": "AMD", "超威半导体": "AMD",
    "INTEL": "INTC", "英特尔": "INTC",
    "TSMC": "TSM", "台积电": "TSM",
    "ASML": "ASML",
    "BROADCOM": "AVGO", "博通": "AVGO",
    "QUALCOMM": "QCOM", "高通": "QCOM",
    # Finance
    "JPMORGAN": "JPM", "摩根大通": "JPM",
    "GOLDMAN SACHS": "GS", "高盛": "GS",
    "BERKSHIRE": "BRK.B", "伯克希尔": "BRK.B",
    # Commodities / Gold
    "NEWMONT": "NEM",
    "BARRICK": "GOLD", "巴里克": "GOLD",
    # Crypto-adjacent
    "COINBASE": "COIN",
    "MICROSTRATEGY": "MSTR",
    # Chinese ADR
    "ALIBABA": "BABA", "阿里巴巴": "BABA",
    "TENCENT": "TCEHY", "腾讯": "TCEHY",
    "BAIDU": "BIDU", "百度": "BIDU",
    "JD.COM": "JD", "京东": "JD",
    "PINDUODUO": "PDD", "拼多多": "PDD",
    "NIO": "NIO", "蔚来": "NIO",
    "BYDCOMPANY": "BYDDY", "比亚迪": "BYDDY",
}
```

- [ ] **Step 4: Implement ticker extraction**

```python
# tagging/tickers.py
"""Ticker extraction from article text."""
import re
from config import TICKER_ALIASES

_CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")

# Build case-insensitive lookup (keys uppercased for non-CJK, original for CJK)
_ALIAS_LOOKUP: dict[str, str] = {}
for name, ticker in TICKER_ALIASES.items():
    _ALIAS_LOOKUP[name.upper()] = ticker
    # Keep original for CJK characters (already case-insensitive by nature)
    if any("\u4e00" <= ch <= "\u9fff" for ch in name):
        _ALIAS_LOOKUP[name] = ticker


def extract_tickers(
    title: str | None,
    content: str | None,
    source_tickers: list[str] | None = None,
) -> list[str]:
    """Extract stock tickers from article text.

    Rules (applied in order, deduplicated):
    1. $TICKER cashtag format
    2. Company name → ticker alias mapping (case-insensitive)
    3. Source-provided tickers (e.g., Yahoo Finance)
    """
    found: list[str] = []
    seen: set[str] = set()

    title = title or ""
    content = (content or "")[:2000]
    text = f"{title} {content}"

    def _add(ticker: str) -> None:
        if ticker not in seen:
            seen.add(ticker)
            found.append(ticker)

    # Rule 1: Cashtags
    for match in _CASHTAG_RE.findall(text):
        _add(match)

    # Rule 2: Company name aliases
    text_upper = text.upper()
    for alias, ticker in _ALIAS_LOOKUP.items():
        # CJK: search in original text
        if any("\u4e00" <= ch <= "\u9fff" for ch in alias):
            if alias in text:
                _add(ticker)
        else:
            # Non-CJK: word boundary match in uppercased text
            if re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", text_upper):
                _add(ticker)

    # Rule 3: Source-provided tickers
    if source_tickers:
        for ticker in source_tickers:
            _add(ticker)

    return found
```

- [ ] **Step 5: Update tagging/__init__.py**

```python
from tagging.keywords import tag_article
from tagging.tickers import extract_tickers

__all__ = ["tag_article", "extract_tickers"]
```

- [ ] **Step 6: Add tickers field to Article model**

In `db/models.py`, add after `narrative_tags` (line 55):

```python
    tickers: Mapped[str | None] = mapped_column(String, nullable=True)  # JSON array
```

In `db/migrations.py`, add to the `migrations` list:

```python
        ("articles", "tickers", "TEXT"),
```

- [ ] **Step 7: Update BaseCollector.save() to extract tickers**

In `collectors/base.py`, update import (line 13):
```python
from tagging import tag_article, extract_tickers
```

In `save()`, after `merged_tags` (around line 45), add:
```python
                # Extract tickers
                source_tickers = data.get("tickers", None)
                if isinstance(source_tickers, str):
                    try:
                        import json as _json
                        source_tickers = _json.loads(source_tickers)
                    except (json.JSONDecodeError, TypeError):
                        source_tickers = None
                tickers = extract_tickers(data.get("title"), data.get("content"), source_tickers)
```

In the `Article(...)` constructor, add:
```python
                    tickers=json.dumps(tickers) if tickers else None,
```

- [ ] **Step 8: Update Yahoo Finance collector**

In `collectors/yahoo_finance.py`, in `_fetch_ticker_news()`, add `tickers` to the article dict (around line 82-92):

```python
            articles.append({
                ...existing fields...,
                "tickers": [symbol],
            })
```

And in the keyword search section (around line 173-183):
```python
                    all_articles.append({
                        ...existing fields...,
                        "tickers": [],  # keyword search has no specific ticker
                    })
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd /Users/wendy/work/trading-co/park-intel && python -m pytest tests/test_ticker_extraction.py -v`
Expected: 8 tests PASS

- [ ] **Step 10: Run all tests for regression**

Run: `cd /Users/wendy/work/trading-co/park-intel && python -m pytest tests/ -v --timeout=30`
Expected: All PASS

- [ ] **Step 11: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add tagging/tickers.py tagging/__init__.py config.py db/models.py db/migrations.py collectors/base.py collectors/yahoo_finance.py tests/test_ticker_extraction.py
git commit -m "feat: add ticker extraction with cashtag, alias, and yahoo source support"
```

---

## Task 10: Ticker Backfill Script

**Files:**
- Create: `scripts/backfill_tickers.py`

- [ ] **Step 1: Create backfill script**

```python
# scripts/backfill_tickers.py
"""One-time backfill: extract tickers for existing articles.

Uses a processed marker ('[]') to distinguish unprocessed (NULL) from
processed-but-no-tickers-found. After backfill, unprocessed articles
have tickers=NULL, processed-with-tickers have tickers='["NVDA",...]',
processed-without-tickers have tickers='[]'.
"""
import json
import logging
import sys

from db.database import get_session, init_db
from db.models import Article
from tagging.tickers import extract_tickers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def backfill_tickers(batch_size: int = 500) -> int:
    """Backfill tickers for articles where tickers IS NULL."""
    init_db()
    session = get_session()
    total = 0

    try:
        while True:
            articles = (
                session.query(Article)
                .filter(Article.tickers.is_(None))
                .limit(batch_size)
                .all()
            )
            if not articles:
                break

            for article in articles:
                tickers = extract_tickers(article.title, article.content)
                # Use '[]' as "processed, no tickers" marker to avoid re-processing
                article.tickers = json.dumps(tickers) if tickers else "[]"

            session.commit()
            total += len(articles)
            logger.info("Backfilled %d articles (total: %d)", len(articles), total)

    finally:
        session.close()

    logger.info("Backfill complete: %d articles processed", total)
    return total


if __name__ == "__main__":
    batch = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    backfill_tickers(batch)
```

- [ ] **Step 2: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add scripts/backfill_tickers.py
git commit -m "feat: add ticker backfill script for existing articles"
```

---

## Task 11: Quant Bridge Module

**Files:**
- Create: `bridge/__init__.py`
- Create: `bridge/quant.py`
- Create: `tests/test_quant_bridge.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Write failing test for bridge**

```python
# tests/test_quant_bridge.py
"""Tests for quant bridge price snapshot fetcher."""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest


def test_get_price_snapshot_success():
    from bridge.quant import get_price_snapshot

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "price_at_event": 142.5,
        "change_1d": 3.2,
        "change_3d": 5.1,
        "change_5d": 4.8,
    }

    with patch("bridge.quant.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = asyncio.run(get_price_snapshot("NVDA", datetime(2026, 3, 18)))
        assert result is not None
        assert result["price_at_event"] == 142.5
        assert result["change_1d"] == 3.2


def test_get_price_snapshot_timeout():
    from bridge.quant import get_price_snapshot
    import httpx

    with patch("bridge.quant.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client_cls.return_value = mock_client

        result = asyncio.run(get_price_snapshot("NVDA", datetime(2026, 3, 18)))
        assert result is None


def test_get_price_snapshot_404():
    from bridge.quant import get_price_snapshot

    mock_response = AsyncMock()
    mock_response.status_code = 404

    with patch("bridge.quant.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = asyncio.run(get_price_snapshot("FAKE", datetime(2026, 3, 18)))
        assert result is None


def test_get_price_impacts_parallel():
    from bridge.quant import get_price_impacts

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "price_at_event": 100.0,
        "change_1d": 1.0,
        "change_3d": 2.0,
        "change_5d": 3.0,
    }

    with patch("bridge.quant.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = asyncio.run(
            get_price_impacts(["NVDA", "AAPL"], datetime(2026, 3, 18))
        )
        assert len(result) == 2
        assert result[0]["ticker"] == "NVDA"
        assert result[1]["ticker"] == "AAPL"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/wendy/work/trading-co/park-intel && python -m pytest tests/test_quant_bridge.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Add httpx to requirements.txt**

```
httpx>=0.27
```

- [ ] **Step 4: Install httpx**

Run: `cd /Users/wendy/work/trading-co/park-intel && pip install httpx>=0.27`

- [ ] **Step 5: Implement bridge module**

```python
# bridge/__init__.py
```

```python
# bridge/quant.py
"""Async bridge to quant-data-pipeline for price impact data."""
import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx

from config import QUANT_API_BASE_URL

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 3.0


async def get_price_snapshot(
    ticker: str,
    event_date: datetime,
) -> dict[str, Any] | None:
    """Fetch price snapshot from quant-data-pipeline.

    Returns dict with price_at_event, change_1d, change_3d, change_5d.
    Returns None on any failure.
    """
    url = f"{QUANT_API_BASE_URL}/api/price/{ticker}"
    params = {"date": event_date.strftime("%Y-%m-%d")}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.warning(
                    "Quant API returned %d for %s on %s",
                    resp.status_code, ticker, event_date.date(),
                )
                return None
            return resp.json()
    except httpx.TimeoutException:
        logger.warning("Quant API timeout for %s", ticker)
        return None
    except Exception:
        logger.warning("Quant API error for %s", ticker, exc_info=True)
        return None


async def get_price_impacts(
    tickers: list[str],
    event_date: datetime,
) -> list[dict[str, Any]]:
    """Fetch price impacts for multiple tickers in parallel.

    Returns list of {ticker, price_at_event, change_1d, change_3d, change_5d}.
    Skips tickers that fail.
    """
    tasks = [get_price_snapshot(t, event_date) for t in tickers]
    results = await asyncio.gather(*tasks)

    impacts = []
    for ticker, result in zip(tickers, results):
        if result is not None:
            impacts.append({"ticker": ticker, **result})

    return impacts
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/wendy/work/trading-co/park-intel && python -m pytest tests/test_quant_bridge.py -v`
Expected: 4 tests PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add bridge/__init__.py bridge/quant.py tests/test_quant_bridge.py requirements.txt
git commit -m "feat: add quant bridge module for async price impact fetching"
```

---

## Task 12: Integrate Price Impacts into Event API

**Files:**
- Modify: `api/event_routes.py`

- [ ] **Step 1: Add price_impacts to event detail endpoint**

In `api/event_routes.py`, modify `get_event_detail()` to be async and add price impacts.

Change function signature:
```python
@event_router.get("/events/{event_id}")
async def get_event_detail(event_id: int) -> dict[str, Any]:
```

After building the `articles` list, add:

```python
        # Aggregate tickers from all articles
        all_tickers: list[str] = []
        seen_tickers: set[str] = set()
        for a in linked:
            if a.tickers:
                try:
                    article_tickers = json.loads(a.tickers)
                    for t in article_tickers:
                        if t not in seen_tickers:
                            seen_tickers.add(t)
                            all_tickers.append(t)
                except (json.JSONDecodeError, TypeError):
                    pass

        # Fetch price impacts (parallel, async)
        price_impacts: list[dict[str, Any]] = []
        if all_tickers and event.window_start:
            from bridge.quant import get_price_impacts
            price_impacts = await get_price_impacts(all_tickers, event.window_start)
```

Add `price_impacts` to the return dict:
```python
        return {
            "event": { ... },
            "articles": articles,
            "price_impacts": price_impacts,
        }
```

- [ ] **Step 2: Run all tests**

Run: `cd /Users/wendy/work/trading-co/park-intel && python -m pytest tests/ -v --timeout=30`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add api/event_routes.py
git commit -m "feat: add price_impacts to event detail endpoint with async parallel fetch"
```

---

## Task 13: Final Integration Test + CLAUDE.md Update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/wendy/work/trading-co/park-intel && python -m pytest tests/ -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 2: Verify server starts**

Run: `cd /Users/wendy/work/trading-co/park-intel && timeout 5 python -c "from main import app; print('App loaded OK')"`
Expected: "App loaded OK"

- [ ] **Step 3: Update CLAUDE.md**

Add to the Architecture section:
```
### Event Aggregation (V1)
- `events/models.py` — Event + EventArticle models
- `events/aggregator.py` — Clusters articles by narrative_tag in 48h windows, runs hourly
- `api/event_routes.py` — /api/events/active, /api/events/{id}
- Signal score = source_count × avg_relevance

### User Personalization
- `users/models.py` — UserProfile with topic_weights (JSON)
- `users/service.py` — CRUD + weight validation (0.0-3.0, 13 valid topics)
- `api/user_routes.py` — /api/users CRUD
- Feed personalization via ?user= param on /api/ui/feed

### Quant Bridge
- `tagging/tickers.py` — Ticker extraction (cashtag + alias + source)
- `bridge/quant.py` — Async price snapshot from quant-data-pipeline (port 8000)
- Event detail includes price_impacts when tickers available
```

Add to API Endpoints section:
```
- `GET /api/events/active` — active events by signal score
- `GET /api/events/{id}` — event detail with articles and price impacts
- `POST /api/users` — create user profile
- `GET /api/users` — list users
- `GET /api/users/{username}` — get user profile
- `PUT /api/users/{username}/weights` — update topic weights
```

Add to Commands section:
```bash
# Backfill tickers for existing articles
python scripts/backfill_tickers.py
```

- [ ] **Step 4: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with event aggregation, user profiles, and quant bridge"
```

- [ ] **Step 5: Run backfill script**

Run: `cd /Users/wendy/work/trading-co/park-intel && python scripts/backfill_tickers.py`
Expected: Processes ~37K articles, extracts tickers where found
