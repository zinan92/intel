# Signal Aggregation, User Personalization & Quant Bridge

**Date**: 2026-03-18
**Status**: Approved
**Scope**: Three features for park-intel (qualitative-data-pipeline)

---

## Overview

Three sequential features that evolve park-intel from a data collection tool into a personalized trading intelligence platform:

1. **Signal Aggregation** — Cross-source event clustering with composite signal scoring
2. **User Personalization** — Per-user topic weight profiles for personalized feed ranking
3. **Quant Bridge** — Ticker extraction + price impact data from quant-data-pipeline

---

## Feature 1: Signal Aggregation Layer

### Concept

Aggregate articles sharing the same `narrative_tag` within a 48-hour window into "Events". Each event gets a composite signal score based on how many distinct sources reported it and the average relevance.

### Data Model

**New table: `events`**

| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PK | Auto-increment |
| narrative_tag | TEXT NOT NULL | Aggregation key (e.g., "nvidia-earnings-beat") |
| window_start | DATETIME NOT NULL | First article's published_at |
| window_end | DATETIME NOT NULL | window_start + 48 hours |
| source_count | INTEGER DEFAULT 0 | Distinct source types that reported this event |
| article_count | INTEGER DEFAULT 0 | Total related articles |
| signal_score | REAL DEFAULT 0.0 | source_count × avg_relevance |
| avg_relevance | REAL DEFAULT 0.0 | Mean relevance_score of related articles |
| status | TEXT DEFAULT 'active' | "active" or "closed" |
| created_at | DATETIME | |
| updated_at | DATETIME | |

Indexes: `idx_events_tag` (narrative_tag), `idx_events_status` (status), `idx_events_score` (signal_score DESC).

Unique constraint: `uq_events_tag_active` on (narrative_tag) WHERE status = 'active' — prevents duplicate active events for the same tag from concurrent aggregator runs.

**New table: `event_articles`** (many-to-many)

| Field | Type | Description |
|-------|------|-------------|
| event_id | INTEGER FK → events.id | |
| article_id | INTEGER FK → articles.id | |

Unique constraint on (event_id, article_id).

### Aggregation Logic

Scheduled task running every 1 hour:

1. Query articles from the last 48 hours that have `narrative_tags` (non-null, non-empty)
2. For each distinct tag across these articles:
   - Determine article timestamp: use `published_at` if not None, else fall back to `collected_at` (never None)
   - Find existing active Event with matching `narrative_tag` whose `window_end` > now
   - If found: update `article_count`, `source_count` (distinct sources), recalculate `avg_relevance` and `signal_score`
   - Link new articles via `event_articles` (skip duplicates via INSERT OR IGNORE)
   - If not found: create new Event with `window_start` = earliest article timestamp (with fallback), `window_end` = `window_start` + 48h
   - Link articles via `event_articles`
3. Set `status = "closed"` for all events where `window_end` < now

**Note**: `published_at` is nullable for some collectors. Always use `COALESCE(published_at, collected_at)` in queries and Python logic.

### Signal Score Formula

```
signal_score = source_count × avg_relevance
```

- `source_count`: number of distinct `article.source` values in the event
- `avg_relevance`: mean of `article.relevance_score` for articles with non-null scores

Example: 3 sources report same event, avg relevance 4.0 → signal_score = 12.0

### API Endpoints

**`GET /api/events/active`**

Query params: `limit` (default 20), `min_score` (default 0)

Response:
```json
{
  "events": [
    {
      "id": 1,
      "narrative_tag": "nvidia-earnings-beat",
      "source_count": 4,
      "article_count": 12,
      "signal_score": 16.0,
      "avg_relevance": 4.0,
      "window_start": "2026-03-18T10:00:00",
      "window_end": "2026-03-20T10:00:00",
      "status": "active",
      "sources": ["hackernews", "google_news", "rss", "reddit"]
    }
  ]
}
```

**`GET /api/events/{id}`**

Response:
```json
{
  "event": { ... },
  "articles": [ ... ]
}
```

**`GET /api/ui/feed` modification**

Add `top_events` to the existing `context` rail. Fetched via a lightweight query: `SELECT * FROM events WHERE status='active' ORDER BY signal_score DESC LIMIT 5` — no full-article scan:
```json
{
  "items": [...],
  "context": {
    "rising_topics": [...],
    "source_health": [...],
    "top_events": [
      {"narrative_tag": "...", "signal_score": 12.0, "source_count": 3}
    ]
  }
}
```

