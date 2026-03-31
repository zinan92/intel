# Phase 2: Health Visibility - Research

**Researched:** 2026-03-31
**Domain:** Health monitoring API + frontend dashboard for data pipeline sources
**Confidence:** HIGH

## Summary

Phase 2 adds health visibility to an existing FastAPI + React data pipeline. The backend work involves creating a new `api/health_routes.py` router with two endpoints (`/api/health/sources` and `/api/health/summary`), adding an `expected_freshness_hours` column to `source_registry`, implementing a scheduler heartbeat, and adding startup boot logging. The frontend work involves a new `/health` page with color-coded source cards, an overall health banner, volume anomaly flags, and disabled source display.

All infrastructure needed is already in place: Phase 1 created the `collector_runs` table and recording logic, the source registry exists with per-source metadata, ContextRail.tsx already renders health dots with ok/stale/degraded colors, and TanStack Query is configured for polling. The work is straightforward extension of existing patterns with no new libraries required.

**Primary recommendation:** Build backend endpoints first (they can be tested independently), then the frontend page. The migration for `expected_freshness_hours` must happen before the health status logic can use per-source freshness policies.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: New router file `api/health_routes.py` with 2 endpoints: /api/health/sources and /api/health/summary
- D-02: Existing /api/health endpoint stays unchanged (backward compatible)
- D-03: Health endpoints read from collector_runs table (Phase 1 output)
- D-04: Per-source status computed from: last run time vs expected_freshness_hours, last error category, article count
- D-05: Heartbeat is a module-level timestamp updated by scheduler on each tick (every 5 min)
- D-06: Health endpoint reports scheduler as "dead" if heartbeat older than 10 minutes
- D-07: No separate heartbeat table -- in-memory timestamp is sufficient
- D-08: Add `expected_freshness_hours` column to source_registry (via migration)
- D-09: Seed with sensible defaults: RSS/HN/Reddit = 2h, GitHub = 12h, Yahoo = 6h, others = 4h
- D-10: Health status logic: age < expected = ok, age < 2x expected = stale, age > 2x = degraded
- D-11: On startup, log one INFO line per active source and one WARNING per skipped source (with skip reason)
- D-12: Log summary: "X active sources, Y skipped, scheduler started at HH:MM"
- D-13: New React page at /health route (add to App.tsx router)
- D-14: Extend existing ContextRail patterns -- same status colors (green/amber/red), same TanStack Query patterns
- D-15: Source cards: status dot, source name, freshness ("2h ago"), 24h article count, last error (expandable)
- D-16: Overall banner at top: "8/10 sources healthy" with aggregate status
- D-17: Volume anomaly: compare 24h count to 7-day average from collector_runs. Flag if below 50%. Show as red text on the card, not a chart.
- D-18: Disabled sources: show as gray cards with "Missing GITHUB_TOKEN -- set in .env to enable" style instructions
- D-19: No Recharts/sparklines for v1 -- numbers + colors only. Defer charts to v2.
- D-20: Poll /api/health/sources every 60s via TanStack Query (existing pattern)

### Claude's Discretion
- Exact API response shape
- Card component structure and CSS
- Error log display format
- How to detect "disabled" sources (missing env var check vs registry field)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| HLTH-01 | GET /api/health/sources returns per-source status with freshness, counts, last error | New health_routes.py router; query collector_runs + source_registry + articles tables |
| HLTH-02 | GET /api/health/summary returns aggregate stats | Same router; aggregate query over health/sources data |
| HLTH-03 | Scheduler heartbeat updated every 5 min; health endpoint reports alive/dead | Module-level `_heartbeat_ts` in scheduler.py; 10-min threshold |
| HLTH-04 | Per-source freshness policy via expected_freshness_hours | New column on source_registry; idempotent migration in migrations.py |
| HLTH-05 | Startup boot log lists active/skipped sources | Add to CollectorScheduler.start() after _register_jobs() |
| HLTH-06 | Health page at /health with color-coded source statuses | New HealthPage.tsx; reuse ContextRail color patterns |
| HLTH-07 | Overall health banner | Top-level summary component on HealthPage |
| HLTH-08 | Volume anomaly flag (24h vs 7-day avg, 50% threshold) | Backend computes in /api/health/sources; frontend displays as red text |
| HLTH-09 | Disabled sources shown with reason and enable instructions | Backend includes disabled sources with reason; frontend renders gray cards |
</phase_requirements>

## Standard Stack

### Core (already installed, no new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.100.0+ | API router for health endpoints | Already in stack |
| SQLAlchemy | 2.0+ | Query collector_runs, source_registry, articles | Already in stack |
| React | 18.3.1 | Health page UI | Already in stack |
| TanStack Query | 5.60.5 | Polling /api/health/sources every 60s | Already in stack |
| React Router | 6.28.0 | /health route | Already in stack |
| Tailwind CSS | 3.4.15 | Status colors, card layouts | Already in stack |

