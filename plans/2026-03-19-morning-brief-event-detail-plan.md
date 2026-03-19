# Morning Brief + Event Detail Page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the homepage from a flat feed into a signal-focused intelligence brief with top events and clickable event detail pages.

**Architecture:** Two connected frontend features backed by minor backend extensions. Morning Brief embeds at the top of the existing FeedPage, showing hero event + 2×2 event grid. Event Detail is a new page with multi-source timeline + price impacts. Backend changes: extend `_build_top_events()` with batched source/ticker queries, add `summary` to event article serialization, remove duplicate Active Events from ContextRail.

**Tech Stack:** React 18, TypeScript, TanStack Query, React Router, Tailwind CSS, FastAPI, SQLAlchemy

**Spec:** `plans/2026-03-19-morning-brief-event-detail-design.md`

---

## File Map

### New Files
| File | Purpose |
|------|---------|
| `frontend/src/components/MorningBrief.tsx` | Brief area: date header + hero event + 2×2 event grid |
| `frontend/src/components/EventCard.tsx` | Reusable small event card for the grid |
| `frontend/src/pages/EventPage.tsx` | Event detail page: header + price impact + timeline |

### Modified Files
| File | Changes |
|------|---------|
| `api/ui_routes.py` | Extend `_build_top_events()` with batched sources + tickers |
| `api/event_routes.py` | Add `summary` field to article serialization |
| `frontend/src/types/api.ts` | Update TopEvent, add EventDetail/EventArticle/PriceImpact types |
| `frontend/src/api/client.ts` | Add `eventDetail(id)` method |
| `frontend/src/pages/FeedPage.tsx` | Render `<MorningBrief>` above filter bar |
| `frontend/src/components/ContextRail.tsx` | Remove "Active Events" section |
| `frontend/src/App.tsx` | Add `/events/:id` route |

---

## Task 1: Backend — Extend top_events with sources + tickers

**Files:**
- Modify: `api/ui_routes.py`

- [ ] **Step 1: Read current `_build_top_events` and understand the data flow**

Current implementation (around line 270 in `api/ui_routes.py`):
```python
def _build_top_events(session: Any) -> list[dict[str, Any]]:
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

- [ ] **Step 2: Extend with batched source + ticker query**

Replace `_build_top_events` with:

```python
def _build_top_events(session: Any) -> list[dict[str, Any]]:
    """Fetch top active events with sources and tickers (batched query)."""
    from events.models import Event, EventArticle

    events = (
        session.query(Event)
        .filter(Event.status == "active")
        .order_by(Event.signal_score.desc())
        .limit(5)
        .all()
    )
    if not events:
        return []

    event_ids = [e.id for e in events]

    # Single batched query for all event articles
    rows = (
        session.query(EventArticle.event_id, Article.source, Article.tickers)
        .join(Article, EventArticle.article_id == Article.id)
        .filter(EventArticle.event_id.in_(event_ids))
        .all()
    )

    # Group by event_id
    from collections import defaultdict
    event_sources: dict[int, set[str]] = defaultdict(set)
    event_tickers: dict[int, list[str]] = defaultdict(list)
    for event_id, source, tickers_json in rows:
        event_sources[event_id].add(source)
        if tickers_json:
            for t in _parse_tags(tickers_json):
                if t and t not in event_tickers[event_id]:
                    event_tickers[event_id].append(t)

    return [
        {
            "id": e.id,
            "narrative_tag": e.narrative_tag,
            "signal_score": e.signal_score,
            "source_count": e.source_count,
            "article_count": e.article_count,
            "sources": sorted(event_sources.get(e.id, set())),
            "tickers": event_tickers.get(e.id, [])[:5],  # limit to 5 tickers
        }
        for e in events
    ]
```

- [ ] **Step 3: Run existing tests to verify no regression**

Run: `cd /Users/wendy/work/trading-co/park-intel && .venv/bin/python -m pytest tests/test_ui_feed_api.py tests/test_event_api.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add api/ui_routes.py
git commit -m "feat: extend top_events with batched sources and tickers"
```

---

## Task 2: Backend — Add summary to event detail articles

**Files:**
- Modify: `api/event_routes.py`

- [ ] **Step 1: Read current article serialization in `get_event_detail()`**

Current code builds an `articles` list without `content` or `summary`. The `EventPage` timeline needs a short summary.

- [ ] **Step 2: Add `summary` field to article dict**

In `get_event_detail()`, update the article list comprehension to include:

```python
        articles = [
            {
                "id": a.id,
                "title": a.title,
                "source": a.source,
                "url": a.url,
                "relevance_score": a.relevance_score,
                "summary": (a.content or "")[:150],
                "published_at": a.published_at.isoformat() if a.published_at else None,
                "collected_at": a.collected_at.isoformat() if a.collected_at else None,
            }
            for a in linked
        ]
