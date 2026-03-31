---
phase: 02-health-visibility
plan: 01
subsystem: api
tags: [fastapi, health-check, freshness, heartbeat, volume-anomaly, sqlite-migration]

# Dependency graph
requires:
  - phase: 01-collector-reliability
    provides: CollectorRun model and run recording in scheduler
provides:
  - "GET /api/health/sources with per-source status, freshness, volume anomaly, disabled reason"
  - "GET /api/health/summary with aggregate health counts"
  - "expected_freshness_hours column on SourceRegistry with migration and default seeding"
  - "Scheduler heartbeat (5min interval) queryable via get_heartbeat()"
  - "Boot logging of active/skipped sources on startup"
  - "compute_status, compute_volume_anomaly, _check_source_disabled pure functions"
affects: [02-health-visibility plan 02 (frontend), future monitoring/alerting]

# Tech tracking
tech-stack:
  added: []
  patterns: [per-source freshness policy via DB column, heartbeat pattern for scheduler liveness, volume anomaly detection with 50% threshold and 3-day minimum baseline]

key-files:
  created:
    - api/health_routes.py
    - tests/test_health_api.py
  modified:
    - db/models.py
    - db/migrations.py
    - scheduler.py
    - main.py

key-decisions:
  - "Disabled check takes priority over error status - a source missing its env var shows as disabled, not error"
  - "Volume anomaly requires minimum 3 days of data before flagging"
  - "SQLite naive datetimes treated as UTC when computing freshness age"
  - "Freshness defaults seeded during migration even if column already exists (idempotent NULL check)"

patterns-established:
  - "Health computation as pure functions (compute_status, compute_volume_anomaly) separate from endpoints"
  - "get_session() wrapper in route modules for clean test patching"
  - "StaticPool for in-memory SQLite test databases shared across connections"

requirements-completed: [HLTH-01, HLTH-02, HLTH-03, HLTH-04, HLTH-05, HLTH-08, HLTH-09]

# Metrics
duration: 9min
completed: 2026-03-31
---

# Phase 02 Plan 01: Health Backend API Summary

**Per-source health endpoints with freshness policy, volume anomaly detection, scheduler heartbeat, and disabled source reasoning**

## Performance

- **Duration:** 9 min
- **Started:** 2026-03-31T13:40:14Z
- **Completed:** 2026-03-31T13:49:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Two new health endpoints: /api/health/sources (per-source detail) and /api/health/summary (aggregate)
- Per-source freshness uses expected_freshness_hours from DB (not hardcoded 24h), with migration seeding sensible defaults per source type
- Scheduler heartbeat updated every 5 minutes, reported as alive/dead in both endpoints
- Volume anomaly flagged when 24h count drops below 50% of 7-day average, with None for insufficient data
- Disabled sources include human-readable reason with enable instructions
- Boot logging shows active/skipped sources with reasons on scheduler startup
- 28 tests covering all status transitions, volume anomaly, disabled detection, heartbeat, migration, and endpoint integration

## Task Commits

Each task was committed atomically:

1. **Task 1: Migration, heartbeat, boot logging, and health computation logic** - `09c8cca` (feat)
2. **Task 2: Health API endpoints and router registration** - `61ed12a` (feat)

## Files Created/Modified
- `api/health_routes.py` - Health router with /sources and /summary endpoints, compute_status, volume anomaly, disabled detection
- `db/models.py` - Added expected_freshness_hours column to SourceRegistry
- `db/migrations.py` - Migration for expected_freshness_hours + default seeding by source type
- `scheduler.py` - Heartbeat (5min), get_heartbeat(), boot logging of active/skipped sources
- `main.py` - health_router registration
- `tests/test_health_api.py` - 28 tests: unit (compute_status, volume anomaly, disabled, heartbeat, migration) + integration (endpoints, backward compat)

## Decisions Made
- Disabled check takes priority over error status: a source missing its required env var shows as "disabled" with instructions, not "error"
- Volume anomaly requires minimum 3 days of data before flagging (avoids false positives for new sources)
- SQLite naive datetimes treated as UTC when computing freshness age (consistent with how they're stored)
- Migration seeds freshness defaults via idempotent NULL check, even if column already exists (handles both fresh installs and upgrades)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed naive/aware datetime comparison**
- **Found during:** Task 2 (endpoint implementation)
- **Issue:** SQLite returns timezone-naive datetimes, but freshness computation uses timezone-aware UTC now
- **Fix:** Added .replace(tzinfo=timezone.utc) for naive datetimes before subtraction
- **Files modified:** api/health_routes.py
- **Verification:** All endpoint tests pass with correct freshness_age_hours values
- **Committed in:** 61ed12a (Task 2 commit)

**2. [Rule 1 - Bug] Fixed migration seeding when column already exists**
- **Found during:** Task 1 (migration tests)
- **Issue:** When Base.metadata.create_all creates the column (fresh install), migration skipped seeding defaults because column already existed
- **Fix:** Separated column creation check from default seeding - seeding always runs with NULL check
- **Files modified:** db/migrations.py
- **Verification:** Migration test confirms defaults seeded correctly
- **Committed in:** 09c8cca (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both fixes necessary for correctness. No scope creep.

## Issues Encountered
- Pre-existing test failure in test_source_registry_model.py::test_migration_creates_table (events table ALTER before CREATE) - confirmed pre-existing, not caused by this plan's changes

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Health backend API complete, ready for frontend health dashboard (Plan 02)
- Endpoints can be tested via curl independently
- Existing /api/health endpoint unchanged (backward compatible)

---
*Phase: 02-health-visibility*
*Completed: 2026-03-31*