### No New Dependencies Required

This phase requires zero new packages. Everything is built with existing libraries.

## Architecture Patterns

### Recommended Project Structure (changes only)

```
api/
  health_routes.py     # NEW: /api/health/sources, /api/health/summary
  routes.py            # UNCHANGED: existing /api/health stays
db/
  models.py            # MODIFY: add expected_freshness_hours to SourceRegistry
  migrations.py        # MODIFY: add column migration
scheduler.py           # MODIFY: add heartbeat + boot logging
main.py                # MODIFY: register health_routes router
frontend/src/
  pages/
    HealthPage.tsx     # NEW: /health dashboard page
  components/
    SourceCard.tsx     # NEW: per-source health card (optional, could inline)
  api/
    client.ts          # MODIFY: add healthSources() and healthSummary() methods
  types/
    api.ts             # MODIFY: add HealthSource, HealthSummary interfaces
  App.tsx              # MODIFY: add /health route
  components/
    Sidebar.tsx        # MODIFY: add health nav link
```

### Pattern 1: Health Router Registration

**What:** New FastAPI APIRouter file, registered alongside existing routers in main.py.
**When to use:** Always -- this is the established pattern (see event_routes, user_routes).
**Example:**

```python
# api/health_routes.py
from fastapi import APIRouter

health_router = APIRouter(prefix="/api/health")

@health_router.get("/sources")
def get_health_sources():
    ...

@health_router.get("/summary")
def get_health_summary():
    ...
```

```python
# main.py -- add one line
from api.health_routes import health_router
app.include_router(health_router)
```

### Pattern 2: Session-per-Request (existing pattern)

**What:** Each endpoint creates its own session via `get_session()`, uses try/finally to close.
**When to use:** All DB-reading endpoints.
**Example (from existing api/routes.py):**

```python
session = get_session()
try:
    # queries here
    return result
finally:
    session.close()
```

### Pattern 3: Module-Level Heartbeat

**What:** A module-level `datetime` variable in scheduler.py, updated each scheduler tick.
**When to use:** HLTH-03 requires this specific approach (D-05, D-07).
**Example:**

```python
# scheduler.py
_heartbeat_ts: datetime | None = None

def get_heartbeat() -> datetime | None:
    return _heartbeat_ts

def _update_heartbeat() -> None:
    global _heartbeat_ts
    _heartbeat_ts = datetime.now(timezone.utc)
```

Register as a 5-minute interval job in `_register_jobs()`. The health endpoint checks: if `_heartbeat_ts` is None or older than 10 minutes, scheduler is "dead".

### Pattern 4: TanStack Query Polling (existing pattern)

**What:** `useQuery` with `refetchInterval` for auto-polling.
**When to use:** The health page polls every 60s (D-20).
**Example (derived from existing FeedPage pattern):**

```typescript
const { data, isLoading, isError } = useQuery({
  queryKey: ["health", "sources"],
  queryFn: () => api.healthSources(),
  refetchInterval: 60_000,
  staleTime: 30_000,
});
```

### Pattern 5: Idempotent Column Migration

**What:** Check if column exists before ALTER TABLE ADD COLUMN.
**When to use:** Adding expected_freshness_hours to source_registry.
**Example (from existing migrations.py):**

```python
# In run_migrations()
if not _column_exists(engine, "source_registry", "expected_freshness_hours"):
    conn.execute(text(
        "ALTER TABLE source_registry ADD COLUMN expected_freshness_hours REAL"
    ))
    conn.commit()
```

After migration, seed defaults for existing rows:

```python
# In a post-migration step or in seed.py
# RSS/HN/Reddit = 2, GitHub = 12, Yahoo = 6, others = 4
```

### Anti-Patterns to Avoid

- **Overloading existing /api/health:** D-02 says keep it unchanged. New endpoints go in health_routes.py.
- **Computing volume anomaly on frontend:** The backend should compute the 7-day average and 50% flag. Frontend just displays it.
- **Separate heartbeat table or file:** D-07 explicitly says in-memory timestamp is sufficient.
- **Adding Recharts or any chart library:** D-19 explicitly defers charts to v2.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Status color mapping | Custom color logic | Reuse ContextRail's existing dot color classes | Already tested: green-400/amber-400/red-400/slate-500 |
| API polling | Manual setInterval | TanStack Query `refetchInterval` | Already configured in the project, handles stale/error states |
| Database session management | Connection pooling | Existing `get_session()` + try/finally | Established pattern across all routes |
| Time-ago formatting | Custom function | Simple `Math.round(age_hours)` + "h ago" string | No library needed for this simple case |

## Common Pitfalls

### Pitfall 1: SourceRegistry Column Default on Existing Rows

