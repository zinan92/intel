# Phase 1: Collector Reliability - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Stop collectors from silently swallowing errors. Persist every collection execution to a new collector_runs table. Add retry with exponential backoff for transient failures. Verify SQLite concurrency safety.

</domain>

<decisions>
## Implementation Decisions

### Error handling strategy
- **D-01:** Keep the `collect_from_source()` return-list interface unchanged (Codex recommendation — don't break the collector contract)
- **D-02:** Wrap `collect_from_source()` in adapters.py with tenacity retry decorator at the adapter dispatch layer (research: this is the exact HTTP boundary)
- **D-03:** Add a CollectorResult dataclass alongside the return value to carry error metadata (status, error_message, error_category, retry_count, duration_ms)
- **D-04:** Scheduler records CollectorResult to collector_runs table after each execution

### Retry policy
- **D-05:** Retry only transient errors: ConnectionError, Timeout, OSError, HTTP 429/500/502/503
- **D-06:** Do NOT retry: HTTP 401/403 (auth), JSON parse errors, missing config/env vars
- **D-07:** 3 attempts max, exponential backoff 2s base with full jitter (tenacity)
- **D-08:** All source types use the same retry policy (no per-source config for v1)
- **D-09:** Xueqiu cookie expiry (400 response) classified as "auth" error, not retried

### Error categorization
- **D-10:** Four categories: transient (timeout, connection, rate limit), auth (401/403/cookie expired), parse (unexpected response format), config (missing env var/dependency)
- **D-11:** Category stored as string enum in CollectorRun row

### CollectorRun model
- **D-12:** Append-only table: source_type, source_key, status (ok/error), articles_fetched, articles_saved, duration_ms, error_message, error_category, retry_count, completed_at
- **D-13:** Indexed on (source_type, completed_at) for health API queries in Phase 2
- **D-14:** 30-day retention with weekly cleanup job (APScheduler, low priority)
- **D-15:** ~60 rows/day = ~1800/month, negligible storage impact

### Database safety
- **D-16:** Verify busy_timeout is set (currently configured in db/database.py); set to 5000ms if not
- **D-17:** Verify session-per-call pattern is correct (Codex noted it already is)
- **D-18:** No separate health.db for v1 — single database, split only if SQLITE_BUSY observed

### Claude's Discretion
- Migration implementation (idempotent ALTER TABLE / CREATE TABLE IF NOT EXISTS)
- CollectorResult dataclass exact fields and typing
- How retry decorator integrates with existing scheduler._run_source_type()
- Test structure and coverage approach
- Logging format (keep existing logging module for v1, structlog deferred to v2)

</decisions>

<specifics>
## Specific Ideas

- Codex found the exact silent failure point: `adapters.py:216-220` catches Exception and returns `[]`
- Research confirmed: retry at adapter dispatch layer, not BaseCollector or scheduler level
- Research: start without pybreaker (circuit breaker), add only if retry storms observed
- Existing `_last_results` in-memory dict should still be updated for backward compat, but collector_runs is the persistent source of truth

</specifics>

<canonical_refs>
## Canonical References

### Retry and error handling
- `.planning/research/ARCHITECTURE.md` — Component boundaries, retry placement rationale, data flow
- `.planning/research/PITFALLS.md` — Retry storm prevention, SQLite contention, collector contract

### Stack decisions
- `.planning/research/STACK.md` — tenacity 9.1.4 recommendation, pybreaker deferral

### Existing code
- `sources/adapters.py` lines 201-220 — The silent failure point to fix
- `collectors/base.py` lines 55-81 — BaseCollector.save() pattern (keep unchanged)
- `db/models.py` — Existing SQLAlchemy models (add CollectorRun here)
- `db/database.py` — Session factory and WAL config
- `db/migrations.py` — Idempotent migration pattern to follow
- `scheduler.py` lines 56-120 — Scheduler job dispatch (integration point for recording)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `db/migrations.py` — Idempotent migration pattern (CREATE TABLE IF NOT EXISTS + ALTER TABLE try/except)
- `scheduler.py:CollectorResult` — Existing dataclass for run results (in-memory only, extend or replace)
- `scheduler.py:_last_results` — Module-level dict, keep updating for backward compat

### Established Patterns
- All models in `db/models.py` use SQLAlchemy DeclarativeBase with type annotations
- Migrations in `db/migrations.py` are idempotent (safe to re-run)
- Collectors return `list[dict[str, Any]]` — this contract is preserved

### Integration Points
- `sources/adapters.py:collect_from_source()` — Wrap with tenacity retry + result recording
- `scheduler.py:_run_source_type()` — After collection, write CollectorRun to database
- `db/database.py:init_db()` — Run new migration at startup

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope (user delegated all decisions to Claude)

</deferred>

---

*Phase: 01-collector-reliability*
*Context gathered: 2026-03-31*
