# Event Narrative, Signal Velocity & Event Retrospective — Design Spec

**Date**: 2026-03-19
**Status**: Approved
**Scope**: Three features that make events actionable — LLM narrative summaries, signal trend indicators, and historical event archive

---

## Overview

Three features extending the Event system:

1. **Event Narrative** — LLM-generated 2-3 sentence summaries for cross-source events, answering "what happened and why it matters"
2. **Signal Velocity** — Trend arrows (↑/↓/→/NEW) showing whether an event's signal is strengthening or weakening
3. **Event Retrospective** — Searchable archive of closed events from the last 30 days

---

## Feature 1: Event Narrative

### Data Model

Event table gains two new fields (migration in `db/migrations.py`):
- `narrative_summary` (TEXT, nullable) — LLM-generated 2-3 sentence event summary
- `prev_signal_score` (REAL, nullable) — previous signal_score for velocity calculation

### Generation Logic

In `events/aggregator.py`, after the existing aggregation loop completes:

1. Query events where `source_count >= 2` AND `narrative_summary IS NULL`
2. For each, fetch top 3 linked articles by `relevance_score` DESC
3. Call `claude` CLI with prompt:
   ```
   Summarize this cross-source event in 2-3 sentences for a trader.
   What happened, why it matters, and potential market impact. Be concise.

   Event: {narrative_tag}
   Sources: {source_count} sources, {article_count} articles

   Article 1: {title}
   {content[:200]}

   Article 2: {title}
   {content[:200]}

   Article 3: {title}
   {content[:200]}
   ```
4. Store result in `narrative_summary`
5. Already-summarized events are skipped (idempotent)

### CLI Invocation

Use `subprocess.run()` with `claude` CLI, same pattern as `tagging/llm.py`:
```python
result = subprocess.run(
    ["claude", "-p", prompt, "--output-format", "text"],
    capture_output=True, text=True, timeout=30,
)
```

Rate limit: 2-second pause between calls (matching existing LLM tagger pattern).

### New Module

`events/narrator.py` — Encapsulates narrative generation logic. Called from `run_aggregation()` at the end.

### Error Handling

- CLI not found → log warning, skip all narratives
- CLI timeout (30s) → log warning, skip that event
- CLI returns error → log warning, skip that event
- All failures are non-fatal; aggregation completes normally

### Frontend Display

**Brief Hero Card** (`MorningBrief.tsx`):
- `narrative_summary` displayed below event name, white/slate-300 text, `text-xs`, max 2 lines (`line-clamp-2`)
- Hidden when NULL

**Brief Grid Cards** (`EventCard.tsx`):
- No narrative (too compact)

**EventPage** (`EventPage.tsx`):
- `narrative_summary` displayed below source badges, before Price Impact bar
- `text-sm text-gray-600`, full text (no clamping)
- Hidden when NULL

### API Changes

- `_build_top_events()` in `ui_routes.py` — add `narrative_summary` to returned dict
- `GET /api/events/{id}` in `event_routes.py` — add `narrative_summary` to event dict

---

## Feature 2: Signal Velocity

### Data Flow

In `run_aggregation()`, before recalculating event stats:
```python
# Save current score before recalculation
active_event.prev_signal_score = active_event.signal_score
# ... recalculate source_count, article_count, signal_score ...
```

For newly created events, `prev_signal_score` remains NULL.

### API Changes

Both `_build_top_events()` and `GET /api/events/{id}` return `prev_signal_score` (nullable float).

Frontend computes velocity client-side:
- `prev_signal_score` is NULL → display "NEW" (blue)
- `signal_score > prev_signal_score` → display "↑" (green)
- `signal_score < prev_signal_score` → display "↓" (red)
- `signal_score == prev_signal_score` → display "→" (gray)

### Frontend Display

**Brief Hero Card** — After signal score: `"SIGNAL 12.0 ↑"` with colored arrow
**Brief Grid Cards** — After signal score label: colored arrow
**EventPage Header** — Below signal badge: `"Signal 12.0 (↑ from 8.0)"` in small text

### Frontend Types

Update `TopEvent` and `EventInfo`:
```typescript
prev_signal_score: number | null;
```

Add helper function in a shared util or inline:
```typescript
function velocityLabel(current: number, prev: number | null): { arrow: string; color: string; label: string }
```

---

## Feature 3: Event Retrospective

### New API Endpoint

`GET /api/events/history`

Query params:
- `days` (int, default 30) — how far back to look
- `tag` (str, optional) — filter by narrative_tag substring (case-insensitive)
- `limit` (int, default 50, max 200)

Response:
```json
{
  "events": [
    {
      "id": 1,
      "narrative_tag": "btc-etf-inflows",
      "signal_score": 12.0,
      "source_count": 4,
      "article_count": 5,
      "narrative_summary": "...",
      "window_start": "2026-03-15T04:00:00",
      "window_end": "2026-03-17T04:00:00",
      "status": "closed",
      "tickers": ["BTC", "COIN"]
    }
  ]
}
```

Sorted by `window_start` DESC. Tickers aggregated via batched query (same pattern as `_build_top_events`).

Price impacts are NOT included in the list view — loaded on demand when user clicks through to `/events/{id}` (existing EventPage handles both active and closed events).

### Frontend Page

`/events/history` — new route

Structure:
1. **Header** — "Event History · Last 30 Days"
2. **Filter** — Text input for tag search (client-side filter on loaded data, debounced)
3. **Event List** — Each row:
   - Date (formatted window_start)
   - Event name (narrative_tag formatted)
   - Signal score (with velocity arrow if prev_signal_score available)
   - Source count + article count
   - Ticker symbols (gray pills)
   - Narrative summary (1 line, truncated)
   - Clickable → `/events/{id}`

### Sidebar Navigation

Add "History" link in Sidebar, after existing navigation items.

### New Files

| File | Purpose |
|------|---------|
| `events/narrator.py` | LLM narrative generation via claude CLI |
| `frontend/src/pages/EventHistoryPage.tsx` | Event history archive page |

### Modified Files

| File | Changes |
|------|---------|
| `events/models.py` | Add `narrative_summary`, `prev_signal_score` fields |
| `db/migrations.py` | Add column migrations for both fields |
| `events/aggregator.py` | Save prev_signal_score before recalc; call narrator after aggregation |
| `api/event_routes.py` | Add `narrative_summary` + `prev_signal_score` to event detail; add `/api/events/history` endpoint |
| `api/ui_routes.py` | Add `narrative_summary` + `prev_signal_score` to `_build_top_events()` |
| `frontend/src/types/api.ts` | Update TopEvent + EventInfo with new fields; add EventHistoryItem |
| `frontend/src/api/client.ts` | Add `eventHistory()` method |
| `frontend/src/components/MorningBrief.tsx` | Show narrative_summary in hero card |
| `frontend/src/components/EventCard.tsx` | Show velocity arrow |
| `frontend/src/pages/EventPage.tsx` | Show narrative_summary + velocity detail |
| `frontend/src/App.tsx` | Add `/events/history` route |
| `frontend/src/components/Sidebar.tsx` | Add History link |

---

## Out of Scope

- Updating narrative_summary when event gains new articles (once generated, it's final for that event)
- Price impact caching for closed events
- Event comparison view (side-by-side events)
- LLM-generated trade recommendations
- Narrative generation for single-source events