```

Remove the `_parse_tags` helper and `tags` field that were in the original — they're unused by the EventPage.

- [ ] **Step 3: Run tests**

Run: `cd /Users/wendy/work/trading-co/park-intel && .venv/bin/python -m pytest tests/test_event_api.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add api/event_routes.py
git commit -m "feat: add summary field to event detail article serialization"
```

---

## Task 3: Frontend Types + API Client

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Update TopEvent interface**

In `frontend/src/types/api.ts`, update `TopEvent`:

```typescript
export interface TopEvent {
  id: number;
  narrative_tag: string;
  signal_score: number;
  source_count: number;
  article_count: number;
  sources: string[];
  tickers: string[];
}
```

- [ ] **Step 2: Add EventDetail types**

Add to `frontend/src/types/api.ts`:

```typescript
export interface EventArticle {
  id: number;
  title: string | null;
  source: string;
  url: string | null;
  relevance_score: number | null;
  summary: string;
  published_at: string | null;
  collected_at: string | null;
}

export interface PriceImpact {
  ticker: string;
  price_at_event: number;
  change_1d: number;
  change_3d: number;
  change_5d: number;
}

export interface EventInfo {
  id: number;
  narrative_tag: string;
  source_count: number;
  article_count: number;
  signal_score: number;
  avg_relevance: number;
  window_start: string | null;
  window_end: string | null;
  status: string;
}

export interface EventDetail {
  event: EventInfo;
  articles: EventArticle[];
  price_impacts: PriceImpact[];
}
```

- [ ] **Step 3: Add eventDetail method to API client**

Add to the `api` object in `frontend/src/api/client.ts`:

```typescript
  eventDetail: (id: number): Promise<EventDetail> =>
    get(`/api/events/${id}`),
```

Add `EventDetail` to the import from `../types/api`.

- [ ] **Step 4: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add frontend/src/types/api.ts frontend/src/api/client.ts
git commit -m "feat: add EventDetail types and API client method"
```

---

## Task 4: EventCard Component

**Files:**
- Create: `frontend/src/components/EventCard.tsx`

- [ ] **Step 1: Create EventCard component**

```tsx
// frontend/src/components/EventCard.tsx
import { Link } from "react-router-dom";
import type { TopEvent } from "../types/api";

interface Props {
  event: TopEvent;
}

export function EventCard({ event }: Props) {
  const scoreColor = event.signal_score >= 8 ? "text-orange-500" : "text-yellow-500";

  return (
    <Link
      to={`/events/${event.id}`}
      className="block bg-white border border-gray-200 rounded-lg p-3 hover:border-brand-400 hover:shadow-sm transition-all"
    >
      <div className={`text-[10px] font-semibold uppercase ${scoreColor}`}>
        Signal {event.signal_score.toFixed(1)}
      </div>
      <div className="text-sm font-semibold text-gray-800 mt-0.5 line-clamp-1">
        {event.narrative_tag.replace(/-/g, " ")}
      </div>
      <div className="text-xs text-gray-500 mt-1">
        {event.source_count} sources
        {event.tickers.length > 0 && (
          <span className="ml-1.5 text-gray-400">
            · {event.tickers.slice(0, 2).map(t => `$${t}`).join(" ")}
          </span>
        )}
      </div>
    </Link>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add frontend/src/components/EventCard.tsx
git commit -m "feat: add EventCard component"
```

---

## Task 5: MorningBrief Component

**Files:**
- Create: `frontend/src/components/MorningBrief.tsx`

- [ ] **Step 1: Create MorningBrief component**

