# Morning Brief + Event Detail Page — Design Spec

**Date**: 2026-03-19
**Status**: Approved
**Scope**: Two frontend features that transform the homepage from a flat feed into a signal-focused intelligence brief

---

## Overview

Two connected features:

1. **Morning Brief** — A signal summary area embedded at the top of the existing FeedPage, showing the top 5 cross-source events before the regular feed list
2. **Event Detail Page** — A new `/events/{id}` page showing a multi-source timeline view of a single event with price impact data

Together they answer: "What happened that matters?" instead of "Here are all your articles."

---

## Feature 1: Morning Brief (Feed Top Area)

### Placement

Embedded at the top of the existing FeedPage (`/`), above the filter bar. When no active events exist, the Brief area does not render and the page behaves exactly as before.

### Visual Structure (top to bottom)

**1. Date Header**
- Format: "March 19, 2026 · Morning Brief"
- Style: small uppercase gray text (`text-xs text-gray-400 uppercase tracking-wider`)

**2. Hero Event Card** (highest signal_score event)
- Full-width dark gradient card (`bg-gradient-to-br from-slate-800 to-slate-700`)
- Left side:
  - Signal label: orange uppercase, e.g., "SIGNAL 12.0 · 4 SOURCES"
  - Event name: white, semibold, ~16px
  - Source list: gray small text, e.g., "HackerNews · Reddit · Google News · RSS"
- Right side:
  - Primary ticker symbol(s) as gray pill badges (e.g., "$NVDA · $BTC")
  - No price data in Brief (prices only on Event Detail page)
- Clickable → navigates to `/events/{id}`

**3. Event Grid** (2nd through 5th events)
- 2×2 CSS grid, `gap-3`
- Each card: white background, subtle border, rounded-lg
  - Signal score label (orange or yellow based on score ≥8 vs <8)
  - Event name (12px semibold)
  - Subtitle: source count + ticker symbols (if available, no prices)
- Clickable → navigates to `/events/{id}`

**4. Section Divider**
- "Latest Feed" label in uppercase gray, same style as date header
- Below: existing FeedCard list with all current filters and pagination

### Conditional Rendering

- **0 active events**: Brief area hidden entirely, FeedPage unchanged
- **1 event**: Hero only, no grid
- **2-4 events**: Hero + partial grid
- **5+ events**: Hero + full 2×2 grid (showing top 5 total)

### Data Requirements

The existing `GET /api/ui/feed` response already includes `context.top_events` with `id`, `narrative_tag`, `signal_score`, `source_count`, `article_count`.

**Backend change needed**: Extend `_build_top_events()` in `api/ui_routes.py` to also return:
- `tickers`: list of ticker symbols aggregated from event articles
- `sources`: list of distinct source names

New response shape for each top event:
```json
{
  "id": 1,
  "narrative_tag": "btc-etf-inflows",
  "signal_score": 12.0,
  "source_count": 4,
  "article_count": 5,
  "sources": ["hackernews", "reddit", "google_news", "rss"],
  "tickers": ["BTC", "COIN"]
}
```

Price data is NOT fetched in the feed endpoint (too expensive for a list view). The Brief displays ticker symbols only; actual price changes are shown on the Event Detail page.

### Frontend Changes

- `frontend/src/pages/FeedPage.tsx` — Add `<MorningBrief>` component above filter bar
- `frontend/src/components/MorningBrief.tsx` — New component (hero + grid)
- `frontend/src/components/EventCard.tsx` — Reusable small event card for the grid
- `frontend/src/types/api.ts` — Update `TopEvent` interface with `sources` and `tickers` fields

---

## Feature 2: Event Detail Page

### Route

`/events/:id` — new route in App.tsx

### Visual Structure (top to bottom)

**1. Back Link**
- "← Back to Brief" — navigates to `/`
- Style: small gray text with hover

**2. Event Header**
- Row layout, space-between
- Left: event name (text-xl font-bold) + subtitle (signal score, source count, article count, time since window_start)
- Right: signal score badge (orange bg, white text, large rounded pill)

**3. Source Badges**
- Horizontal row of pills
- Each source as a light blue badge (`bg-blue-100 text-blue-700`)