**What goes wrong:** Adding `expected_freshness_hours` column via ALTER TABLE creates it as NULL for all existing rows. If health logic divides by this or uses it without null-check, it crashes.
**Why it happens:** SQLite ALTER TABLE ADD COLUMN only adds nullable columns. Existing rows get NULL.
**How to avoid:** After adding the column, run an UPDATE to set defaults based on source_type. Health status logic must also handle NULL gracefully (fall back to a sensible default like 4h).
**Warning signs:** NoneType errors when computing status for sources that existed before migration.

### Pitfall 2: Heartbeat Not Updated on First Start

**What goes wrong:** `_heartbeat_ts` starts as None. The 5-minute heartbeat job hasn't fired yet. Health endpoint reports scheduler as "dead" immediately after startup.
**Why it happens:** IntervalTrigger fires after the first interval, not at time zero.
**How to avoid:** Set `_heartbeat_ts = datetime.now(timezone.utc)` in `CollectorScheduler.start()` before the heartbeat job's first tick. Alternatively, schedule the heartbeat job with `next_run_time=datetime.now()`.
**Warning signs:** Health page shows "scheduler dead" right after fresh start.

### Pitfall 3: Volume Anomaly Division by Zero

**What goes wrong:** A new source with zero 7-day history causes division by zero when computing "below 50% of average".
**Why it happens:** New sources or sources that just started have no collector_runs history.
**How to avoid:** If 7-day average is 0 or insufficient data (< 3 days of runs), skip anomaly detection for that source. Return `volume_anomaly: null` instead of a boolean.
**Warning signs:** HTTP 500 on /api/health/sources for newly added sources.

### Pitfall 4: Disabled Source Detection

**What goes wrong:** No clear way to distinguish "disabled because missing env var" from "disabled because user turned it off".
**Why it happens:** `source_registry.is_active = 0` covers both cases. The reason isn't stored.
**How to avoid:** Check environment variables at health-query time for known optional sources. Map: github_release/github_trending need GITHUB_TOKEN, xueqiu needs XUEQIU_COOKIE, social_kol needs clawfeed CLI. If `is_active=1` but the required resource is missing, mark as "disabled" with the specific reason.
**Warning signs:** Gray cards with no actionable instructions.

### Pitfall 5: Slow Health Query on Large collector_runs Table

**What goes wrong:** Querying the latest run per source_type with a GROUP BY on a large table is slow.
**Why it happens:** collector_runs grows ~60 rows/day; after months it could be 5000+ rows.
**How to avoid:** The existing index `idx_collector_runs_type_time` on `(source_type, completed_at)` already covers this. Use a subquery pattern: get MAX(completed_at) per source_type, then join to get the full row.
**Warning signs:** /api/health/sources response time > 500ms.

## Code Examples

### Health Sources Endpoint Query Pattern

```python
# Get latest collector_run per source_type
from sqlalchemy import func

subq = (
    session.query(
        CollectorRun.source_type,
        func.max(CollectorRun.completed_at).label("max_completed"),
    )
    .group_by(CollectorRun.source_type)
    .subquery()
)

latest_runs = (
    session.query(CollectorRun)
    .join(
        subq,
        (CollectorRun.source_type == subq.c.source_type)
        & (CollectorRun.completed_at == subq.c.max_completed),
    )
    .all()
)
```

### Volume Anomaly Computation

```python
# 24h count vs 7-day average from collector_runs
now = datetime.now(timezone.utc)
day_ago = now - timedelta(hours=24)
week_ago = now - timedelta(days=7)

# Per source_type: sum articles_fetched in last 24h
count_24h = (
    session.query(
        CollectorRun.source_type,
        func.sum(CollectorRun.articles_fetched).label("total_24h"),
    )
    .filter(CollectorRun.completed_at >= day_ago)
    .group_by(CollectorRun.source_type)
    .all()
)

# Per source_type: average daily articles over 7 days
count_7d = (
    session.query(
        CollectorRun.source_type,
        func.sum(CollectorRun.articles_fetched).label("total_7d"),
    )
    .filter(CollectorRun.completed_at >= week_ago)
    .group_by(CollectorRun.source_type)
    .all()
)

# avg_daily = total_7d / 7
# anomaly = (total_24h < avg_daily * 0.5)
```

### Freshness Status Logic

```python
def compute_status(
    age_hours: float | None,
    expected_freshness_hours: float | None,
    last_error_category: str | None,
) -> str:
    """D-10 status logic."""
    if age_hours is None:
        return "no_data"
    expected = expected_freshness_hours or 4.0  # fallback default
    if last_error_category in ("auth", "config"):
        return "error"
    if age_hours < expected:
        return "ok"
    if age_hours < expected * 2:
        return "stale"
    return "degraded"
```

### Frontend SourceCard Pattern

