---
phase: 01-collector-reliability
plan: 02
subsystem: api
tags: [tenacity, retry, exponential-backoff, collector-run, scheduler, sqlite]

requires:
  - phase: 01-collector-reliability plan 01
    provides: ErrorCategory, is_retryable, CollectorResult, CollectorRun model
provides:
  - tenacity retry wrapper on collect_from_source (3 attempts, exponential backoff + jitter)
  - CollectorRun DB recording for every collection attempt (success and failure)
  - 30-day retention cleanup job (weekly)
  - (articles, CollectorResult) tuple return from collect_from_source
affects: [02-health-dashboard, scheduler, sources/adapters]

tech-stack:
  added: [tenacity]
  patterns: [retry-with-categorization, tuple-return-with-metadata, db-recording-per-attempt]

key-files:
  created:
    - tests/test_retry_integration.py
    - tests/test_collector_run_recording.py
  modified:
    - sources/adapters.py
    - scheduler.py
    - tests/test_source_adapters.py

key-decisions:
  - "Patched tenacity.nap.time.sleep in tests to avoid real waits"
  - "duration_ms can be 0 for very fast operations (monotonic clock resolution)"
  - "Fallback error recording in scheduler even for unexpected exceptions"

patterns-established:
  - "Retry wrapper: _call_adapter_with_retry with tenacity decorator, statistics tracking for retry count"
  - "Result tuple: collect_from_source returns (articles, CollectorResult) instead of bare list"
  - "DB recording: _record_collector_run writes immutable CollectorRun rows with session-per-call"

requirements-completed: [RELY-04, RELY-05, RELY-07]

duration: 7min
completed: 2026-03-31
---

# Phase 01 Plan 02: Retry + Recording Integration Summary

**Tenacity retry on collect_from_source with 3-attempt exponential backoff, CollectorRun DB persistence for every collection attempt, and weekly 30-day cleanup job**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-31T10:44:18Z
- **Completed:** 2026-03-31T10:50:48Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- collect_from_source now retries transient errors (ConnectionError, Timeout, HTTP 429/500/502/503) up to 3 times with exponential backoff + jitter via tenacity
- Non-transient errors (HTTP 401/403, ValueError) fail immediately without retry
- Every collection attempt (success or failure) writes a CollectorRun row to the database
- Scheduler unpacks new (articles, CollectorResult) tuple; _last_results backward compat preserved
- Weekly cleanup job deletes collector_runs older than 30 days

## Task Commits

Each task was committed atomically:

1. **Task 1: Add tenacity retry wrapper to sources/adapters.py** - `ec26edf` (feat)
2. **Task 2: Wire CollectorRun recording into scheduler and add cleanup job** - `50d3d0d` (feat)

_Both tasks followed TDD: RED (failing tests) then GREEN (implementation)_

## Files Created/Modified
- `sources/adapters.py` - Added _call_adapter_with_retry with tenacity, collect_from_source returns (articles, CollectorResult) tuple
- `scheduler.py` - Added _record_collector_run, _cleanup_old_runs, updated _run_source_type to unpack tuple and record runs, registered cleanup job
- `tests/test_retry_integration.py` - 8 tests for transient retry, non-transient no-retry, success path, unknown adapter
- `tests/test_collector_run_recording.py` - 3 tests for DB persistence and cleanup
- `tests/test_source_adapters.py` - Updated existing tests to handle tuple return type

## Decisions Made
- Patched `tenacity.nap.time.sleep` in tests rather than creating separate retry instances with `wait_none()` -- simpler and tests real decorator
- duration_ms assertion relaxed to >= 0 (monotonic clock can return 0 for sub-millisecond operations)
- Added fallback error recording in scheduler's except block to capture unexpected exceptions not handled by adapters.py

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing test_source_adapters.py for tuple return**
- **Found during:** Task 1 (retry wrapper implementation)
- **Issue:** Existing tests expected collect_from_source to return a list, but it now returns (list, CollectorResult) tuple
- **Fix:** Updated TestCollectFromSource tests to unpack tuple; added tenacity.nap.time.sleep patch
- **Files modified:** tests/test_source_adapters.py
- **Verification:** All 11 existing adapter tests pass
- **Committed in:** ec26edf (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug fix for return type change)
**Impact on plan:** Planned and expected; the plan's acceptance criteria noted these tests would need updating.

## Issues Encountered
- 2 pre-existing test failures unrelated to this plan (test_source_registry_model migration issue, test_source_registry_seed schedule_hours) -- not caused by these changes

## Known Stubs
None -- all functionality is fully wired with real implementations.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 01 collector reliability is complete (Plan 01 + Plan 02)
- collector_runs table now has data for Phase 02 health dashboard queries
- Index on (source_type, completed_at) ready for health API queries

---
## Self-Check: PASSED

All files exist, all commits verified.

---
*Phase: 01-collector-reliability*
*Completed: 2026-03-31*
