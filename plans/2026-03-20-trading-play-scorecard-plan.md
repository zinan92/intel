# Today's Play + Signal Scorecard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add LLM scenario analysis (bull/bear case) to events and historical signal accuracy evidence on EventPage.

**Architecture:** Extend narrator prompt to produce `trading_play` alongside `narrative_summary`. Snapshot price outcomes on event close via quant bridge. New scorecard API aggregates historical accuracy. Frontend shows both on EventPage.

**Tech Stack:** Python, FastAPI, SQLAlchemy, claude CLI, React, TypeScript, httpx

**Spec:** `plans/2026-03-20-trading-play-scorecard-design.md`

---

## File Map

### New Files
| File | Purpose |
|------|---------|
| `scripts/backfill_outcomes.py` | Backfill outcome_data for existing closed events |
| `tests/test_trading_play.py` | Tests for trading_play parsing |
| `tests/test_scorecard.py` | Tests for scorecard endpoint |

### Modified Files
| File | Changes |
|------|---------|
| `events/models.py` | Add `trading_play`, `outcome_data` fields |
| `db/migrations.py` | Add column migrations |
| `events/narrator.py` | Update prompt, parse trading_play from response |
| `events/aggregator.py` | Snapshot outcome_data on event close |
| `api/event_routes.py` | Add `trading_play` to event detail; add scorecard endpoint |
| `frontend/src/types/api.ts` | Add `trading_play` to EventInfo; add Scorecard types |
| `frontend/src/api/client.ts` | Add `scorecard()` method |
| `frontend/src/pages/EventPage.tsx` | Add Trading Consideration + Historical Context |

---

## Task 1: DB Migration — Add trading_play + outcome_data fields

**Files:**
- Modify: `events/models.py`
- Modify: `db/migrations.py`

- [ ] **Step 1: Add fields to Event model**

In `events/models.py`, add after `prev_signal_score`:
```python
    trading_play: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome_data: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 2: Add migrations**

In `db/migrations.py`, add to the `migrations` list:
```python
        ("events", "trading_play", "TEXT"),
        ("events", "outcome_data", "TEXT"),
```

- [ ] **Step 3: Verify and commit**

Run: `PYTHONPATH=. .venv/bin/python -c "from main import app; print('OK')"`
Commit: `feat: add trading_play and outcome_data to Event model`

---

## Task 2: Update Narrator — Scenario Analysis Prompt + Parsing

**Files:**
- Modify: `events/narrator.py`
- Create: `tests/test_trading_play.py`

- [ ] **Step 1: Write test for parsing**

```python
# tests/test_trading_play.py
"""Tests for trading play parsing."""
import pytest


def test_parse_response_with_scenarios():
    from events.narrator import _parse_narrator_response

    response = """SUMMARY: Bitcoin ETFs saw record inflows, signaling institutional adoption.

SCENARIO A: If inflows continue above $500M daily, BTC could test $75K resistance within 1-2 weeks. Consider long BTC or COIN.

SCENARIO B: If inflows reverse below $100M, this was a one-day anomaly. Consider reducing crypto exposure or hedging with puts."""

    summary, play = _parse_narrator_response(response)
    assert "Bitcoin ETFs" in summary
    assert "SCENARIO A" in play
    assert "SCENARIO B" in play


def test_parse_response_without_scenarios():
    from events.narrator import _parse_narrator_response

    response = "Bitcoin ETFs saw record inflows. This is bullish for the sector."
    summary, play = _parse_narrator_response(response)
    assert summary == response
    assert play is None


def test_parse_response_empty():
    from events.narrator import _parse_narrator_response

    summary, play = _parse_narrator_response("")
    assert summary == ""
    assert play is None
