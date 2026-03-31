# Project Research Summary

**Project:** Park-Intel Reliability & Open-Source Milestone
**Domain:** Self-hosted data pipeline health monitoring, collector reliability, developer onboarding
**Researched:** 2026-03-31
**Confidence:** HIGH

## Executive Summary

Park-intel is an existing FastAPI + React qualitative signal pipeline with 10 collector types, 283 passing tests, and a working feed-first UI. This milestone adds three capabilities that do not exist today: collector retry/resilience, persistent health monitoring with a visual dashboard, and open-source packaging with launchd deployment. The research consensus is clear -- this is an instrumentation project, not a rewrite. The existing scheduler, adapter, and collector layers remain unchanged; we wrap them with retry logic, record execution history to a new SQLite table, and build a read-only dashboard on top.

The recommended approach follows the "Record-then-Report" pattern used by Dagster and Airflow: every collector execution writes an immutable `CollectorRun` row to SQLite. The health dashboard reads these rows to compute status, freshness, volume trends, and error rates. Retry logic hooks in at the adapter dispatch layer (the exact HTTP boundary where transient failures occur), using tenacity for exponential backoff with jitter. No new infrastructure is needed -- no Prometheus, no Redis, no Docker. The only new backend dependencies are tenacity (retry), pybreaker (optional circuit breaker), and structlog (structured logging). The frontend adds only recharts for dashboard charts.

The three critical risks are: (1) retry storms overwhelming upstream APIs if jitter and error classification are not implemented correctly, (2) SQLite write contention from adding monitoring writes alongside existing collector writes (mitigated by batching or a separate health.db), and (3) breaking the implicit collector contract during error surfacing refactors (mitigated by keeping the return-list interface and adding error metadata alongside it, not replacing it). The existing CONCERNS.md tech debt -- specifically session isolation and the _last_results threading issue -- must be fixed before adding monitoring writes.

## Key Findings

### Recommended Stack

The existing stack (FastAPI, SQLAlchemy 2.0, SQLite WAL, React 18, TypeScript, Vite, Tailwind, TanStack Query, D3) stays unchanged. Only four new dependencies are needed. See [STACK.md](STACK.md) for full rationale.

**New backend dependencies:**
- **tenacity 9.1.4**: Retry with exponential backoff and jitter for all collectors -- de facto Python standard, 170M+ monthly downloads, native async support
- **pybreaker 1.4.1**: Circuit breaker for external API calls -- prevents hammering degraded sources (optional, architecture research suggests simple retry may suffice for low-frequency collection)
- **structlog 25.5.0**: Structured JSON logging -- machine-parseable output for health dashboard queries, replaces basic logging/print

**New frontend dependency:**
- **recharts 3.8.1**: React-native chart components for health dashboard -- wraps D3 in declarative JSX, avoids writing raw D3 for standard line/bar charts

**Infrastructure:**
- **launchd LaunchAgent**: macOS-native process persistence, auto-restart on crash, no Docker dependency
- **pyproject.toml (PEP 621)**: Replace requirements.txt for open-source packaging -- zero-new-tooling for contributors

### Expected Features

From [FEATURES.md](FEATURES.md), organized by priority.

**Must have (table stakes):**
- Per-source status indicator (ok/stale/degraded/no_data) with color coding
- Data freshness per source with human-readable display and per-source thresholds
- Collection volume with 24h/7d trend context
- Run history (persistent `collector_runs` table replacing in-memory `_last_results`)
- Retry logic for transient failures (3 attempts, exponential backoff)
- Error categorization (transient vs auth vs parse vs config)
- Scheduler liveness heartbeat
- Startup health validation (boot log of active/skipped sources)
- Frontend health dashboard page

**Should have (differentiators):**
- Volume trend sparklines (7-day per source)
- Per-source freshness policies (replace hardcoded 24h threshold)
- Simple anomaly detection (50% drop from 7-day rolling average)
- Dead-letter logging for exhausted retries
- One-command setup validation script
- Graceful degradation reporting (show disabled sources with enable instructions)
- Source dependency health (ping quant bridge and Claude API)

**Defer (v2+):**
- Historical freshness timeline (high complexity, needs weeks of data)
- Complex alerting (email/Slack/PagerDuty)
- Multi-user RBAC
- ML-based anomaly detection
- Data lineage visualization
- Prometheus/Grafana integration

### Architecture Approach

The architecture adds three layers to the existing pipeline without restructuring it. See [ARCHITECTURE.md](ARCHITECTURE.md) for system diagram and implementation patterns.