```tsx
// frontend/src/components/MorningBrief.tsx
import { Link } from "react-router-dom";
import { EventCard } from "./EventCard";
import type { TopEvent } from "../types/api";

interface Props {
  events: TopEvent[];
}

export function MorningBrief({ events }: Props) {
  if (events.length === 0) return null;

  const [hero, ...rest] = events;
  const gridEvents = rest.slice(0, 4);

  const today = new Date().toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="mb-6">
      {/* Date Header */}
      <p className="text-xs text-gray-400 uppercase tracking-wider mb-3">
        {today} · Morning Brief
      </p>

      {/* Hero Event */}
      <Link
        to={`/events/${hero.id}`}
        className="block bg-gradient-to-br from-slate-800 to-slate-700 rounded-xl p-4 mb-3 hover:from-slate-700 hover:to-slate-600 transition-all"
      >
        <div className="flex justify-between items-start">
          <div>
            <div className="text-[10px] font-semibold text-orange-400 uppercase tracking-wide">
              Signal {hero.signal_score.toFixed(1)} · {hero.source_count} sources
            </div>
            <div className="text-base font-semibold text-white mt-1">
              {hero.narrative_tag.replace(/-/g, " ")}
            </div>
            <div className="text-xs text-slate-400 mt-1">
              {hero.sources.join(" · ")}
            </div>
          </div>
          {hero.tickers.length > 0 && (
            <div className="text-right shrink-0 ml-4">
              <div className="text-xs text-slate-400">
                {hero.tickers.slice(0, 3).map(t => `$${t}`).join(" · ")}
              </div>
            </div>
          )}
        </div>
      </Link>

      {/* Event Grid */}
      {gridEvents.length > 0 && (
        <div className="grid grid-cols-2 gap-3 mb-4">
          {gridEvents.map((event) => (
            <EventCard key={event.id} event={event} />
          ))}
        </div>
      )}

      {/* Divider */}
      <p className="text-xs text-gray-400 uppercase tracking-wider mt-2">
        Latest Feed
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add frontend/src/components/MorningBrief.tsx
git commit -m "feat: add MorningBrief component with hero event and grid"
```

---

## Task 6: Integrate MorningBrief into FeedPage + Remove ContextRail Duplicate

**Files:**
- Modify: `frontend/src/pages/FeedPage.tsx`
- Modify: `frontend/src/components/ContextRail.tsx`

- [ ] **Step 1: Add MorningBrief to FeedPage**

In `frontend/src/pages/FeedPage.tsx`:

Add import:
```tsx
import { MorningBrief } from "../components/MorningBrief";
```

Inside the component, extract `top_events` from context:
```tsx
const topEvents = context?.top_events ?? [];
```

Render `<MorningBrief>` BEFORE the filter bar `<div className="flex flex-wrap items-center gap-3 mb-4">`:
```tsx
<MorningBrief events={topEvents} />
```

- [ ] **Step 2: Remove Active Events from ContextRail**

In `frontend/src/components/ContextRail.tsx`, delete the entire "Active Events" block (the `{context?.top_events && context.top_events.length > 0 && (...)}` section).

- [ ] **Step 3: Build frontend to verify**

Run: `cd /Users/wendy/work/trading-co/park-intel/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add frontend/src/pages/FeedPage.tsx frontend/src/components/ContextRail.tsx
git commit -m "feat: integrate MorningBrief into FeedPage, remove ContextRail duplicate"
```

---

## Task 7: EventPage Component

**Files:**
- Create: `frontend/src/pages/EventPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create EventPage**

```tsx
// frontend/src/pages/EventPage.tsx
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { ItemDrawer } from "../components/ItemDrawer";
import type { EventArticle as EventArticleType } from "../types/api";

function formatTimeAgo(iso: string | null): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 1) return "just now";
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function PriceChange({ value }: { value: number }) {
  const color = value >= 0 ? "text-green-400" : "text-red-400";
  const sign = value >= 0 ? "+" : "";
  return <span className={`text-xs ${color}`}>{sign}{value.toFixed(1)}%</span>;
}