```

- [ ] **Step 2: Implement parsing and update prompt**

In `events/narrator.py`, add parsing function:

```python
def _parse_narrator_response(response: str) -> tuple[str, str | None]:
    """Parse narrator response into (summary, trading_play).

    Expected format:
    SUMMARY: ...
    SCENARIO A: ...
    SCENARIO B: ...

    If no SCENARIO markers found, entire response is summary, play is None.
    """
    marker = "SCENARIO A:"
    idx = response.find(marker)
    if idx == -1:
        return response.strip(), None

    summary_part = response[:idx].strip()
    play_part = response[idx:].strip()

    # Remove "SUMMARY:" prefix if present
    if summary_part.upper().startswith("SUMMARY:"):
        summary_part = summary_part[8:].strip()

    return summary_part, play_part
```

Update `_build_prompt()` to the new prompt:

```python
def _build_prompt(event: Event, articles: list[Article]) -> str:
    tag_display = event.narrative_tag.replace("-", " ")
    articles_text = ""
    for i, a in enumerate(articles[:3], 1):
        title = a.title or "Untitled"
        content = (a.content or "")[:200]
        articles_text += f"\nArticle {i}: {title}\n{content}\n"
    return (
        f"You are a trading analyst. Analyze this cross-source market event.\n\n"
        f"Event: {tag_display}\n"
        f"Sources: {event.source_count} sources, {event.article_count} articles\n"
        f"{articles_text}\n"
        f"Respond in this exact format:\n\n"
        f"SUMMARY: [2-3 sentence summary of what happened and why it matters]\n\n"
        f"SCENARIO A: If [specific bull condition], then [expected outcome]. "
        f"Consider [specific action with ticker and timeframe].\n\n"
        f"SCENARIO B: If [specific bear condition], then [expected outcome]. "
        f"Consider [specific action with ticker and timeframe]."
    )
```

Update `generate_narratives()` to use parsing and fill both fields:

In the loop, replace the block after `narrative = _call_claude(prompt)` with:

```python
        if narrative:
            summary, play = _parse_narrator_response(narrative)
            event.narrative_summary = summary
            event.trading_play = play
            generated += 1
            logger.info("[narrator] Generated narrative for '%s'", event.narrative_tag)
```

Also update the query filter — need to generate for events missing EITHER field:
```python
    events = (
        session.query(Event)
        .filter(
            Event.status == "active",
            Event.source_count >= 2,
            Event.trading_play.is_(None),
        )
        .order_by(Event.signal_score.desc())
        .limit(10)
        .all()
    )
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/test_trading_play.py -v`

- [ ] **Step 4: Commit**

`feat: update narrator with scenario analysis prompt and parsing`

---

## Task 3: Snapshot Outcomes on Event Close

**Files:**
- Modify: `events/aggregator.py`

- [ ] **Step 1: Add outcome snapshot to close loop**

In `events/aggregator.py`, replace the close loop:

```python
    # 4. Close expired events + snapshot outcomes
    expired = (
        session.query(Event)
        .filter(Event.status == "active", Event.window_end < now)
        .all()
    )
    for event in expired:
        event.status = "closed"
        event.updated_at = now

        # Snapshot price outcomes if event has tickers
        if event.outcome_data is None:
            try:
                linked_ids = [
                    ea.article_id
                    for ea in session.query(EventArticle)
                    .filter(EventArticle.event_id == event.id)
                    .all()
                ]
                tickers = set()
                for art in session.query(Article).filter(Article.id.in_(linked_ids)).all():
                    if art.tickers:
                        try:
                            for t in json.loads(art.tickers):
                                if t:
                                    tickers.add(t)
                        except (json.JSONDecodeError, TypeError):
                            pass

                if tickers:
                    import asyncio
                    from bridge.quant import get_price_impacts
                    impacts = asyncio.run(get_price_impacts(list(tickers)[:5], event.window_start))
                    if impacts:
                        outcome = {
                            "tickers": {
                                pi["ticker"]: {
                                    "price_at_event": pi.get("price_at_event"),
                                    "change_1d": pi.get("change_1d"),
                                    "change_3d": pi.get("change_3d"),
                                    "change_5d": pi.get("change_5d"),
                                }
                                for pi in impacts
                            },
                            "captured_at": now.isoformat(),
                        }
                        event.outcome_data = json.dumps(outcome)
                        logger.info("[aggregator] Captured outcome for '%s': %d tickers", event.narrative_tag, len(impacts))
            except Exception:
                logger.warning("[aggregator] Failed to capture outcome for '%s'", event.narrative_tag, exc_info=True)