### New Files

- `events/__init__.py`
- `events/aggregator.py` — Core aggregation logic
- `events/models.py` — Event + EventArticle SQLAlchemy models
- `api/event_routes.py` — Event API endpoints (prefix `/api`, registered in `main.py`)
- `tests/test_event_aggregation.py`
- `tests/test_event_api.py`

### Modified Files

- `main.py` — Register `event_routes.router`
- `scheduler.py` — Add 1-hour aggregation job

---

## Feature 2: User Personalization

### Concept

Simple user profiles (username-based, no auth) with per-topic weight configuration. Feed ranking is multiplied by user's topic weights for personalized ordering.

### Data Model

**New table: `user_profiles`**

| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PK | Auto-increment |
| username | TEXT UNIQUE NOT NULL | e.g., "wendy", "monica" |
| display_name | TEXT NOT NULL | Display name |
| topic_weights | TEXT DEFAULT '{}' | JSON: {"ai": 2.0, "macro": 1.5} |
| created_at | DATETIME | |
| updated_at | DATETIME | |

### Weight Rules

- Default weight for unconfigured topics = 1.0
- Weight range: 0.0 to 3.0
- 0.0 = hide articles where ALL tags have weight 0.0 (filtered out, not just scored low)
- Topics correspond to keyword tagger's 13 categories: ai, crypto, macro, geopolitics, china-market, us-market, sector/tech, sector/finance, sector/energy, trading, regulation, earnings, commodities

### Personalized Feed Ranking

Current priority score formula (approximate):
```
base_score = relevance × freshness_factor × momentum_factor
```

With personalization:
```
personalized_score = base_score × max(user_weight for each matching tag)
```

- Article tags = ["ai", "macro"] → take max(weights["ai"], weights["macro"])
- No matching tags → weight = 1.0 (unchanged)
- No `user` param → original behavior (backward compatible)
- **Filter rule**: After scoring, articles with `personalized_score == 0.0` are excluded from results (not just sorted low). This implements the "0.0 = hide" semantics.

### API Endpoints

**`POST /api/users`**

Body: `{"username": "wendy", "display_name": "Wendy"}`

**`GET /api/users/{username}`**

Returns user profile including topic_weights.

**`PUT /api/users/{username}/weights`**

Body: `{"ai": 2.0, "macro": 1.5, "crypto": 0.5}`

Replaces all weights. Omitted topics reset to default 1.0.

**Validation** (enforced in `users/service.py`):
- Keys must be from the 13 known topic categories — unknown keys rejected with 422
- Values must be floats in `[0.0, 3.0]` — out-of-range rejected with 422
- **Immutability**: service creates a new `UserProfile` row state (new JSON string), never mutates existing dict in-place

**`GET /api/ui/feed?user=wendy`**

Existing endpoint, new optional query param. When provided, applies personalized ranking.

### Frontend Changes

- **Sidebar**: User selector dropdown at top (simple `<select>` with usernames)
- **Settings page**: New route `/settings` with topic weight sliders (0.0–3.0 per category)
- **Feed**: Auto-passes `?user=xxx` when user is selected

### New Files

- `users/__init__.py`
- `users/models.py` — UserProfile SQLAlchemy model
- `users/service.py` — CRUD operations for user profiles (immutable update pattern)
- `api/user_routes.py` — User API endpoints (prefix `/api`, registered in `main.py`)
- `frontend/src/pages/SettingsPage.tsx`
- `tests/test_user_profiles.py`
- `tests/test_personalized_feed.py`

### Modified Files

- `main.py` — Register `user_routes.router`
- `api/ui_routes.py` — Add `user` query param to `get_feed()`

---

## Feature 3: Quant Bridge

### Concept

Extract stock tickers from articles, then fetch price impact data from quant-data-pipeline (localhost:8000) to show how events correlated with price movements.

### Ticker Extraction — Keyword Tagger Extension

Extend `tagging/keywords.py` to extract tickers alongside topic tags:

**Three matching rules (applied in order, deduplicated):**

1. **Cashtag format**: regex `\$([A-Z]{1,5})\b` → extracts "NVDA" from "$NVDA"
2. **Company name mapping**: lookup table in `config.py` → `TICKER_ALIASES`. Lookup is **case-insensitive** (normalize input via `.upper()` before matching):
   ```python
   TICKER_ALIASES = {
       "NVIDIA": "NVDA", "英伟达": "NVDA",
       "Tesla": "TSLA", "特斯拉": "TSLA",
       "Apple": "AAPL", "苹果": "AAPL",
       # ~50-100 entries covering actively traded names
   }
   ```
