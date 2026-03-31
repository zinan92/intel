---
phase: 01-collector-reliability
verified: 2026-03-31T11:10:00Z
status: passed
score: 17/17 must-haves verified
re_verification: false
---

# Phase 01: Collector Reliability Verification Report

**Phase Goal:** Collectors stop silently failing. Every run is recorded. Transient errors retry automatically.
**Verified:** 2026-03-31T11:10:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth                                                                               | Status     | Evidence                                                                  |
|----|-------------------------------------------------------------------------------------|------------|---------------------------------------------------------------------------|
| 1  | ErrorCategory enum defines exactly 4 values: transient, auth, parse, config        | VERIFIED   | `sources/errors.py` lines 19-25; test `test_has_exactly_four_values` PASS |
| 2  | categorize_error() classifies ConnectionError/Timeout as transient                 | VERIFIED   | `sources/errors.py` line 45; tests `test_connection_error`, `test_timeout` PASS |
| 3  | categorize_error() classifies HTTP 401/403 as auth                                 | VERIFIED   | `sources/errors.py` line 29 `_AUTH_HTTP_CODES`; tests `test_http_401`, `test_http_403` PASS |
| 4  | categorize_error() classifies HTTP 400 as auth (Xueqiu cookie expiry per D-09)     | VERIFIED   | `_AUTH_HTTP_CODES = frozenset({400, 401, 403})`; test `test_http_400_xueqiu_cookie` PASS |
| 5  | categorize_error() classifies ValueError/KeyError as parse                         | VERIFIED   | `sources/errors.py` line 70; tests `test_value_error`, `test_key_error` PASS |
| 6  | is_retryable() returns True only for transient errors                               | VERIFIED   | `sources/errors.py` line 78-79; tests `TestIsRetryable` 4/4 PASS         |
| 7  | CollectorRun model has all required columns per D-12                               | VERIFIED   | `db/models.py` lines 70-92; 11 mapped columns present                    |
| 8  | collector_runs table has index on (source_type, completed_at) per D-13             | VERIFIED   | `db/models.py` line 88 `idx_collector_runs_type_time`; `test_index_exists` PASS |
| 9  | Migration creates collector_runs table idempotently                                 | VERIFIED   | `db/migrations.py` lines 119-123; `test_run_migrations_twice_no_error` PASS |
| 10 | SQLite busy_timeout is 30s (exceeds 5000ms requirement)                            | VERIFIED   | `db/database.py` line 32 `"timeout": 30` with RELY-03 comment; `test_busy_timeout_documented` PASS |
| 11 | Transient errors retry up to 3 times with exponential backoff                      | VERIFIED   | `sources/adapters.py` lines 206-214 `@retry(stop=stop_after_attempt(3))`; tests `TestTransientRetry` 4/4 PASS |
| 12 | Non-transient errors fail immediately without retry                                 | VERIFIED   | `retry_if_exception(is_retryable)` only retries TRANSIENT; tests `TestNonTransientNoRetry` 2/2 PASS |
| 13 | Every successful collection writes a CollectorRun row with status=ok               | VERIFIED   | `scheduler.py` line 153 `_record_collector_run(adapter_result, saved_count=saved)`; `test_success_result_persisted` PASS |
| 14 | Every failed collection writes a CollectorRun row with status=error, error metadata | VERIFIED   | `scheduler.py` lines 154-172 fallback recording; `test_error_result_persisted` PASS |
| 15 | Existing collect_from_source() callers still work (tuple return)                   | VERIFIED   | `scheduler.py` line 143 `articles, adapter_result = collect_from_source(record)` |
| 16 | _last_results dict is still updated for backward compatibility                     | VERIFIED   | `scheduler.py` line 185 `_last_results[source_type] = result`            |
| 17 | 30-day cleanup job is registered in the scheduler                                  | VERIFIED   | `scheduler.py` lines 365-373 `add_job(_cleanup_old_runs, trigger=IntervalTrigger(weeks=1))`; `test_old_rows_deleted_recent_kept` PASS |

**Score:** 17/17 truths verified

---

### Required Artifacts

| Artifact                               | Expected                                    | Status     | Details                                            |
|----------------------------------------|---------------------------------------------|------------|----------------------------------------------------|
| `sources/errors.py`                    | ErrorCategory, categorize_error, is_retryable, CollectorResult | VERIFIED | 99 lines, all exports present, fully wired into adapters.py |
| `db/models.py`                         | CollectorRun SQLAlchemy model               | VERIFIED   | Lines 70-92, all D-12 fields and D-13 index        |
| `db/migrations.py`                     | collector_runs table creation               | VERIFIED   | Lines 118-123, idempotent via `_table_exists` guard |
| `tests/test_error_categorization.py`   | Unit tests for error classification         | VERIFIED   | 185 lines, 27 tests, all PASS                      |
| `tests/test_collector_run_model.py`    | Unit tests for CollectorRun persistence     | VERIFIED   | 133 lines, 5 tests, all PASS                       |
| `sources/adapters.py`                  | Retry-wrapped collection with CollectorResult | VERIFIED | `_call_adapter_with_retry` present, tenacity wired |
| `scheduler.py`                         | CollectorRun DB recording in _run_source_type | VERIFIED | `CollectorRun` imported locally, `_record_collector_run` defined |
| `tests/test_retry_integration.py`      | Tests for retry behavior                    | VERIFIED   | 200 lines, 8 tests, all PASS                       |
| `tests/test_collector_run_recording.py`| Tests for CollectorRun DB persistence       | VERIFIED   | 137 lines, 3 tests, all PASS                       |