```typescript
// Reuse ContextRail color mapping
const STATUS_COLORS: Record<string, string> = {
  ok: "bg-green-400",
  stale: "bg-amber-400",
  degraded: "bg-red-400",
  error: "bg-red-400",
  disabled: "bg-slate-500",
  no_data: "bg-slate-500",
};

const STATUS_TEXT_COLORS: Record<string, string> = {
  ok: "text-green-400",
  stale: "text-amber-400",
  degraded: "text-red-400",
  error: "text-red-400",
  disabled: "text-slate-500",
  no_data: "text-slate-500",
};
```

### Disabled Source Detection

```python
# Map source_type -> required env var / tool
_REQUIRED_RESOURCES: dict[str, tuple[str, str]] = {
    "github_release": ("GITHUB_TOKEN", "Set GITHUB_TOKEN in .env to enable"),
    "github_trending": ("GITHUB_TOKEN", "Set GITHUB_TOKEN in .env to enable"),
    "xueqiu": ("XUEQIU_COOKIE", "Set XUEQIU_COOKIE in .env to enable"),
    "social_kol": ("CLAWFEED_CLI", "Install clawfeed CLI to enable"),
}

def _check_source_disabled(source_type: str) -> str | None:
    """Return disable reason or None if source is available."""
    if source_type not in _REQUIRED_RESOURCES:
        return None
    env_key, message = _REQUIRED_RESOURCES[source_type]
    if env_key == "CLAWFEED_CLI":
        import shutil
        if not shutil.which("clawfeed"):
            return message
    else:
        import os
        if not os.getenv(env_key):
            return message
    return None
```

### API Response Shape (Claude's Discretion)

```python
# Recommended /api/health/sources response
{
    "scheduler_alive": True,
    "scheduler_heartbeat": "2026-03-31T10:05:00Z",
    "sources": [
        {
            "source_type": "rss",
            "display_name": "RSS Feeds",
            "status": "ok",           # ok/stale/degraded/error/disabled/no_data
            "is_active": True,
            "freshness_age_hours": 0.5,
            "expected_freshness_hours": 2.0,
            "articles_24h": 42,
            "articles_7d_avg": 38.5,
            "volume_anomaly": False,   # true if 24h < 50% of 7d avg
            "last_run_at": "2026-03-31T10:00:00Z",
            "last_run_status": "ok",
            "last_error": null,
            "last_error_category": null,
            "disabled_reason": null,   # non-null for disabled sources
        }
    ]
}

# Recommended /api/health/summary response
{
    "total_sources": 10,
    "healthy_count": 8,
    "stale_count": 1,
    "degraded_count": 0,
    "error_count": 1,
    "disabled_count": 0,
    "total_articles_24h": 156,
    "scheduler_alive": True,
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hardcoded 24h freshness threshold | Per-source expected_freshness_hours | This phase (D-08) | Sources with different collection frequencies get appropriate thresholds |
| In-memory _last_results only | collector_runs table + _last_results | Phase 1 (RELY-01) | Historical data available for 7-day volume comparison |
| No scheduler liveness check | Module-level heartbeat timestamp | This phase (D-05) | Can detect scheduler death within 10 minutes |

## Open Questions

1. **Expected freshness for inactive/disabled sources**
   - What we know: D-09 specifies defaults for active sources by type
   - What's unclear: Should disabled sources still show freshness? They won't have recent runs.
   - Recommendation: Disabled sources skip freshness computation entirely; show "disabled" status with reason.

2. **Seeding expected_freshness_hours for existing DB rows**
   - What we know: Migration adds the column as NULL. New seeds via seed.py could set it.
   - What's unclear: seed.py is insert-only -- it won't update existing rows.
   - Recommendation: Add a post-migration UPDATE statement in migrations.py that sets defaults based on source_type WHERE expected_freshness_hours IS NULL. This is idempotent and covers existing rows.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `api/routes.py` (health endpoint pattern), `scheduler.py` (module-level state), `db/migrations.py` (idempotent migration pattern)
- Existing codebase: `frontend/src/components/ContextRail.tsx` (status dot colors), `frontend/src/pages/FeedPage.tsx` (TanStack Query polling)
- Existing codebase: `db/models.py` (CollectorRun, SourceRegistry models), `sources/errors.py` (ErrorCategory)
- Existing codebase: `main.py` (router registration pattern), `frontend/src/App.tsx` (route registration)

### Secondary (MEDIUM confidence)
- CONTEXT.md decisions D-01 through D-20 (user-validated design choices)
- ARCHITECTURE.md research (health API design, build order)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new libraries, everything already installed and in use
- Architecture: HIGH - extending existing patterns (router, migration, TanStack Query)
- Pitfalls: HIGH - identified from direct codebase inspection of existing patterns

**Research date:** 2026-03-31
**Valid until:** 2026-04-30 (stable -- no external library changes affect this work)
