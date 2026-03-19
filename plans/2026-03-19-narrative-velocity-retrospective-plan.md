# Event Narrative, Signal Velocity & Retrospective — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make events actionable with LLM narrative summaries, signal trend arrows, and a searchable event history archive.

**Architecture:** Two new DB fields on Event (`narrative_summary`, `prev_signal_score`), a new `events/narrator.py` module for CLI-based LLM summarization, a new history API endpoint, and frontend updates across MorningBrief, EventCard, EventPage, plus a new EventHistoryPage.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, claude CLI, React 18, TypeScript, TanStack Query, Tailwind

**Spec:** `plans/2026-03-19-narrative-velocity-retrospective-design.md`

---

## File Map

### New Files
| File | Purpose |
|------|---------|
| `events/narrator.py` | LLM narrative generation via claude CLI |
| `frontend/src/pages/EventHistoryPage.tsx` | Event history archive page |
| `tests/test_narrator.py` | Tests for narrator module |
| `tests/test_event_history_api.py` | Tests for history endpoint |

### Modified Files
| File | Changes |
|------|---------|
| `events/models.py` | Add `narrative_summary`, `prev_signal_score` fields |
| `db/migrations.py` | Add column migrations |
| `events/aggregator.py` | Save prev_signal_score; call narrator |
| `api/event_routes.py` | Add fields to event detail; add history endpoint |
| `api/ui_routes.py` | Add fields to `_build_top_events()` |
| `frontend/src/types/api.ts` | Update types with new fields |
| `frontend/src/api/client.ts` | Add `eventHistory()` method |
| `frontend/src/components/MorningBrief.tsx` | Show narrative in hero |
| `frontend/src/components/EventCard.tsx` | Show velocity arrow |
| `frontend/src/pages/EventPage.tsx` | Show narrative + velocity detail |
| `frontend/src/App.tsx` | Add history route |
| `frontend/src/components/Sidebar.tsx` | Add History link |

---

## Task 1: DB Migration — Add narrative_summary + prev_signal_score

**Files:**
- Modify: `events/models.py`
- Modify: `db/migrations.py`

- [ ] **Step 1: Add fields to Event model**

In `events/models.py`, add after `status` field:

```python
    narrative_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    prev_signal_score: Mapped[float | None] = mapped_column(Float, nullable=True)
```

Add `Text` to the imports from sqlalchemy if not present.

- [ ] **Step 2: Add migrations**

In `db/migrations.py`, add to the `migrations` list inside `run_migrations()`:

```python
        ("events", "narrative_summary", "TEXT"),
        ("events", "prev_signal_score", "REAL"),
```

- [ ] **Step 3: Verify server loads**

Run: `cd /Users/wendy/work/trading-co/park-intel && PYTHONPATH=. .venv/bin/python -c "from main import app; print('OK')"`
Expected: "OK"

- [ ] **Step 4: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add events/models.py db/migrations.py
git commit -m "feat: add narrative_summary and prev_signal_score to Event model"
```

---

## Task 2: Signal Velocity — Save prev_signal_score in aggregator

**Files:**
- Modify: `events/aggregator.py`

- [ ] **Step 1: Save prev_signal_score before recalculation**

In `events/aggregator.py`, in the `run_aggregation()` function, find the block that recalculates stats (after linking articles). BEFORE the line `active_event.source_count = len(sources)`, add:

```python
        # Save current score for velocity tracking
        active_event.prev_signal_score = active_event.signal_score
```

- [ ] **Step 2: Run existing aggregation tests**

Run: `cd /Users/wendy/work/trading-co/park-intel && .venv/bin/python -m pytest tests/test_event_aggregation.py -v`
Expected: All 5 PASS

- [ ] **Step 3: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add events/aggregator.py
git commit -m "feat: save prev_signal_score in aggregator for velocity tracking"
```

---

## Task 3: Event Narrator Module

**Files:**
- Create: `events/narrator.py`
- Create: `tests/test_narrator.py`

- [ ] **Step 1: Write test**