3. **Yahoo Finance source**: yahoo_finance collector passes the configured ticker(s) from `config.YAHOO_FINANCE_TICKERS` into each article's result dict as a `tickers` field during `collect()`. `BaseCollector.save()` reads this field if present.

**Storage**: New field `tickers` (TEXT, JSON array) on `articles` table. Written by keyword tagger in `BaseCollector.save()`, same pattern as `tags`.

**Migration**: Add to `db/migrations.py`:
```python
("articles", "tickers", "TEXT"),
```
And add to `db/models.py`:
```python
tickers: Mapped[str | None] = mapped_column(String, nullable=True)
```

**Backfill**: `scripts/backfill_tickers.py` — runs ticker extraction on existing articles that have `tickers IS NULL`. One-time script, same pattern as `scripts/backfill_tags.py`.

### Price Snapshot — Bridge Module

**New module: `bridge/quant.py`**

```python
async def get_price_snapshot(ticker: str, event_date: datetime) -> dict | None:
    """
    Call quant-data-pipeline API for price impact data.
    Returns: {"price_at_event": 142.5, "change_1d": 3.2, "change_3d": 5.1, "change_5d": 4.8}
    Returns None on any failure (timeout, not found, service down).
    """
```

- Target: `GET http://localhost:8000/api/price/{ticker}?date=YYYY-MM-DD`
- Timeout: 3 seconds
- Failure → return None (never block main flow)

**Quant-side requirement**: New endpoint needed in quant-data-pipeline:
- `GET /api/price/{ticker}?date=YYYY-MM-DD`
- Returns: closing price on date + percentage changes at +1d, +3d, +5d
- If ticker or date not in DB → 404

### Event API Extension

`GET /api/events/{id}` response gains `price_impacts`:

```json
{
  "event": { ... },
  "articles": [ ... ],
  "price_impacts": [
    {
      "ticker": "NVDA",
      "price_at_event": 142.50,
      "change_1d": "+3.2%",
      "change_3d": "+5.1%",
      "change_5d": "+4.8%"
    }
  ]
}
```

Ticker list is aggregated from all articles in the event (deduplicated). Price snapshots fetched on-demand via **`asyncio.gather()`** — all tickers in parallel, not sequential. Event route handler must be `async def`.

### Frontend Changes

- **Event detail page**: "Price Impact" section at bottom
- Simple table: Ticker | Event Price | 1D | 3D | 5D
- Green/red color coding for positive/negative changes
- Hidden when no tickers or quant API unavailable

### Error Handling

- quant-data-pipeline down → `price_impacts` = empty array, no error surfaced
- Ticker not in quant DB → skip that ticker
- Timeout (>3s) → skip, return empty
- All failures logged at WARNING level

### New Files

- `bridge/__init__.py`
- `bridge/quant.py` — Price snapshot fetcher (async, uses `httpx`)
- `scripts/backfill_tickers.py` — Backfill tickers for existing articles
- `tests/test_ticker_extraction.py`
- `tests/test_quant_bridge.py`

### Modified Files

- `config.py` — Add `TICKER_ALIASES` dict, `QUANT_API_BASE_URL = "http://localhost:8000"`
- `db/models.py` — Add `tickers` field to `Article`
- `db/migrations.py` — Add `("articles", "tickers", "TEXT")` migration
- `tagging/keywords.py` — Add `extract_tickers()` function
- `collectors/base.py` — Call `extract_tickers()` in `save()`, write to `tickers` field
- `collectors/yahoo_finance.py` — Pass configured ticker in `collect()` output
- `api/event_routes.py` — Add `price_impacts` to event detail (async handler)
- `requirements.txt` — Add `httpx` for async HTTP calls

---

## Implementation Order

1. **Signal Aggregation** (Feature 1) — Foundation for Features 2 and 3
2. **User Personalization** (Feature 2) — Independent of Feature 1 data model, but benefits from events in context rail
3. **Quant Bridge** (Feature 3) — Extends Event model from Feature 1 with price data

---

## Out of Scope

- User authentication (login/password/sessions)
- Source weight personalization (only topic weights in this iteration)
- Embedding-based text similarity for event clustering
- K-line chart visualization (price snapshot table only)
- Caching layer for quant API responses
- LLM-based ticker extraction
