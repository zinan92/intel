# Today's Play + Signal Scorecard — Design Spec

**Date**: 2026-03-20
**Status**: Approved
**Scope**: Two features that bridge "what happened" to "what to do" — LLM scenario analysis per event, and historical signal accuracy evidence

---

## Overview

1. **Today's Play** — LLM-generated scenario analysis (bull/bear case) for each cross-source event, answering "what should I consider doing?"
2. **Signal Scorecard** — Price outcome snapshots captured when events close, with historical accuracy statistics shown in-context on EventPage

---

## Feature 1: Today's Play (Scenario Analysis)

### Data Model

Event table gains one new field:
- `trading_play` (TEXT, nullable) — LLM-generated scenario analysis

Migration in `db/migrations.py`:
```python
("events", "trading_play", "TEXT"),
```

### Generation Logic

Extend `events/narrator.py` to generate both `narrative_summary` and `trading_play` in a single claude CLI call.

Updated prompt:
```
Summarize this cross-source event in 2-3 sentences for a trader.
Then provide a scenario analysis with two outcomes:

SCENARIO A (bull case): If [condition], then [expected outcome + suggested action with specific ticker and timeframe].
SCENARIO B (bear case): If [condition], then [expected outcome + suggested action with specific ticker and timeframe].

Format your response as:

SUMMARY: [2-3 sentence summary]

SCENARIO A: [bull case]

SCENARIO B: [bear case]
```

Parse the response:
- Everything before "SCENARIO A:" → `narrative_summary`
- "SCENARIO A:" through end → `trading_play` (store both scenarios as one text block)

If parsing fails (no "SCENARIO A:" marker), store entire response as `narrative_summary`, leave `trading_play` NULL.

### Generation Conditions

Same as narrative: `source_count >= 2` AND `trading_play IS NULL`. Runs in `generate_narratives()` — one CLI call produces both fields.

### Frontend Display

**EventPage** (`EventPage.tsx`), below Price Impact bar and narrative summary:

```
Trading Consideration
┌─────────────────────────────────────────────┐
│ SCENARIO A (Bull)                           │
│ If [condition], then [outcome + action]     │
│                                             │
│ SCENARIO B (Bear)                           │
│ If [condition], then [outcome + action]     │
│                                             │
│ ⚠ AI-generated analysis. Not financial     │
│   advice.                                   │
└─────────────────────────────────────────────┘
```

Style: `bg-slate-800/50 border border-surface-border rounded-lg`
- "SCENARIO A" label in green, "SCENARIO B" in red
- Scenario text in `text-slate-300`
- Disclaimer in `text-slate-500 text-xs`

Hidden when `trading_play` is NULL.

**MorningBrief**: Not shown (too long for brief cards).

### API Changes

- `GET /api/events/{id}` — add `trading_play` to event dict
- `_build_top_events()` — do NOT include (not needed in feed)

### Error Handling

- CLI fails → both fields stay NULL
- Parsing fails → narrative_summary gets full text, trading_play stays NULL
- All failures non-fatal

---

## Feature 2: Signal Scorecard

### Data Model

Event table gains one new field:
- `outcome_data` (TEXT, nullable) — JSON with price outcomes captured at event close

JSON schema:
```json
{
  "tickers": {
    "NVDA": {"price_at_event": 142.5, "change_1d": 3.2, "change_3d": 5.1, "change_5d": 4.8}
  },
  "captured_at": "2026-03-20T08:00:00"
}
```

Migration:
```python
("events", "outcome_data", "TEXT"),
```

### Snapshot Logic

In `events/aggregator.py`, when closing expired events (status active → closed):

1. For each event being closed, collect all unique tickers from linked articles
2. If tickers exist, call `bridge.quant.get_price_impacts(tickers, event.window_start)`
3. Serialize result as JSON into `outcome_data`
4. If quant API fails or no tickers → `outcome_data` stays NULL

This runs inside the existing `run_aggregation()` close loop. Use `asyncio.run()` to call the async `get_price_impacts()` from the sync aggregator context.

### Scorecard API

New endpoint: `GET /api/events/scorecard`

Query params:
- `days` (int, default 30) — lookback window
- `min_events` (int, default 3) — minimum events per bucket for statistical relevance

Response:
```json
{
  "buckets": [
    {
      "label": "Signal ≥ 8.0",
      "min_score": 8.0,
      "event_count": 5,
      "avg_change_1d": 1.8,
      "avg_change_3d": 2.4,
      "avg_change_5d": 3.1
    },
    {
      "label": "Signal 6.0-7.9",
      "min_score": 6.0,
      "event_count": 8,
      "avg_change_1d": 0.9,
      "avg_change_3d": 1.2,
      "avg_change_5d": 1.5
    }
  ],
  "total_events_with_data": 20,
  "period_days": 30
}
```

Logic:
1. Query closed events with `outcome_data IS NOT NULL` from last N days
2. Parse each event's `outcome_data` JSON
3. Average all ticker changes per event (one number per event)
4. Bucket by signal_score ranges: ≥8, 6-7.9, 4-5.9, <4
5. Calculate average 1D/3D/5D change per bucket
6. Only include buckets with ≥ `min_events` events

### Frontend Display

**EventPage** (`EventPage.tsx`), below Trading Consideration:

```
Historical Context
┌─────────────────────────────────────────────┐
│ Events with signal ≥ 8.0 (5 events, 30d)   │
│                                             │
│ Avg 1D: +1.8%   Avg 3D: +2.4%   Avg 5D: +3.1% │
│                                             │
│ This event: Signal 8.0                      │
└─────────────────────────────────────────────┘
```

- Fetch scorecard data once via `useQuery` on EventPage mount
- Find the bucket matching current event's signal_score
- Display that bucket's stats
- Green/red coloring for positive/negative averages
- Hidden when no scorecard data available (not enough closed events with outcomes)

Style: `bg-slate-800/30 border border-surface-border rounded-lg`, monospace numbers

### Backfill Script

`scripts/backfill_outcomes.py` — one-time script to populate `outcome_data` for existing closed events that have tickers. Calls quant bridge for each.

---

## New Files

| File | Purpose |
|------|---------|
| `scripts/backfill_outcomes.py` | One-time backfill outcome_data for closed events |
| `tests/test_trading_play.py` | Tests for trading_play generation + parsing |
| `tests/test_scorecard.py` | Tests for scorecard endpoint |

## Modified Files

| File | Changes |
|------|---------|
| `events/models.py` | Add `trading_play`, `outcome_data` fields |
| `db/migrations.py` | Add column migrations |
| `events/narrator.py` | Update prompt + parse trading_play from response |
| `events/aggregator.py` | Snapshot outcome_data on event close |
| `api/event_routes.py` | Add `trading_play` to event detail; add scorecard endpoint |
| `frontend/src/types/api.ts` | Add `trading_play` to EventInfo; add ScorecardResponse types |
| `frontend/src/api/client.ts` | Add `scorecard()` method |
| `frontend/src/pages/EventPage.tsx` | Add Trading Consideration + Historical Context sections |

---

## Out of Scope

- Trading play in MorningBrief cards (too long)
- Scorecard as independent dashboard page (later)
- Per-topic accuracy breakdown (later)
- Automated trading execution based on plays
- Position sizing recommendations