```python
# tests/test_narrator.py
"""Tests for event narrator module."""
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, Article
from events.models import Event, EventArticle


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed_event_with_articles(session, narrative_tag="test-event", num_articles=3):
    now = datetime.utcnow()
    event = Event(
        narrative_tag=narrative_tag,
        window_start=now - timedelta(hours=2),
        window_end=now + timedelta(hours=46),
        source_count=2,
        article_count=num_articles,
        signal_score=8.0,
        status="active",
    )
    session.add(event)
    session.flush()

    for i in range(num_articles):
        article = Article(
            source=["hackernews", "reddit", "rss"][i % 3],
            source_id=f"test_{narrative_tag}_{i}",
            title=f"Article {i} about {narrative_tag}",
            content=f"Content about {narrative_tag} from source {i}. " * 20,
            relevance_score=5 - i,
            collected_at=now - timedelta(hours=i),
        )
        session.add(article)
        session.flush()
        session.add(EventArticle(event_id=event.id, article_id=article.id))

    session.commit()
    return event


def test_generate_narrative_skips_when_already_set(db_session):
    from events.narrator import generate_narratives

    event = _seed_event_with_articles(db_session)
    event.narrative_summary = "Already set"
    db_session.commit()

    with patch("events.narrator._call_claude") as mock_claude:
        generate_narratives(db_session)
        mock_claude.assert_not_called()


def test_generate_narrative_skips_single_source(db_session):
    from events.narrator import generate_narratives

    event = _seed_event_with_articles(db_session)
    event.source_count = 1
    db_session.commit()

    with patch("events.narrator._call_claude") as mock_claude:
        generate_narratives(db_session)
        mock_claude.assert_not_called()


def test_generate_narrative_calls_claude(db_session):
    from events.narrator import generate_narratives

    event = _seed_event_with_articles(db_session)

    with patch("events.narrator._call_claude") as mock_claude:
        mock_claude.return_value = "BTC ETFs saw record inflows. Multiple sources confirm institutional adoption."
        generate_narratives(db_session)

    refreshed = db_session.query(Event).filter_by(id=event.id).first()
    assert refreshed.narrative_summary == "BTC ETFs saw record inflows. Multiple sources confirm institutional adoption."
    mock_claude.assert_called_once()


def test_generate_narrative_handles_cli_failure(db_session):
    from events.narrator import generate_narratives

    event = _seed_event_with_articles(db_session)

    with patch("events.narrator._call_claude") as mock_claude:
        mock_claude.return_value = None  # CLI failure
        generate_narratives(db_session)

    refreshed = db_session.query(Event).filter_by(id=event.id).first()
    assert refreshed.narrative_summary is None  # not set on failure
```

- [ ] **Step 2: Implement narrator**