export function EventPage() {
  const { id } = useParams<{ id: string }>();
  const eventId = parseInt(id ?? "0", 10);
  const [selectedArticleId, setSelectedArticleId] = useState<number | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["event", eventId],
    queryFn: () => api.eventDetail(eventId),
    enabled: eventId > 0,
  });

  if (isLoading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-6 bg-gray-100 rounded w-48" />
        <div className="h-20 bg-gray-100 rounded-xl" />
        <div className="h-40 bg-gray-100 rounded-lg" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="text-sm text-red-500 bg-red-50 px-4 py-3 rounded-lg">
        Failed to load event. <Link to="/" className="underline">Back to Brief</Link>
      </div>
    );
  }

  const { event, articles, price_impacts } = data;
  const sortedArticles = [...articles].sort((a, b) => {
    const ta = a.published_at || a.collected_at || "";
    const tb = b.published_at || b.collected_at || "";
    return tb.localeCompare(ta); // newest first
  });

  return (
    <div className="max-w-2xl">
      {/* Back Link */}
      <Link to="/" className="text-sm text-gray-500 hover:text-gray-700 mb-4 inline-block">
        ← Back to Brief
      </Link>

      {/* Event Header */}
      <div className="flex justify-between items-start mb-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900">
            {event.narrative_tag.replace(/-/g, " ")}
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {event.source_count} sources · {event.article_count} articles · {formatTimeAgo(event.window_start)}
          </p>
        </div>
        <div className="bg-orange-500 text-white text-lg font-bold px-3.5 py-1.5 rounded-lg shrink-0 ml-4">
          {event.signal_score.toFixed(1)}
        </div>
      </div>

      {/* Source Badges */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {Array.from(new Set(articles.map(a => a.source))).map((source) => (
          <span
            key={source}
            className="bg-blue-100 text-blue-700 text-[10px] px-2 py-0.5 rounded-full"
          >
            {source}
          </span>
        ))}
      </div>

      {/* Price Impact Bar */}
      {price_impacts.length > 0 && (
        <div className="bg-slate-800 rounded-lg p-4 mb-5">
          <p className="text-[9px] text-slate-400 uppercase tracking-wider mb-2">Price Impact</p>
          <div className="flex gap-6">
            {price_impacts.map((pi) => (
              <div key={pi.ticker}>
                <div className="text-xs text-slate-400">${pi.ticker}</div>
                <div className="text-xs text-slate-500">{pi.price_at_event.toLocaleString()}</div>
                <div className="flex gap-2 mt-1">
                  <span className="text-[10px] text-slate-500">1D</span><PriceChange value={pi.change_1d} />
                  <span className="text-[10px] text-slate-500">3D</span><PriceChange value={pi.change_3d} />
                  <span className="text-[10px] text-slate-500">5D</span><PriceChange value={pi.change_5d} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Timeline */}
      <p className="text-[9px] text-gray-400 uppercase tracking-wider mb-3">Timeline</p>
      <div className="border-l-2 border-gray-200 pl-4 space-y-4">
        {sortedArticles.map((article, idx) => {
          const dotColor = idx === 0 ? "bg-green-500" : "bg-blue-500";
          const timeStr = formatTimeAgo(article.published_at || article.collected_at);

          return (
            <div key={article.id} className="relative">
              <div
                className={`absolute -left-[21px] top-1.5 w-2 h-2 rounded-full ${dotColor}`}
              />
              <div className="text-xs text-gray-400">
                {timeStr} · {article.source}
              </div>
              <button
                onClick={() => setSelectedArticleId(article.id)}
                className="text-sm font-medium text-gray-800 hover:text-brand-600 text-left mt-0.5"
              >
                {article.title || "Untitled"}
              </button>
              {article.summary && (
                <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">
                  {article.summary}
                </p>
              )}
            </div>
          );
        })}
      </div>

      {/* ItemDrawer */}
      <ItemDrawer
        itemId={selectedArticleId}
        onClose={() => setSelectedArticleId(null)}
      />
    </div>
  );
}
```

- [ ] **Step 2: Add route to App.tsx**

In `frontend/src/App.tsx`:

Add import:
```tsx
import { EventPage } from "./pages/EventPage";
```

Add route (after the `/settings` route):
```tsx
<Route path="/events/:id" element={<EventPage />} />
```

- [ ] **Step 3: Build frontend**

Run: `cd /Users/wendy/work/trading-co/park-intel/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
cd /Users/wendy/work/trading-co/park-intel && git add frontend/src/pages/EventPage.tsx frontend/src/App.tsx
git commit -m "feat: add EventPage with timeline, price impacts, and ItemDrawer integration"
```

---

## Task 8: Final Verification

**Files:** None (verification only)

- [ ] **Step 1: Run full backend test suite**

Run: `cd /Users/wendy/work/trading-co/park-intel && .venv/bin/python -m pytest tests/ -v`
Expected: All pass (except pre-existing `test_health_no_data_status_for_fresh_source`)

- [ ] **Step 2: Build frontend**

Run: `cd /Users/wendy/work/trading-co/park-intel/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Verify server loads**

Run: `cd /Users/wendy/work/trading-co/park-intel && PYTHONPATH=. .venv/bin/python -c "from main import app; print('OK')"`
Expected: "OK"

- [ ] **Step 4: Restart servers and verify in browser**

```bash
lsof -ti:8001 | xargs kill 2>/dev/null
sleep 1
PYTHONPATH=/Users/wendy/work/trading-co/park-intel /Users/wendy/work/trading-co/park-intel/.venv/bin/python /Users/wendy/work/trading-co/park-intel/main.py &
```

Verify at http://localhost:5174:
- Morning Brief appears at top of feed with hero event + grid
- Clicking an event navigates to `/events/{id}` with timeline
- Price Impact bar shows when tickers have data
- ContextRail no longer shows duplicate "Active Events"
- Back link returns to feed