**Major components:**
1. **`collector_runs` table** -- Append-only immutable log of every collection execution (source_type, status, articles_fetched, articles_saved, duration, error_message, retry_count). Indexed on (source_type, completed_at). 30-day retention with weekly cleanup.
2. **`retry_with_recording()` wrapper** -- tenacity decorator on adapter dispatch function (`collect_from_source()`). Retries only ConnectionError/Timeout/OSError. 3 attempts, exponential backoff 2s/4s with jitter. Records outcome to collector_runs.
3. **`api/health_routes.py` router** -- Four new endpoints: `/api/health/sources` (per-source current status), `/api/health/history` (time-series for charts), `/api/health/errors` (recent failures), `/api/health/summary` (aggregate stats). Backward-compatible with existing `/api/health`.
4. **Health Dashboard (frontend)** -- New React page with SourceStatusGrid, CollectionTimeline (sparklines), ErrorLog, OverallBanner. TanStack Query polling at 60s intervals.
5. **launchd plist + management scripts** -- User-level LaunchAgent with KeepAlive, absolute paths, structured log output. Wrapper script for venv activation.

### Critical Pitfalls

Top 5 from [PITFALLS.md](PITFALLS.md), in order of risk:

1. **Retry storms on transient failures** -- Use exponential backoff with FULL jitter, classify errors (only retry transient), max 3 attempts per cycle. Never retry 4xx errors.
2. **SQLite write contention from monitoring + collection** -- Batch monitoring writes on interval (not per-event), configure `PRAGMA busy_timeout = 5000`, consider separate health.db. Fix session isolation from CONCERNS.md first.
3. **Breaking collector contract during error surfacing** -- Keep the return-list contract. Add `CollectorResult(articles=[], errors=[], warnings=[])` alongside existing flow. Refactor one collector at a time with tests.
4. **launchd permission and environment failures** -- Use absolute paths everywhere, set WorkingDirectory, set StandardOutPath/StandardErrorPath, test with `launchctl kickstart` not `load`. Add startup health check file.
5. **Open-source clone-to-run failure** -- Ship `.env.example`, auto-create `data/` directory, graceful degradation for optional deps (Playwright, claude CLI), fresh-clone CI test, audit for hardcoded `/Users/` paths.

## Implications for Roadmap

Based on combined research, the dependency graph dictates a clear 5-phase structure.

### Phase 1: Foundation -- Data Model and Tech Debt

