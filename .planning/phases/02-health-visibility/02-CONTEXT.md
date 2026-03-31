# Phase 2: Health Visibility - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Add health API endpoints that expose per-source status, freshness, error history, and scheduler liveness. Build a frontend /health page showing color-coded source cards with volume anomaly detection. Extend existing health primitives (ContextRail, /api/health) rather than building from scratch.

</domain>

<decisions>
## Implementation Decisions

### Health API design
- **D-01:** New router file `api/health_routes.py` with 2 endpoints: /api/health/sources and /api/health/summary
- **D-02:** Existing /api/health endpoint stays unchanged (backward compatible)
- **D-03:** Health endpoints read from collector_runs table (Phase 1 output)
- **D-04:** Per-source status computed from: last run time vs expected_freshness_hours, last error category, article count

### Scheduler heartbeat
- **D-05:** Heartbeat is a module-level timestamp updated by scheduler on each tick (every 5 min)
- **D-06:** Health endpoint reports scheduler as "dead" if heartbeat older than 10 minutes
- **D-07:** No separate heartbeat table — in-memory timestamp is sufficient (lost on restart, but restart resets scheduler anyway)

### Per-source freshness policy
- **D-08:** Add `expected_freshness_hours` column to source_registry (via migration)
- **D-09:** Seed with sensible defaults: RSS/HN/Reddit = 2h, GitHub = 12h, Yahoo = 6h, others = 4h
- **D-10:** Health status logic: age < expected = ok, age < 2x expected = stale, age > 2x = degraded

### Startup boot log
- **D-11:** On startup, log one INFO line per active source and one WARNING per skipped source (with skip reason)
- **D-12:** Log summary: "X active sources, Y skipped, scheduler started at HH:MM"

### Frontend health page
- **D-13:** New React page at /health route (add to App.tsx router)
- **D-14:** Extend existing ContextRail patterns — same status colors (green/amber/red), same TanStack Query patterns
- **D-15:** Source cards: status dot, source name, freshness ("2h ago"), 24h article count, last error (expandable)
- **D-16:** Overall banner at top: "8/10 sources healthy" with aggregate status
- **D-17:** Volume anomaly: compare 24h count to 7-day average from collector_runs. Flag if below 50%. Show as red text on the card, not a chart.
- **D-18:** Disabled sources: show as gray cards with "Missing GITHUB_TOKEN — set in .env to enable" style instructions
- **D-19:** No Recharts/sparklines for v1 — numbers + colors only. Defer charts to v2.
- **D-20:** Poll /api/health/sources every 60s via TanStack Query (existing pattern)

### Claude's Discretion
- Exact API response shape
- Card component structure and CSS
- Error log display format
- How to detect "disabled" sources (missing env var check vs registry field)

</decisions>

<specifics>
## Specific Ideas

- ContextRail.tsx already renders colored dots per source with ok/degraded/stale status — reuse this pattern
- Codex noted: "a full dashboard with sparklines and anomaly detection is not required" — keep it simple
- User's core request: "每一个数据源都要检查 data freshness" and "获取的数据数量应该保持稳定"
- Volume anomaly is the user's explicit requirement, not gold-plating — implement as number comparison, not chart

</specifics>

<canonical_refs>
## Canonical References

### Phase 1 outputs (this phase depends on)
- `sources/errors.py` — ErrorCategory, CollectorResult used by health status computation
- `db/models.py` — CollectorRun model queried by health endpoints
- `scheduler.py` — Where heartbeat and _record_collector_run live

### Research
- `.planning/research/FEATURES.md` — Table stakes for health monitoring, freshness policies
- `.planning/research/ARCHITECTURE.md` — Health API design, 4 endpoints, TanStack Query polling

### Existing code
- `api/routes.py` lines 32-95 — Existing /api/health endpoint (keep unchanged)
- `frontend/src/components/ContextRail.tsx` — Existing health display patterns
- `frontend/src/App.tsx` — Router setup for new /health page
- `frontend/src/api/client.ts` — API client patterns

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ContextRail.tsx` — Already renders source health with colored dots, ok/degraded/stale status
- `api/routes.py:/api/health` — Existing health endpoint with per-source status, freshness age_hours
- TanStack Query setup in frontend — same pattern for /health page polling
- Tailwind CSS classes for status colors already established

### Established Patterns
- API routes use FastAPI Router, register in main.py
- Frontend uses React Router, pages in src/pages/
- Data fetching via TanStack Query with staleTime configuration
- Session-per-request pattern in API routes

### Integration Points
- `api/health_routes.py` → register in main.py alongside existing routers
- `frontend/src/pages/HealthPage.tsx` → add route in App.tsx
- `db/migrations.py` → add expected_freshness_hours column migration
- `scheduler.py` → add heartbeat timestamp update

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-health-visibility*
*Context gathered: 2026-03-31*
