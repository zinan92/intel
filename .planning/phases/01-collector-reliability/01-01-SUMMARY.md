---
phase: 01-collector-reliability
plan: 01
subsystem: database
tags: [sqlalchemy, tenacity, error-handling, dataclass, sqlite]

requires: []
provides:
  - ErrorCategory enum with 4-way error classification
  - categorize_error() and is_retryable() for retry decisions
  - CollectorResult frozen dataclass for execution recording
  - CollectorRun SQLAlchemy model for persistent run logging
  - Idempotent migration for collector_runs table
affects: [01-collector-reliability plan 02, phase-02 health dashboard]

tech-stack:
  added: [tenacity>=9.0]
  patterns: [error-category-enum, frozen-dataclass-result, idempotent-migration]

key-files:
  created:
    - sources/errors.py
    - tests/test_error_categorization.py
    - tests/test_collector_run_model.py
  modified:
    - db/models.py
    - db/migrations.py
    - db/database.py
    - requirements.txt

key-decisions:
  - "FileNotFoundError check ordered before OSError check (subclass relationship)"
  - "CollectorResult in sources/errors.py coexists with scheduler.py CollectorResult (different purpose)"
  - "busy_timeout already at 30s (6x the 5000ms requirement) -- documented, not changed"

patterns-established:
  - "Error categorization: categorize_error() classifies any exception into 4 categories"
  - "Retryability predicate: is_retryable() wraps categorize_error() for tenacity integration"
  - "CollectorRun append-only log: every execution attempt gets a row"

requirements-completed: [RELY-01, RELY-02, RELY-03, RELY-06]

duration: 5min
completed: 2026-03-31
---

# Phase 01 Plan 01: Error Types and Collector Run Model Summary

**ErrorCategory 4-way enum, categorize_error/is_retryable functions, CollectorResult dataclass, and CollectorRun persistent model with idempotent migration**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-31T10:37:23Z
- **Completed:** 2026-03-31T10:42:05Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- ErrorCategory enum (transient/auth/parse/config) with categorize_error() covering all exception types per D-05/D-06/D-09/D-10
- CollectorRun SQLAlchemy model with all D-12 fields and D-13 composite index
- 32 new tests passing (27 error categorization + 5 model/migration)
- tenacity>=9.0 added to requirements.txt for Plan 02 retry wiring

## Task Commits

Each task was committed atomically:

1. **Task 1: Error categorization and CollectorResult** (TDD)
   - `e4b91da` test(01-01): add failing tests for error categorization
   - `494145b` feat(01-01): implement error categorization and CollectorResult
2. **Task 2: CollectorRun model, migration, busy_timeout** (TDD)
   - `44d19e6` test(01-01): add failing tests for CollectorRun model and migration
   - `36e9fab` feat(01-01): add CollectorRun model, migration, and busy_timeout docs

## Files Created/Modified
- `sources/errors.py` - ErrorCategory enum, categorize_error(), is_retryable(), CollectorResult dataclass
- `db/models.py` - CollectorRun SQLAlchemy model with D-12 fields and D-13 index
- `db/migrations.py` - Idempotent collector_runs table creation
- `db/database.py` - RELY-03 busy_timeout documentation comment
- `requirements.txt` - tenacity>=9.0 added
- `tests/test_error_categorization.py` - 27 tests for error classification
- `tests/test_collector_run_model.py` - 5 tests for model persistence, migration, index

## Decisions Made
- FileNotFoundError isinstance check placed before OSError check because FileNotFoundError is a subclass of OSError -- without this ordering, file-not-found would be classified as transient instead of config
- CollectorResult in sources/errors.py coexists with the existing scheduler.py CollectorResult -- they serve different purposes (DB persistence vs in-memory scheduler tracking)
- busy_timeout already set to 30s (30000ms), which exceeds the RELY-03 requirement of 5000ms by 6x -- documented with comment, no code change needed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed FileNotFoundError classification ordering**
- **Found during:** Task 1 (error categorization implementation)
- **Issue:** FileNotFoundError inherits from OSError, so the OSError isinstance check caught it first, classifying it as TRANSIENT instead of CONFIG
- **Fix:** Moved CONFIG isinstance check (ImportError, FileNotFoundError) before the OSError check
- **Files modified:** sources/errors.py
- **Verification:** test_file_not_found passes, asserting ErrorCategory.CONFIG
- **Committed in:** 494145b (part of Task 1 feat commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary fix for correct error classification. No scope creep.

## Issues Encountered
- Pre-existing test failure in tests/test_source_registry_model.py::TestSourceRegistryMigration::test_migration_creates_table (ALTER TABLE events on non-existent table) -- verified this failure exists without our changes, not a regression

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Error types and model are ready for Plan 02 to wire retry decorator and recording
- sources/errors.py exports are the exact interface Plan 02 needs: is_retryable for tenacity, CollectorResult for recording, categorize_error for error metadata
- CollectorRun model ready for Plan 02 to persist execution outcomes

---
*Phase: 01-collector-reliability*
*Completed: 2026-03-31*