**Rationale:** Everything depends on the `collector_runs` table and fixed session isolation. PITFALLS.md explicitly warns that monitoring writes on top of unfixed threading issues causes data corruption. This must come first.
**Delivers:** CollectorRun SQLAlchemy model, idempotent migration, PRAGMA busy_timeout configuration, session isolation fix from CONCERNS.md, _last_results threading fix.
**Addresses:** Run history table (table stakes), database migration safety
**Avoids:** SQLite write contention (#2), migration breaking existing data (#10)

### Phase 2: Retry and Error Handling

**Rationale:** Retry logic must exist before the health dashboard can meaningfully distinguish "transient failure" from "broken source." Error classification and retry are designed together per PITFALLS.md dependency graph.
**Delivers:** tenacity retry wrapper on adapter dispatch, error categorization (transient/auth/parse/config), structlog integration, dead-letter logging for exhausted retries
**Addresses:** Retry logic, error categorization, error visibility (table stakes)
**Avoids:** Retry storms (#1), masking permanent failures (#9), breaking collector contract (#3)

### Phase 3: Health API and Scheduler Monitoring

**Rationale:** API endpoints must exist before the frontend dashboard can be built. Scheduler heartbeat is a low-effort addition that prevents the silent-death failure mode.
**Delivers:** health_routes.py with 4 endpoints, scheduler heartbeat job (5-min interval), per-source freshness policies, startup health validation, APScheduler event listeners
**Addresses:** Scheduler liveness, freshness policies, startup validation (table stakes); source dependency health (differentiator)
**Avoids:** Over-engineering the dashboard (#6), stale state on crash (#7), APScheduler crash undetected (#11)

### Phase 4: Frontend Health Dashboard

**Rationale:** Frontend is the visualization layer that depends on all API work being complete. Recharts added here for trend charts.
**Delivers:** Health dashboard React page at `/health`, source status grid with color coding, error log, overall banner, volume trend sparklines (after data accumulates), anomaly detection flags
**Addresses:** Frontend health dashboard (table stakes); sparklines, anomaly detection, graceful degradation reporting (differentiators)
**Avoids:** WebSocket over-engineering (#6 anti-pattern), dashboard scope creep

### Phase 5: Deployment and Open-Source Packaging

**Rationale:** Packaging is the final phase per PITFALLS.md -- it depends on all functional work being stable. launchd is independent of dashboard work and could partially overlap with Phase 4.
**Delivers:** launchd plist + management scripts, pyproject.toml migration, `.env.example`, `scripts/check_setup.py` validation, README with tested commands, CORS hardened to localhost, fresh-clone CI test, hardcoded path audit
**Addresses:** One-command setup (differentiator), all open-source onboarding concerns
**Avoids:** launchd env/path failures (#4), clone-to-run failure (#5), hardcoded paths (#8), CORS exposure (#13), README-driven fiction (#12)

### Phase Ordering Rationale

- **Phase 1 before Phase 2**: Retry writes CollectorRun rows; the table must exist first. Session isolation must be fixed before any new concurrent writes.
- **Phase 2 before Phase 3**: Health API reads retry outcomes and error categories from collector_runs. Without retry data, the API returns empty results.
- **Phase 3 before Phase 4**: Frontend calls health API endpoints. Building UI before API exists means mocking data and rework.
- **Phase 5 last**: Open-source packaging documents what exists. Documenting before building creates aspirational fiction (Pitfall #12). However, `.env.example` and auto-directory-creation should be added early (Phase 1) since they cost nothing.
- **launchd (Phase 5) can partially overlap Phase 3-4**: It wraps the existing process with no code changes. Start it once the core API is stable.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (Retry):** Error classification taxonomy needs validation against actual collector failure modes. Run each collector with network disconnected and capture real error types before designing the retry policy.
- **Phase 5 (Open-Source):** Fresh-clone testing may reveal undocumented dependencies or config assumptions. The 80MB production database needs migration testing.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** Standard SQLAlchemy model + migration. Well-documented patterns.
- **Phase 3 (Health API):** Standard FastAPI router with SQLAlchemy queries. No novel patterns.
- **Phase 4 (Frontend Dashboard):** Standard React + Recharts + TanStack Query. Well-documented.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All recommendations are mainstream libraries with high adoption. tenacity and structlog are de facto standards. No risky or niche choices. |
| Features | HIGH | Feature landscape derived from Dagster, Airflow, Monte Carlo -- mature data pipeline monitoring tools with extensive documentation. |
| Architecture | HIGH | "Instrument, don't restructure" approach is well-supported by existing codebase analysis. Build order has clear dependency chain. |
| Pitfalls | HIGH | All critical pitfalls are well-documented in distributed systems literature (Google SRE, SQLite docs). Project-specific pitfalls validated against CONCERNS.md. |

**Overall confidence:** HIGH

### Gaps to Address

- **Circuit breaker necessity:** STACK.md recommends pybreaker, but ARCHITECTURE.md's anti-pattern analysis argues circuit breakers add complexity without value for low-frequency collection (10 types, 1-6 hour intervals). Recommendation: start without pybreaker, add it only if retry storms are observed in practice. Do not pre-engineer.
- **Separate health.db vs single database:** PITFALLS.md suggests a separate SQLite file for health data to avoid write contention. ARCHITECTURE.md recommends keeping everything in one database for simplicity. Recommendation: start with one database + busy_timeout + batched writes. Split only if SQLITE_BUSY errors appear.
- **Existing tech debt resolution:** Multiple pitfalls depend on fixing CONCERNS.md issues (session isolation, _last_results threading, WAL checkpoint strategy). These fixes are prerequisites, not optional. The roadmap must account for this work in Phase 1.
- **Production database migration testing:** The 80MB park_intel.db needs migration testing before any schema changes ship. No research covered the specific migration path from current schema to new schema with collector_runs table.

## Sources

### Primary (HIGH confidence)
- [Tenacity documentation](https://tenacity.readthedocs.io/) -- retry patterns, jitter, async support
- [SQLite WAL documentation](https://www.sqlite.org/wal.html) -- concurrent write constraints, checkpoint behavior
- [Dagster asset health monitoring](https://docs.dagster.io/examples/best-practices/asset-health-monitoring) -- freshness policies, health status patterns
- [Google SRE - Data Processing Pipelines](https://sre.google/sre-book/data-processing-pipelines/) -- retry storms, pipeline reliability
- [launchd.info](https://www.launchd.info/) -- plist configuration, environment variables, permissions
- [Python Packaging User Guide](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/) -- pyproject.toml, PEP 621

### Secondary (MEDIUM confidence)
- [Monte Carlo pipeline monitoring](https://www.montecarlodata.com/blog-data-pipeline-monitoring/) -- 5 pillars of data observability
- [Airflow UI documentation](https://airflow.apache.org/docs/apache-airflow/stable/ui.html) -- dashboard patterns, task status visualization
- [Recharts GitHub](https://github.com/recharts/recharts) -- React chart components
- [structlog documentation](https://www.structlog.org/) -- structured logging patterns

### Tertiary (LOW confidence)
- pybreaker necessity -- single community source recommending circuit breakers for this use case; architecture analysis argues against it

---
*Research completed: 2026-03-31*
*Ready for roadmap: yes*