```python
# events/narrator.py
"""LLM narrative generation for cross-source events via claude CLI."""
import logging
import shutil
import subprocess
import time

from sqlalchemy.orm import Session

from db.models import Article
from events.models import Event, EventArticle

logger = logging.getLogger(__name__)

_RATE_LIMIT_SECONDS = 2


def _call_claude(prompt: str) -> str | None:
    """Call claude CLI and return response text, or None on failure."""
    claude_path = shutil.which("claude")
    if not claude_path:
        logger.warning("claude CLI not found — narrative generation disabled")
        return None

    try:
        result = subprocess.run(
            [claude_path, "-p", prompt, "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("claude CLI returned %d: %s", result.returncode, result.stderr[:200])
            return None
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.warning("claude CLI timed out for narrative generation")
        return None
    except Exception:
        logger.exception("claude CLI failed")
        return None


def _build_prompt(event: Event, articles: list[Article]) -> str:
    """Build the narrative prompt from event + top articles."""
    tag_display = event.narrative_tag.replace("-", " ")
    articles_text = ""
    for i, a in enumerate(articles[:3], 1):
        title = a.title or "Untitled"
        content = (a.content or "")[:200]
        articles_text += f"\nArticle {i}: {title}\n{content}\n"

    return (
        f"Summarize this cross-source event in 2-3 sentences for a trader. "
        f"What happened, why it matters, and potential market impact. Be concise.\n\n"
        f"Event: {tag_display}\n"
        f"Sources: {event.source_count} sources, {event.article_count} articles\n"
        f"{articles_text}"
    )


def generate_narratives(session: Session) -> int:
    """Generate narrative summaries for events that need them.

    Returns count of narratives generated.
    """
    # Find events needing narratives: source_count >= 2, no summary yet
    events = (
        session.query(Event)
        .filter(
            Event.status == "active",
            Event.source_count >= 2,
            Event.narrative_summary.is_(None),
        )
        .order_by(Event.signal_score.desc())
        .limit(10)  # cap per run to control CLI costs
        .all()
    )

    if not events:
        return 0

    generated = 0
    for event in events:
        # Get top 3 articles by relevance
        articles = (
            session.query(Article)
            .join(EventArticle, EventArticle.article_id == Article.id)
            .filter(EventArticle.event_id == event.id)
            .order_by(Article.relevance_score.desc().nullslast())
            .limit(3)
            .all()
        )

        if not articles:
            continue

        prompt = _build_prompt(event, articles)
        narrative = _call_claude(prompt)

        if narrative:
            event.narrative_summary = narrative
            generated += 1
            logger.info("[narrator] Generated narrative for '%s'", event.narrative_tag)
        else:
            logger.warning("[narrator] Failed to generate for '%s'", event.narrative_tag)

        time.sleep(_RATE_LIMIT_SECONDS)

    session.commit()
    logger.info("[narrator] Generated %d narratives (of %d candidates)", generated, len(events))
    return generated
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/wendy/work/trading-co/park-intel && .venv/bin/python -m pytest tests/test_narrator.py -v`
Expected: 4 PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add events/narrator.py tests/test_narrator.py
git commit -m "feat: add event narrator module for LLM narrative generation"
```

---

## Task 4: Integrate Narrator into Aggregator

**Files:**
- Modify: `events/aggregator.py`

- [ ] **Step 1: Call narrator at end of run_aggregation()**

At the end of `run_aggregation()`, after `session.commit()` and before the final log, add:

```python
    # Generate narratives for cross-source events
    try:
        from events.narrator import generate_narratives
        generate_narratives(session)
    except Exception:
        logger.exception("Narrative generation failed (non-fatal)")
```

- [ ] **Step 2: Run aggregation tests**

Run: `cd /Users/wendy/work/trading-co/park-intel && .venv/bin/python -m pytest tests/test_event_aggregation.py tests/test_narrator.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add events/aggregator.py
git commit -m "feat: integrate narrator into aggregation pipeline"
```

---

## Task 5: Backend API — Add narrative + velocity to responses

**Files:**
- Modify: `api/ui_routes.py`
- Modify: `api/event_routes.py`

- [ ] **Step 1: Update _build_top_events() in ui_routes.py**

In the return list comprehension, add two fields to each event dict:

```python
            "narrative_summary": e.narrative_summary,
            "prev_signal_score": e.prev_signal_score,
```

- [ ] **Step 2: Update get_event_detail() in event_routes.py**

In the event dict inside the return statement, add:

```python
                "narrative_summary": event.narrative_summary,
                "prev_signal_score": event.prev_signal_score,
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/wendy/work/trading-co/park-intel && .venv/bin/python -m pytest tests/test_event_api.py tests/test_ui_feed_api.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add api/ui_routes.py api/event_routes.py
git commit -m "feat: add narrative_summary and prev_signal_score to event API responses"
```

---

## Task 6: Backend — Event History Endpoint

**Files:**
- Modify: `api/event_routes.py`
- Create: `tests/test_event_history_api.py`

- [ ] **Step 1: Write test**

```python
# tests/test_event_history_api.py
"""Tests for event history API endpoint."""
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

    import db.database as db_mod
    db_mod._engine = None
    db_mod._SessionFactory = None

    from db.database import get_engine, get_session
    from main import app
    engine = get_engine()
    Base.metadata.create_all(engine)

    session = get_session()
    now = datetime.utcnow()

    # Create closed events
    for i in range(3):
        event = Event(
            narrative_tag=f"closed-event-{i}",
            window_start=now - timedelta(days=i + 1),
            window_end=now - timedelta(days=i + 1) + timedelta(hours=48),
            source_count=2,
            article_count=3,
            signal_score=8.0 - i,
            status="closed",
            narrative_summary=f"Summary for event {i}",
        )
        session.add(event)
    session.commit()
    session.close()

    with TestClient(app) as c:
        yield c