```

Make sure `json` is imported at top of file (it already is from the existing code).

- [ ] **Step 2: Run aggregation tests**

Run: `.venv/bin/python -m pytest tests/test_event_aggregation.py -v`

- [ ] **Step 3: Commit**

`feat: snapshot price outcomes on event close`

---

## Task 4: Backend API — trading_play + scorecard endpoint

**Files:**
- Modify: `api/event_routes.py`

- [ ] **Step 1: Add trading_play to event detail**

In `get_event_detail()`, add to the event dict:
```python
                "trading_play": evt.trading_play,
```

- [ ] **Step 2: Add scorecard endpoint**

Add BEFORE `/events/{event_id}` route (to avoid path collision):

```python
@event_router.get("/events/scorecard")
def get_scorecard(
    days: int = Query(default=30, ge=1, le=365),
    min_events: int = Query(default=2, ge=1, le=50),
) -> dict[str, Any]:
    """Aggregate historical signal accuracy by score buckets."""
    session = get_session()
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        events = (
            session.query(Event)
            .filter(
                Event.status == "closed",
                Event.outcome_data.isnot(None),
                Event.window_start >= cutoff,
            )
            .all()
        )

        # Parse outcomes and compute per-event average change
        buckets_config = [
            {"label": "Signal ≥ 8.0", "min": 8.0, "max": 999},
            {"label": "Signal 6.0–7.9", "min": 6.0, "max": 8.0},
            {"label": "Signal 4.0–5.9", "min": 4.0, "max": 6.0},
            {"label": "Signal < 4.0", "min": 0, "max": 4.0},
        ]

        bucket_data: dict[str, list[dict]] = {b["label"]: [] for b in buckets_config}

        for event in events:
            try:
                outcome = json.loads(event.outcome_data)
                tickers = outcome.get("tickers", {})
                if not tickers:
                    continue

                # Average across all tickers for this event
                changes_1d = [v.get("change_1d", 0) for v in tickers.values() if v.get("change_1d") is not None]
                changes_3d = [v.get("change_3d", 0) for v in tickers.values() if v.get("change_3d") is not None]
                changes_5d = [v.get("change_5d", 0) for v in tickers.values() if v.get("change_5d") is not None]

                if not changes_1d:
                    continue

                avg = {
                    "change_1d": sum(changes_1d) / len(changes_1d),
                    "change_3d": sum(changes_3d) / len(changes_3d) if changes_3d else None,
                    "change_5d": sum(changes_5d) / len(changes_5d) if changes_5d else None,
                }

                for b in buckets_config:
                    if b["min"] <= event.signal_score < b["max"]:
                        bucket_data[b["label"]].append(avg)
                        break
            except (json.JSONDecodeError, TypeError):
                continue

        result_buckets = []
        total = 0
        for b in buckets_config:
            items = bucket_data[b["label"]]
            if len(items) < min_events:
                continue
            total += len(items)
            result_buckets.append({
                "label": b["label"],
                "min_score": b["min"],
                "event_count": len(items),
                "avg_change_1d": round(sum(i["change_1d"] for i in items) / len(items), 2),
                "avg_change_3d": round(sum(i["change_3d"] for i in items if i["change_3d"] is not None) / max(1, sum(1 for i in items if i["change_3d"] is not None)), 2),
                "avg_change_5d": round(sum(i["change_5d"] for i in items if i["change_5d"] is not None) / max(1, sum(1 for i in items if i["change_5d"] is not None)), 2),
            })

        return {
            "buckets": result_buckets,
            "total_events_with_data": total,
            "period_days": days,
        }
    finally:
        session.close()