**4. Price Impact Bar** (conditional)
- Dark background (`bg-slate-800`), rounded, padded
- Section label: "Price Impact" in uppercase gray
- Each ticker in a column:
  - Ticker symbol (gray)
  - Price at event (gray)
  - 1D / 3D / 5D changes (green for positive, red for negative)
- **Hidden when**: no tickers on event, or quant API returned empty price_impacts
- **Data source**: `GET /api/events/{id}` already returns `price_impacts` array

**5. Timeline**
- Left border (2px solid gray-200) with colored dots at each article
- Sorted by article time (most recent first)
- Each entry:
  - Dot: green for newest article, blue for others
  - Time + source label (small gray text)
  - Article title (font-medium, clickable)
  - Summary (first ~100 chars of content, gray text)
- Clicking article title → opens `ItemDrawer` (imported and rendered with local `selectedArticleId` state in EventPage)

### Data Source

Fully served by existing `GET /api/events/{id}` endpoint:
```json
{
  "event": {
    "id": 1,
    "narrative_tag": "btc-etf-inflows",
    "source_count": 4,
    "article_count": 5,
    "signal_score": 12.0,
    "avg_relevance": 4.0,
    "window_start": "2026-03-19T04:00:00",
    "window_end": "2026-03-21T04:00:00",
    "status": "active"
  },
  "articles": [
    {
      "id": 123,
      "title": "Bitcoin ETF sees record inflow",
      "source": "google_news",
      "url": "https://...",
      "relevance_score": 5,
      "summary": "BlackRock's iShares Bitcoin Trust led with $800M in single-day inflows...",
      "published_at": "2026-03-19T04:30:00",
      "collected_at": "2026-03-19T05:00:00"
    }
  ],
  "price_impacts": [
    {
      "ticker": "BTC",
      "price_at_event": 67420.0,
      "change_1d": 3.2,
      "change_3d": 5.1,
      "change_5d": 4.8
    }
  ]
}
```

**Backend change needed**: Add `summary` field (first 150 chars of `content`) to the article serialization in `get_event_detail()` in `api/event_routes.py`. This provides text for the timeline summary without sending full article content.

### Frontend Changes

- `frontend/src/pages/EventPage.tsx` — New page component; reads `id` from `useParams()`, parses to integer; renders `ItemDrawer` with local `selectedArticleId` state
- `frontend/src/App.tsx` — Add `/events/:id` route
- `frontend/src/api/client.ts` — Add `eventDetail(id)` method
- `frontend/src/types/api.ts` — Add `EventDetail`, `EventInfo`, `PriceImpact` types

---

## Backend Changes Summary

Only one backend modification needed:

**`api/ui_routes.py` — `_build_top_events()`**

Extend to join through `event_articles` → `articles` to aggregate:
- `sources`: distinct `article.source` values
- `tickers`: distinct tickers from `article.tickers` JSON field

Aggregate sources and tickers for all top-5 events in a **single batched query** (join `EventArticle` → `Article` filtered on `event_id IN (...)`), then group in Python. Do NOT use per-event subqueries.

---

## New Files

| File | Purpose |
|------|---------|
| `frontend/src/components/MorningBrief.tsx` | Brief area: hero event + event grid |
| `frontend/src/components/EventCard.tsx` | Reusable small event card |
| `frontend/src/pages/EventPage.tsx` | Event detail page with timeline |

## Modified Files

| File | Changes |
|------|---------|
| `api/ui_routes.py` | Extend `_build_top_events()` with sources + tickers (batched query) |
| `api/event_routes.py` | Add `summary` field to article serialization in `get_event_detail()` |
| `frontend/src/components/ContextRail.tsx` | Remove "Active Events" section (replaced by Morning Brief) |
| `frontend/src/types/api.ts` | Update TopEvent, add EventDetail/PriceImpact types |
| `frontend/src/api/client.ts` | Add `eventDetail(id)` method |
| `frontend/src/pages/FeedPage.tsx` | Import and render `<MorningBrief>` above filters |
| `frontend/src/App.tsx` | Add `/events/:id` route |

---

## Out of Scope

- Price data in Brief cards (only ticker symbols; prices shown on detail page)
- Event search or filtering
- Event notifications / Telegram push
- Ticker detail page (`/tickers/{symbol}`)
- LLM-generated event summaries