---

### Key Link Verification

| From                 | To                  | Via                                          | Status  | Details                                                  |
|----------------------|---------------------|----------------------------------------------|---------|----------------------------------------------------------|
| `sources/errors.py`  | `sources/adapters.py` | `is_retryable` used as tenacity predicate  | WIRED   | `adapters.py` line 18 `from sources.errors import ... is_retryable`; line 209 `retry_if_exception(is_retryable)` |
| `db/models.py`       | `db/migrations.py`  | `CollectorRun.__table__.create(engine)`      | WIRED   | `migrations.py` lines 121-122                            |
| `db/database.py`     | `db/models.py`      | `import models` to register with Base.metadata | WIRED | `database.py` line 8 `from db.models import Base`; CollectorRun in same module |
| `sources/adapters.py`| `sources/errors.py` | `from sources.errors import ... is_retryable` | WIRED | `adapters.py` line 18, pattern confirmed                 |
| `sources/adapters.py`| tenacity            | `@retry` decorator on `_call_adapter_with_retry` | WIRED | `adapters.py` lines 16, 206-211                         |
| `scheduler.py`       | `db/models.py`      | `from db.models import CollectorRun`         | WIRED   | `scheduler.py` lines 58-59 in `_record_collector_run`   |
| `scheduler.py`       | `sources/adapters.py` | `collect_from_source` returns tuple        | WIRED   | `scheduler.py` line 143 `articles, adapter_result = collect_from_source(record)` |

---

### Requirements Coverage

| Requirement | Source Plan | Description                                                                 | Status    | Evidence                                        |
|-------------|-------------|-----------------------------------------------------------------------------|-----------|-------------------------------------------------|
| RELY-01     | 01-01       | CollectorRun model persists every execution                                 | SATISFIED | `db/models.py` CollectorRun with all D-12 fields |
| RELY-02     | 01-01       | Idempotent migration adds collector_runs table                              | SATISFIED | `db/migrations.py` lines 118-123 with `_table_exists` guard |
| RELY-03     | 01-01       | SQLite busy_timeout verified/set to 5000ms                                  | SATISFIED | `db/database.py` line 32 `timeout=30` (30000ms >> 5000ms) |
| RELY-04     | 01-02       | Transient failures retry with exponential backoff + jitter (3 attempts)     | SATISFIED | `sources/adapters.py` tenacity decorator with `stop_after_attempt(3)`, `wait_exponential_jitter` |
| RELY-05     | 01-02       | Non-transient failures are NOT retried                                      | SATISFIED | `retry_if_exception(is_retryable)` — only TRANSIENT category retries |
| RELY-06     | 01-01       | Errors categorized into 4 types: transient, auth, parse, config             | SATISFIED | `ErrorCategory` enum in `sources/errors.py` |
| RELY-07     | 01-02       | Every collection attempt (success or failure) writes a CollectorRun row     | SATISFIED | `scheduler.py` `_record_collector_run` called on success (line 153) and failure (line 172) |

**All 7 requirements for Phase 01 satisfied. No orphaned requirements.**

---

### Anti-Patterns Found

No anti-patterns detected in phase artifacts. No TODOs, FIXMEs, stubs, or placeholder implementations found across `sources/errors.py`, `db/models.py`, `db/migrations.py`, `db/database.py`, `sources/adapters.py`, and `scheduler.py`.

---

### Test Suite Summary

```
43 tests collected
43 passed
0 failed
2 deprecation warnings (datetime.utcnow() in test helpers — not in production code)
Runtime: 0.26s
```

---

### Human Verification Required

None. All aspects of this phase are verifiable programmatically:
- Error classification is deterministic and fully covered by unit tests
- DB persistence is verified via in-memory SQLite integration tests
- Retry behavior is verified via mocked adapter tests
- Cleanup job is registered in the scheduler (verified by code inspection and test)

---

### Notes

1. **FileNotFoundError ordering** — `categorize_error()` correctly places the `FileNotFoundError` check before the `OSError` check (line 62 before line 66) to prevent the subclass from being misclassified as TRANSIENT. This was an auto-fixed bug during Plan 01 execution.

2. **Two CollectorResult dataclasses coexist** — `sources/errors.py:CollectorResult` (richer, for DB persistence) and `scheduler.py:CollectorResult` (simpler, for `_last_results` backward compat). They are distinct and non-conflicting.

3. **Pre-existing test failure not caused by this phase** — `tests/test_source_registry_model.py::test_migration_creates_table` fails due to an ALTER TABLE on a non-existent `events` table. This failure predates Phase 01 and is not a regression.

---

_Verified: 2026-03-31T11:10:00Z_
_Verifier: Claude (gsd-verifier)_