def test_get_event_history(client):
    resp = client.get("/api/events/history")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert len(data["events"]) == 3
    # Sorted by window_start DESC (newest first)
    assert data["events"][0]["narrative_tag"] == "closed-event-0"


def test_get_event_history_with_tag_filter(client):
    resp = client.get("/api/events/history?tag=event-1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["events"]) == 1
    assert data["events"][0]["narrative_tag"] == "closed-event-1"


def test_get_event_history_empty(client):
    resp = client.get("/api/events/history?tag=nonexistent")
    assert resp.status_code == 200
    assert len(resp.json()["events"]) == 0
```

- [ ] **Step 2: Implement history endpoint**

In `api/event_routes.py`, add:

```python
@event_router.get("/events/history")
def get_event_history(
    days: int = Query(default=30, ge=1, le=365),
    tag: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    session = get_session()
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)

        q = (
            session.query(Event)
            .filter(Event.status == "closed", Event.window_start >= cutoff)
        )
        if tag:
            q = q.filter(Event.narrative_tag.ilike(f"%{tag}%"))

        events = q.order_by(Event.window_start.desc()).limit(limit).all()

        # Batch fetch tickers for all events
        event_ids = [e.id for e in events]
        tickers_map: dict[int, list[str]] = {}
        if event_ids:
            from events.models import EventArticle
            rows = (
                session.query(EventArticle.event_id, Article.tickers)
                .join(Article, EventArticle.article_id == Article.id)
                .filter(EventArticle.event_id.in_(event_ids))
                .all()
            )
            from collections import defaultdict
            tickers_map = defaultdict(list)
            for eid, tickers_json in rows:
                if tickers_json:
                    try:
                        for t in json.loads(tickers_json):
                            if t and t not in tickers_map[eid]:
                                tickers_map[eid].append(t)
                    except (json.JSONDecodeError, TypeError):
                        pass

        result = [
            {
                "id": e.id,
                "narrative_tag": e.narrative_tag,
                "signal_score": e.signal_score,
                "source_count": e.source_count,
                "article_count": e.article_count,
                "narrative_summary": e.narrative_summary,
                "window_start": e.window_start.isoformat() if e.window_start else None,
                "window_end": e.window_end.isoformat() if e.window_end else None,
                "status": e.status,
                "tickers": tickers_map.get(e.id, [])[:5],
            }
            for e in events
        ]
        return {"events": result}
    finally:
        session.close()
```

Add `from datetime import datetime, timedelta` to imports if not present.

- [ ] **Step 3: Run tests**

Run: `cd /Users/wendy/work/trading-co/park-intel && .venv/bin/python -m pytest tests/test_event_history_api.py -v`
Expected: 3 PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add api/event_routes.py tests/test_event_history_api.py
git commit -m "feat: add event history API endpoint with tag filtering"
```

---

## Task 7: Frontend Types + API Client Updates

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Update TopEvent with new fields**

```typescript
export interface TopEvent {
  id: number;
  narrative_tag: string;
  signal_score: number;
  source_count: number;
  article_count: number;
  sources: string[];
  tickers: string[];
  narrative_summary: string | null;
  prev_signal_score: number | null;
}
```

- [ ] **Step 2: Update EventInfo with new fields**

Add to `EventInfo`:
```typescript
  narrative_summary: string | null;
  prev_signal_score: number | null;
```

- [ ] **Step 3: Add EventHistoryItem type**

```typescript
export interface EventHistoryItem {
  id: number;
  narrative_tag: string;
  signal_score: number;
  source_count: number;
  article_count: number;
  narrative_summary: string | null;
  window_start: string | null;
  window_end: string | null;
  status: string;
  tickers: string[];
}

export interface EventHistoryResponse {
  events: EventHistoryItem[];
}
```

- [ ] **Step 4: Add eventHistory to API client**

```typescript
  eventHistory: (params: { days?: number; tag?: string; limit?: number } = {}): Promise<EventHistoryResponse> =>
    get(`/api/events/history${buildQuery(params as Record<string, string | number | undefined>)}`),
```

Add `EventHistoryResponse` to the import.

- [ ] **Step 5: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add frontend/src/types/api.ts frontend/src/api/client.ts
git commit -m "feat: add narrative, velocity, and history types to frontend"
```

---

## Task 8: Frontend — Velocity Arrow + Narrative in Brief & EventPage

**Files:**
- Modify: `frontend/src/components/MorningBrief.tsx`
- Modify: `frontend/src/components/EventCard.tsx`
- Modify: `frontend/src/pages/EventPage.tsx`

- [ ] **Step 1: Add velocity helper**

Create a shared helper. Add to `EventCard.tsx` (used by both EventCard and MorningBrief):

```tsx
export function VelocityArrow({ current, prev }: { current: number; prev: number | null }) {
  if (prev === null) return <span className="text-blue-500 text-[10px] font-semibold ml-1">NEW</span>;
  if (current > prev) return <span className="text-green-500 ml-1">↑</span>;
  if (current < prev) return <span className="text-red-500 ml-1">↓</span>;
  return <span className="text-gray-400 ml-1">→</span>;
}
```

- [ ] **Step 2: Update EventCard with velocity arrow**

In the signal score line, after `{event.signal_score.toFixed(1)}`, add:
```tsx
<VelocityArrow current={event.signal_score} prev={event.prev_signal_score} />
```

- [ ] **Step 3: Update MorningBrief hero with narrative + velocity**

Import `VelocityArrow` from `./EventCard`.

In the hero card, after the source list div, add narrative:
```tsx
{hero.narrative_summary && (
  <p className="text-xs text-slate-300 mt-2 line-clamp-2">
    {hero.narrative_summary}
  </p>
)}
```

In the signal label, add velocity:
```tsx
<VelocityArrow current={hero.signal_score} prev={hero.prev_signal_score} />
```

- [ ] **Step 4: Update EventPage with narrative + velocity**

In EventPage, after source badges and before Price Impact bar, add narrative:
```tsx
{data.event.narrative_summary && (
  <p className="text-sm text-gray-600 mb-4">
    {data.event.narrative_summary}
  </p>
)}
```

Below the signal badge, add velocity detail:
```tsx
{data.event.prev_signal_score !== null && (
  <p className="text-xs text-gray-500 mt-1">
    {data.event.signal_score > data.event.prev_signal_score ? "↑" : data.event.signal_score < data.event.prev_signal_score ? "↓" : "→"}
    {" "}from {data.event.prev_signal_score.toFixed(1)}
  </p>
)}
```

- [ ] **Step 5: Build frontend**

Run: `cd /Users/wendy/work/trading-co/park-intel/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 6: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add frontend/src/components/EventCard.tsx frontend/src/components/MorningBrief.tsx frontend/src/pages/EventPage.tsx
git commit -m "feat: add velocity arrows and narrative display to Brief and EventPage"
```

---

## Task 9: Frontend — EventHistoryPage + Routing

**Files:**
- Create: `frontend/src/pages/EventHistoryPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Sidebar.tsx`

- [ ] **Step 1: Create EventHistoryPage**

```tsx
// frontend/src/pages/EventHistoryPage.tsx
import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { VelocityArrow } from "../components/EventCard";

function formatDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function EventHistoryPage() {
  const [tagFilter, setTagFilter] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["event-history"],
    queryFn: () => api.eventHistory({ days: 30, limit: 100 }),
    staleTime: 60_000,
  });

  const filtered = useMemo(() => {
    const events = data?.events ?? [];
    if (!tagFilter.trim()) return events;
    const q = tagFilter.toLowerCase();
    return events.filter((e) => e.narrative_tag.includes(q));
  }, [data, tagFilter]);

  return (
    <div className="max-w-2xl">
      <h2 className="text-lg font-semibold text-gray-800 mb-1">Event History</h2>
      <p className="text-sm text-gray-500 mb-4">Last 30 days · {filtered.length} events</p>

      <input
        type="text"
        placeholder="Filter by topic..."
        value={tagFilter}
        onChange={(e) => setTagFilter(e.target.value)}
        className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 mb-4 focus:outline-none focus:border-brand-400"
      />

      {isLoading && (
        <div className="space-y-3 animate-pulse">
          {[...Array(5)].map((_, i) => <div key={i} className="h-16 bg-gray-100 rounded-lg" />)}
        </div>
      )}

      <div className="space-y-2">
        {filtered.map((event) => (
          <Link
            key={event.id}
            to={`/events/${event.id}`}
            className="block border border-gray-200 rounded-lg p-3 hover:border-brand-400 hover:shadow-sm transition-all"
          >
            <div className="flex justify-between items-start">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-400">{formatDate(event.window_start)}</span>
                  <span className="text-sm font-semibold text-gray-800 truncate">
                    {event.narrative_tag.replace(/-/g, " ")}
                  </span>
                </div>
                {event.narrative_summary && (
                  <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{event.narrative_summary}</p>
                )}
                <div className="flex items-center gap-2 mt-1 text-xs text-gray-400">
                  <span>{event.source_count} sources · {event.article_count} articles</span>
                  {event.tickers.length > 0 && (
                    <span>{event.tickers.slice(0, 3).map(t => `$${t}`).join(" ")}</span>
                  )}
                </div>
              </div>
              <div className="text-right shrink-0 ml-3">
                <span className="text-sm font-semibold text-orange-500">{event.signal_score.toFixed(1)}</span>
              </div>
            </div>
          </Link>
        ))}
      </div>

      {!isLoading && filtered.length === 0 && (
        <p className="text-sm text-gray-400 text-center py-8">No events match the filter.</p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add route to App.tsx**

Import and add route:
```tsx
import { EventHistoryPage } from "./pages/EventHistoryPage";
// Add route:
<Route path="/events/history" element={<EventHistoryPage />} />
```

**IMPORTANT**: Place this route BEFORE `/events/:id` to avoid the `history` path being captured as an `:id` param.

- [ ] **Step 3: Add History link to Sidebar**

In `Sidebar.tsx`, add a History link in the navigation section:
```tsx
<Link
  to="/events/history"
  className={`block px-2 py-1 rounded text-sm ${
    isActive("/events/history") ? "bg-brand-50 text-brand-700 font-medium" : "text-gray-600 hover:text-gray-900"
  }`}
>
  History
</Link>
```

- [ ] **Step 4: Build frontend**

Run: `cd /Users/wendy/work/trading-co/park-intel/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add frontend/src/pages/EventHistoryPage.tsx frontend/src/App.tsx frontend/src/components/Sidebar.tsx
git commit -m "feat: add EventHistoryPage with tag filtering and sidebar navigation"
```

---

## Task 10: Final Verification

- [ ] **Step 1: Run full backend test suite**

Run: `cd /Users/wendy/work/trading-co/park-intel && .venv/bin/python -m pytest tests/ -v`
Expected: All pass (except pre-existing `test_health_no_data_status_for_fresh_source`)

- [ ] **Step 2: Build frontend**

Run: `cd /Users/wendy/work/trading-co/park-intel/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Restart API server and verify**

```bash
lsof -ti:8001 | xargs kill 2>/dev/null
sleep 1
PYTHONPATH=/Users/wendy/work/trading-co/park-intel /Users/wendy/work/trading-co/park-intel/.venv/bin/python /Users/wendy/work/trading-co/park-intel/main.py &
```

Verify:
- http://localhost:5174 — Brief shows velocity arrows on event cards
- Click event → EventPage shows narrative summary + velocity detail
- `/events/history` — shows closed events with tag filter
- Sidebar has History link