```

- [ ] **Step 3: Write test**

```python
# tests/test_scorecard.py
"""Tests for scorecard endpoint."""
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from db.models import Base
from events.models import Event


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
    for i in range(4):
        outcome = json.dumps({
            "tickers": {"NVDA": {"price_at_event": 140, "change_1d": 1.5 + i, "change_3d": 2.0 + i, "change_5d": 3.0 + i}},
            "captured_at": now.isoformat(),
        })
        session.add(Event(
            narrative_tag=f"test-event-{i}",
            window_start=now - timedelta(days=i + 1),
            window_end=now - timedelta(days=i + 1) + timedelta(hours=48),
            source_count=2, article_count=3,
            signal_score=8.0 + i * 0.5,
            status="closed",
            outcome_data=outcome,
        ))
    session.commit()
    session.close()
    with TestClient(app) as c:
        yield c


def test_scorecard_returns_buckets(client):
    resp = client.get("/api/events/scorecard?min_events=1")
    assert resp.status_code == 200
    data = resp.json()
    assert "buckets" in data
    assert data["total_events_with_data"] > 0


def test_scorecard_empty_when_min_events_high(client):
    resp = client.get("/api/events/scorecard?min_events=100")
    assert resp.status_code == 200
    assert len(resp.json()["buckets"]) == 0
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_scorecard.py tests/test_event_api.py -v`

- [ ] **Step 5: Commit**

`feat: add trading_play to event detail and scorecard endpoint`

---

## Task 5: Frontend — Types + API Client

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Update EventInfo type**

Add to `EventInfo`:
```typescript
  trading_play: string | null;
```

- [ ] **Step 2: Add Scorecard types**

```typescript
export interface ScorecardBucket {
  label: string;
  min_score: number;
  event_count: number;
  avg_change_1d: number;
  avg_change_3d: number;
  avg_change_5d: number;
}

export interface ScorecardResponse {
  buckets: ScorecardBucket[];
  total_events_with_data: number;
  period_days: number;
}
```

- [ ] **Step 3: Add API method**

```typescript
  scorecard: (params: { days?: number; min_events?: number } = {}): Promise<ScorecardResponse> =>
    get(`/api/events/scorecard${buildQuery(params as Record<string, string | number | undefined>)}`),
```

- [ ] **Step 4: Commit**

`feat: add trading_play and scorecard types to frontend`

---

## Task 6: Frontend — Trading Consideration + Historical Context on EventPage

**Files:**
- Modify: `frontend/src/pages/EventPage.tsx`

- [ ] **Step 1: Add Trading Consideration section**

After the narrative summary and before the Timeline, add:

```tsx
{data.event.trading_play && (
  <div className="bg-slate-800/50 border border-surface-border rounded-lg p-4 mb-5">
    <p className="text-[9px] text-slate-400 uppercase tracking-wider mb-3">Trading Consideration</p>
    {data.event.trading_play.split(/SCENARIO [AB]:?\s*/i).filter(Boolean).map((scenario, idx) => (
      <div key={idx} className="mb-3 last:mb-0">
        {idx === 0 && <span className="text-xs font-semibold text-green-400 mr-1">BULL</span>}
        {idx === 1 && <span className="text-xs font-semibold text-red-400 mr-1">BEAR</span>}
        <span className="text-sm text-slate-300">{scenario.trim()}</span>
      </div>
    ))}
    <p className="text-[10px] text-slate-500 mt-3 pt-2 border-t border-surface-border">
      AI-generated analysis. Not financial advice.
    </p>
  </div>
)}
```

- [ ] **Step 2: Add Historical Context section**

Import `ScorecardResponse` type. Add `useQuery` for scorecard:

```tsx
const { data: scorecard } = useQuery({
  queryKey: ["scorecard"],
  queryFn: () => api.scorecard({ days: 30, min_events: 2 }),
  staleTime: 300_000,
});
```

Find matching bucket for current event:
```tsx
const matchingBucket = scorecard?.buckets.find(b => {
  const score = data?.event.signal_score ?? 0;
  if (b.label.includes("≥ 8") && score >= 8) return true;
  if (b.label.includes("6.0") && score >= 6 && score < 8) return true;
  if (b.label.includes("4.0") && score >= 4 && score < 6) return true;
  if (b.label.includes("< 4") && score < 4) return true;
  return false;
});
```

Render after Trading Consideration:
```tsx
{matchingBucket && (
  <div className="bg-slate-800/30 border border-surface-border rounded-lg p-4 mb-5">
    <p className="text-[9px] text-slate-400 uppercase tracking-wider mb-2">Historical Context</p>
    <p className="text-xs text-slate-400 mb-2">
      {matchingBucket.label} ({matchingBucket.event_count} events, {scorecard?.period_days}d)
    </p>
    <div className="flex gap-6 font-mono text-sm">
      <div>
        <span className="text-[10px] text-slate-500">Avg 1D </span>
        <span className={matchingBucket.avg_change_1d >= 0 ? "text-green-400" : "text-red-400"}>
          {matchingBucket.avg_change_1d >= 0 ? "+" : ""}{matchingBucket.avg_change_1d.toFixed(1)}%
        </span>
      </div>
      <div>
        <span className="text-[10px] text-slate-500">Avg 3D </span>
        <span className={matchingBucket.avg_change_3d >= 0 ? "text-green-400" : "text-red-400"}>
          {matchingBucket.avg_change_3d >= 0 ? "+" : ""}{matchingBucket.avg_change_3d.toFixed(1)}%
        </span>
      </div>
      <div>
        <span className="text-[10px] text-slate-500">Avg 5D </span>
        <span className={matchingBucket.avg_change_5d >= 0 ? "text-green-400" : "text-red-400"}>
          {matchingBucket.avg_change_5d >= 0 ? "+" : ""}{matchingBucket.avg_change_5d.toFixed(1)}%
        </span>
      </div>
    </div>
  </div>
)}
```

- [ ] **Step 3: Build frontend**

Run: `cd frontend && npm run build`

- [ ] **Step 4: Commit**

`feat: add Trading Consideration and Historical Context to EventPage`

---

## Task 7: Backfill + Final Verification

- [ ] **Step 1: Create backfill script**

```python
# scripts/backfill_outcomes.py
"""Backfill outcome_data for closed events with tickers."""
import asyncio
import json
import logging
import sys

from db.database import get_session, init_db
from db.models import Article
from events.models import Event, EventArticle
from bridge.quant import get_price_impacts

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def backfill_outcomes(limit: int = 50) -> int:
    init_db()
    session = get_session()
    total = 0

    try:
        events = (
            session.query(Event)
            .filter(Event.status == "closed", Event.outcome_data.is_(None))
            .order_by(Event.signal_score.desc())
            .limit(limit)
            .all()
        )

        for event in events:
            linked_ids = [ea.article_id for ea in session.query(EventArticle).filter(EventArticle.event_id == event.id).all()]
            tickers = set()
            for art in session.query(Article).filter(Article.id.in_(linked_ids)).all():
                if art.tickers:
                    try:
                        for t in json.loads(art.tickers):
                            if t:
                                tickers.add(t)
                    except (json.JSONDecodeError, TypeError):
                        pass

            if not tickers:
                continue

            try:
                impacts = asyncio.run(get_price_impacts(list(tickers)[:5], event.window_start))
                if impacts:
                    from datetime import datetime
                    outcome = {
                        "tickers": {pi["ticker"]: {k: pi.get(k) for k in ["price_at_event", "change_1d", "change_3d", "change_5d"]} for pi in impacts},
                        "captured_at": datetime.utcnow().isoformat(),
                    }
                    event.outcome_data = json.dumps(outcome)
                    total += 1
                    logger.info("Captured outcome for '%s': %d tickers", event.narrative_tag, len(impacts))
            except Exception:
                logger.warning("Failed for '%s'", event.narrative_tag, exc_info=True)

        session.commit()
    finally:
        session.close()

    logger.info("Backfill complete: %d events updated", total)
    return total


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    backfill_outcomes(limit)
```

- [ ] **Step 2: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`

- [ ] **Step 3: Build frontend**

Run: `cd frontend && npm run build`

- [ ] **Step 4: Commit and restart**

```bash
git add scripts/backfill_outcomes.py
git commit -m "feat: add outcome backfill script"
```
