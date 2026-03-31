# Phase 1: Collector Reliability - Research

**Researched:** 2026-03-31
**Domain:** Python retry/resilience patterns, SQLAlchemy model additions, SQLite concurrency, error categorization
**Confidence:** HIGH

## Summary

Phase 1 adds reliability instrumentation to the existing collector pipeline. The core change is wrapping `sources/adapters.py:collect_from_source()` with tenacity retry for transient errors, recording every execution to a new `collector_runs` table, and categorizing errors into 4 types (transient, auth, parse, config). The codebase already has clean boundaries: adapters.py line 216-220 is the exact silent failure point, and the scheduler's `_run_source_type()` is the natural recording integration point.

Key findings: (1) SQLite busy_timeout is already set to 30 seconds via `connect_args={"timeout": 30}` in database.py, exceeding the RELY-03 requirement of 5000ms -- just needs verification/documentation, not a code change. (2) tenacity is not currently installed but is the de facto Python retry standard. (3) The existing `CollectorResult` dataclass in scheduler.py is in-memory only and needs to be extended or supplemented with a persistent `CollectorRun` model. (4) HTTP status codes from `requests.HTTPError.response.status_code` are available for error categorization since collectors call `raise_for_status()`.

**Primary recommendation:** Install tenacity 9.x, add CollectorRun model + migration, wrap adapter dispatch with retry decorator, and record outcomes in `_run_source_type()`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Keep the `collect_from_source()` return-list interface unchanged
- **D-02:** Wrap `collect_from_source()` in adapters.py with tenacity retry decorator at the adapter dispatch layer
- **D-03:** Add a CollectorResult dataclass alongside the return value to carry error metadata (status, error_message, error_category, retry_count, duration_ms)
- **D-04:** Scheduler records CollectorResult to collector_runs table after each execution
- **D-05:** Retry only transient errors: ConnectionError, Timeout, OSError, HTTP 429/500/502/503
- **D-06:** Do NOT retry: HTTP 401/403 (auth), JSON parse errors, missing config/env vars
- **D-07:** 3 attempts max, exponential backoff 2s base with full jitter (tenacity)
- **D-08:** All source types use the same retry policy (no per-source config for v1)
- **D-09:** Xueqiu cookie expiry (400 response) classified as "auth" error, not retried
- **D-10:** Four categories: transient, auth, parse, config
- **D-11:** Category stored as string enum in CollectorRun row
- **D-12:** Append-only table: source_type, source_key, status (ok/error), articles_fetched, articles_saved, duration_ms, error_message, error_category, retry_count, completed_at
- **D-13:** Indexed on (source_type, completed_at) for health API queries in Phase 2
- **D-14:** 30-day retention with weekly cleanup job (APScheduler, low priority)
- **D-15:** ~60 rows/day = ~1800/month, negligible storage impact
- **D-16:** Verify busy_timeout is set; set to 5000ms if not
- **D-17:** Verify session-per-call pattern is correct
- **D-18:** No separate health.db for v1

### Claude's Discretion
- Migration implementation (idempotent ALTER TABLE / CREATE TABLE IF NOT EXISTS)
- CollectorResult dataclass exact fields and typing
- How retry decorator integrates with existing scheduler._run_source_type()
- Test structure and coverage approach
- Logging format (keep existing logging module for v1, structlog deferred to v2)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RELY-01 | CollectorRun model persists every collection execution | CollectorRun SQLAlchemy model pattern documented below; follows existing model conventions in db/models.py |
| RELY-02 | Idempotent migration adds collector_runs table | Existing migration pattern in db/migrations.py uses `_table_exists()` check; follow same pattern |
| RELY-03 | SQLite busy_timeout verified/set to 5000ms | Already set to 30s via `connect_args={"timeout": 30}` in database.py; exceeds requirement |
| RELY-04 | Transient failures retry with exponential backoff and jitter | tenacity `@retry` with `retry_if_exception_type` + custom predicate for HTTP status codes |
| RELY-05 | Non-transient failures NOT retried | Error categorization function classifies before retry; tenacity `retry_if_exception` with custom callable |
| RELY-06 | Errors categorized into 4 types | `categorize_error()` function maps exception types + HTTP codes to categories |
| RELY-07 | Every collection attempt writes a CollectorRun row | Recording in `_run_source_type()` after each `collect_from_source()` call |
</phase_requirements>

## Standard Stack

### Core (New for Phase 1)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| tenacity | 9.x (latest) | Retry with exponential backoff + jitter | De facto Python retry library, 170M+ monthly PyPI downloads, decorator API, supports `retry_if_exception_type` and `wait_exponential_jitter` |

### Existing (No Changes)

| Library | Version | Purpose |
|---------|---------|---------|
| SQLAlchemy | 2.0+ | ORM for CollectorRun model |
| APScheduler | 3.10+ | Cleanup job scheduling |
| requests | 2.31+ | HTTP client (source of retry-able exceptions) |

### Not Installing

| Library | Reason |
|---------|--------|
| pybreaker | Deferred -- add only if retry storms observed (CONTEXT.md decision) |
| structlog | Deferred to v2 -- keep existing logging module |

**Installation:**
```bash
pip install tenacity>=9.0
```

Add to `requirements.txt`:
```
tenacity>=9.0
```

## Architecture Patterns

### Modified File Structure
```
db/
  models.py           # ADD CollectorRun model
  migrations.py       # ADD collector_runs table migration
  database.py         # VERIFY busy_timeout (already 30s, document it)
sources/
  adapters.py         # MODIFY collect_from_source() with retry + result capture
  errors.py           # NEW: error categorization + CollectorResult dataclass
scheduler.py          # MODIFY _run_source_type() to write CollectorRun rows
```

### Pattern 1: Error Categorization Function
**What:** A pure function that maps exceptions to one of 4 categories (transient, auth, parse, config).
**When to use:** Called by retry predicate and by result recording.
**Example:**
```python
# sources/errors.py
from dataclasses import dataclass
from enum import Enum
import requests


class ErrorCategory(str, Enum):
    TRANSIENT = "transient"
    AUTH = "auth"
    PARSE = "parse"
    CONFIG = "config"


def categorize_error(exc: Exception) -> ErrorCategory:
    """Classify an exception into one of 4 error categories."""
    # Transient: network errors
    if isinstance(exc, (requests.ConnectionError, requests.Timeout, OSError)):
        return ErrorCategory.TRANSIENT

    # HTTP errors: check status code
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        code = exc.response.status_code
        if code in (429, 500, 502, 503):
            return ErrorCategory.TRANSIENT
        if code in (401, 403):
            return ErrorCategory.AUTH
        # Xueqiu 400 = cookie expiry (D-09)
        if code == 400:
            return ErrorCategory.AUTH

    # Parse errors
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return ErrorCategory.PARSE

    # Config errors (missing env vars, import errors)
    if isinstance(exc, (KeyError, ImportError, FileNotFoundError)):
        return ErrorCategory.CONFIG

    # Default: treat unknown as transient (will retry, then record)
    return ErrorCategory.TRANSIENT


def is_retryable(exc: Exception) -> bool:
    """Return True if this exception should trigger a retry."""
    return categorize_error(exc) == ErrorCategory.TRANSIENT
```

### Pattern 2: Tenacity Retry with Custom Predicate
**What:** Use `retry_if_exception` with a custom callable instead of `retry_if_exception_type` alone, because we need to inspect HTTP status codes.
**When to use:** Wrapping the adapter dispatch function.
**Example:**
```python
# sources/adapters.py (modified)
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception
from sources.errors import is_retryable

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=2, max=30, jitter=2),
    retry=retry_if_exception(is_retryable),
    reraise=True,
)
def _call_adapter_with_retry(adapter_fn, record: dict) -> list[dict]:
    return adapter_fn(record)
```
**Why `retry_if_exception` over `retry_if_exception_type`:** We need to check HTTP status codes on `HTTPError`, not just exception type. A custom predicate allows `is_retryable()` to inspect `exc.response.status_code`.

### Pattern 3: CollectorResult Dataclass (Extended)
**What:** Immutable dataclass carrying full execution metadata for both in-memory use and DB persistence.
**Example:**
```python
# sources/errors.py
@dataclass(frozen=True)
class CollectorResult:
    """Result of a single source instance collection attempt."""
    source_type: str
    source_key: str
    status: str  # "ok" or "error"
    articles_fetched: int
    articles_saved: int
    duration_ms: int
    error_message: str | None
    error_category: str | None  # ErrorCategory value or None
    retry_count: int
```

### Pattern 4: Recording in _run_source_type()
**What:** After each `collect_from_source()` call, create a CollectorResult and write a CollectorRun row.
**When to use:** In the per-instance loop inside `_run_source_type()`.
**Key insight:** The current code catches exceptions at the instance level (line 101-103). The retry wrapper goes inside `collect_from_source()`, so by the time the scheduler sees an exception, all retries are exhausted. The scheduler records the final outcome.

### Anti-Patterns to Avoid
- **Retry inside BaseCollector.save():** save() writes to local SQLite -- retry won't help with constraint violations or disk errors
- **Retry at scheduler level:** Too coarse -- would re-run ALL instances if one fails
- **Mutable global state for results:** Keep `_last_results` dict for backward compat, but CollectorRun table is source of truth
- **Catching too broadly in retry:** Only retry transient errors; parse/auth/config errors must fail fast

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Exponential backoff + jitter | Custom sleep loops | tenacity `wait_exponential_jitter` | Edge cases: jitter calculation, max backoff cap, attempt counting |
| Retry predicate logic | Manual try/except/retry counters | tenacity `retry_if_exception` | Clean separation of retry policy from business logic |
| Idempotent migration | Raw SQL migration scripts | Existing `_table_exists()` + `Table.create()` pattern | Already established in db/migrations.py |

## Common Pitfalls

### Pitfall 1: KeyError vs Config Error Ambiguity
**What goes wrong:** `KeyError` can mean both "missing dict key in parsed data" (parse error) and "missing env var" (config error).
**Why it happens:** Python uses KeyError for both dict access and os.environ access.
**How to avoid:** Check the exception context. If it comes from within a collector's HTTP response parsing, it's parse. If from config/env loading, it's config. In practice, config errors surface at startup (seed time), not during collection. For the categorization function, treat KeyError in the adapter layer as parse.
**Warning signs:** Auth errors being retried; config errors being retried.

### Pitfall 2: HTTPError Without Response Object
**What goes wrong:** `requests.HTTPError` can be raised without a `.response` attribute in edge cases (e.g., manually constructed).
**Why it happens:** HTTPError is sometimes raised programmatically without a response.
**How to avoid:** Always check `exc.response is not None` before accessing `.status_code`.
**Warning signs:** AttributeError in the categorization function.

### Pitfall 3: Xueqiu 400 Classification
**What goes wrong:** Xueqiu returns HTTP 400 when cookies expire, which looks like a client error, not auth.
**Why it happens:** Xueqiu's API uses 400 instead of 401/403 for expired sessions.
**How to avoid:** D-09 explicitly classifies 400 as auth. The categorization function should handle this. Note: this means ALL 400 responses from ANY source are classified as auth, which is acceptable for v1 since 400 from other sources (e.g., bad request params) is also not retryable.
**Warning signs:** 400 errors being retried in a loop.

### Pitfall 4: Retry Count Tracking
**What goes wrong:** tenacity's retry count is not automatically passed to the caller.
**Why it happens:** The `@retry` decorator is transparent -- the caller doesn't know how many retries occurred.
**How to avoid:** Use tenacity's `before_sleep` or `after` callbacks to track attempt count, or wrap the retry call in a context that captures `RetryCallState`. Alternatively, use a mutable counter in a closure or use `tenacity.statistics` attribute on the decorated function.
**Warning signs:** `retry_count` always showing 0 in CollectorRun rows.

### Pitfall 5: Migration on 80MB Production Database
**What goes wrong:** ALTER TABLE on a large SQLite database can be slow or fail if disk space is tight.
**Why it happens:** SQLite CREATE TABLE IF NOT EXISTS is fast (just metadata), but the 80MB existing DB needs care.
**How to avoid:** `CREATE TABLE IF NOT EXISTS` for the new table is safe and fast. No ALTER TABLE needed since this is a brand new table. Test migration on a copy of production DB first.
**Warning signs:** Slow startup after deployment.

## Code Examples

### CollectorRun Model
```python
# db/models.py (addition)
class CollectorRun(Base):
    """Immutable log of each collector execution attempt."""
    __tablename__ = "collector_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_key: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False)  # "ok" or "error"
    articles_fetched: Mapped[int] = mapped_column(Integer, default=0)
    articles_saved: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    error_category: Mapped[str | None] = mapped_column(String)  # transient/auth/parse/config
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_collector_runs_type_time", "source_type", "completed_at"),
    )
```

### Migration Addition
```python
# db/migrations.py (addition to run_migrations)
if not _table_exists(engine, "collector_runs"):
    logger.info("Creating collector_runs table via migration")
    from db.models import CollectorRun
    CollectorRun.__table__.create(engine)
    logger.info("collector_runs table created")
```

### Retry Integration in adapters.py
```python
# sources/adapters.py (modified collect_from_source)
import time
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception
from sources.errors import is_retryable, categorize_error, CollectorResult, ErrorCategory

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=2, max=30, jitter=2),
    retry=retry_if_exception(is_retryable),
    reraise=True,
)
def _call_adapter_with_retry(adapter_fn, record: dict) -> list[dict]:
    """Call adapter with automatic retry for transient errors."""
    return adapter_fn(record)


def collect_from_source(record: dict[str, Any]) -> tuple[list[dict[str, Any]], CollectorResult]:
    """Dispatch collection and return (articles, result) tuple.

    The return-list interface is preserved: callers can ignore the result.
    """
    source_type = record["source_type"]
    source_key = record.get("source_key", source_type)
    adapter = get_adapter(source_type)

    if adapter is None:
        logger.warning("No adapter for source type %r (key=%s)", source_type, source_key)
        return [], CollectorResult(
            source_type=source_type, source_key=source_key,
            status="error", articles_fetched=0, articles_saved=0,
            duration_ms=0, error_message=f"No adapter for {source_type}",
            error_category=ErrorCategory.CONFIG.value, retry_count=0,
        )

    start = time.monotonic()
    retry_count = 0
    try:
        articles = _call_adapter_with_retry(adapter, record)
        duration_ms = int((time.monotonic() - start) * 1000)
        # Get retry stats from tenacity
        retry_count = _call_adapter_with_retry.statistics.get("attempt_number", 1) - 1
        result = CollectorResult(
            source_type=source_type, source_key=source_key,
            status="ok", articles_fetched=len(articles), articles_saved=0,
            duration_ms=duration_ms, error_message=None,
            error_category=None, retry_count=retry_count,
        )
        return articles, result
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        category = categorize_error(exc)
        retry_count = _call_adapter_with_retry.statistics.get("attempt_number", 1) - 1
        result = CollectorResult(
            source_type=source_type, source_key=source_key,
            status="error", articles_fetched=0, articles_saved=0,
            duration_ms=duration_ms, error_message=str(exc)[:500],
            error_category=category.value, retry_count=retry_count,
        )
        logger.exception("Adapter failed for %s (type=%s, category=%s, retries=%d)",
                         source_key, source_type, category.value, retry_count)
        return [], result
```

### Tracking Retry Count via tenacity.statistics
```python
# After calling a @retry-decorated function, access:
func.statistics["attempt_number"]  # Total attempts (1 = no retry, 2 = 1 retry, etc.)
```
Note: `statistics` is a dict attribute on retry-decorated functions. It tracks the most recent call's stats. This is the cleanest way to get retry count without callbacks.

### Recording in Scheduler
```python
# scheduler.py (modified _run_source_type per-instance loop)
from db.models import CollectorRun
from datetime import datetime, timezone

# Inside the per-instance loop:
articles, result = collect_from_source(record)
# ... save articles as before ...
# Record to DB:
session = get_session()
try:
    run = CollectorRun(
        source_type=result.source_type,
        source_key=result.source_key,
        status=result.status,
        articles_fetched=result.articles_fetched,
        articles_saved=saved_count,  # from BaseCollector.save()
        duration_ms=result.duration_ms,
        error_message=result.error_message,
        error_category=result.error_category,
        retry_count=result.retry_count,
        completed_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.commit()
except Exception:
    session.rollback()
    logger.exception("Failed to record CollectorRun for %s", result.source_key)
finally:
    session.close()
```

### Retention Cleanup Job
```python
# scheduler.py (new function)
def _cleanup_old_runs() -> None:
    """Delete collector_runs older than 30 days."""
    from db.database import get_session
    from db.models import CollectorRun
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    session = get_session()
    try:
        deleted = session.query(CollectorRun).filter(
            CollectorRun.completed_at < cutoff
        ).delete()
        session.commit()
        if deleted:
            logger.info("Cleaned up %d old collector_runs rows", deleted)
    except Exception:
        session.rollback()
        logger.exception("Failed to clean up old collector_runs")
    finally:
        session.close()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual sleep/retry loops | tenacity decorator-based retry | Stable since 2020+ | Cleaner code, configurable |
| `backoff` library | `tenacity` (10x adoption) | tenacity dominant by 2023 | More features, better maintained |
| SQLite timeout as seconds | Python sqlite3 `timeout` param = busy_timeout in seconds | Always | `timeout=30` in connect_args = 30000ms busy_timeout |

## Key Existing Code Facts

### busy_timeout (RELY-03)
The current `database.py` line 32 sets `connect_args={"timeout": 30}`. Python's `sqlite3.connect(timeout=N)` maps directly to SQLite's `busy_timeout` with N in seconds. The current value of 30 seconds (30000ms) already **exceeds** the 5000ms requirement. Action: verify and document, no code change needed.

### Silent Failure Point (adapters.py:216-220)
```python
try:
    return adapter(record)
except Exception:
    logger.exception("Adapter failed for %s (type=%s)", record.get("source_key"), source_type)
    return []
```
This catches ALL exceptions, logs them, and returns `[]`. No error metadata is preserved. This is the exact code to wrap with retry + result capture.

### Existing CollectorResult (scheduler.py:23-32)
The scheduler already has a `CollectorResult` dataclass but it's in-memory only and lacks error_category, retry_count, and duration_ms granularity. Either extend it or create a new one in `sources/errors.py` (recommended: keep scheduler.py's version for backward compat with `_last_results`, create a richer one for DB recording).

### Collector HTTP Patterns
All network-calling collectors use `requests.get()` and call `resp.raise_for_status()`. This means:
- Transient errors surface as `requests.ConnectionError`, `requests.Timeout`, or `requests.HTTPError` with 5xx/429 status
- Auth errors surface as `requests.HTTPError` with 401/403 (or 400 for Xueqiu)
- Parse errors surface as `ValueError`, `KeyError`, `json.JSONDecodeError`

### Session-per-call Pattern (RELY-17)
The codebase consistently uses `session = get_session()` with try/finally/session.close() at each call site. This is correct for SQLite -- no long-lived sessions that could hold locks.

## Open Questions

1. **collect_from_source return type change**
   - What we know: D-01 says keep the return-list interface unchanged, but D-03 says add CollectorResult alongside
   - What's unclear: Whether to return `tuple[list, CollectorResult]` (breaking) or use a side channel
   - Recommendation: Return a tuple `(articles, result)` and update the single call site in `_run_source_type()`. The only caller is the scheduler, so this is a contained change. Alternatively, use a module-level variable or callback, but tuple is cleanest.

2. **tenacity.statistics thread safety**
   - What we know: `statistics` attribute is updated per-call on the decorated function object
   - What's unclear: Whether concurrent scheduler jobs could race on the same `statistics` dict
   - Recommendation: LOW risk because APScheduler runs jobs sequentially by default (thread pool size 1 for each job). But if concerned, use a `before_sleep` callback with a closure instead.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `sources/adapters.py`, `scheduler.py`, `db/models.py`, `db/migrations.py`, `db/database.py`
- [tenacity documentation](https://tenacity.readthedocs.io/en/stable/) -- retry API, `wait_exponential_jitter`, `retry_if_exception`
- [Python sqlite3 docs](https://docs.python.org/3/library/sqlite3.html) -- timeout parameter = busy_timeout

### Secondary (MEDIUM confidence)
- [tenacity GitHub](https://github.com/jd/tenacity) -- statistics attribute, version history
- [SQLite busy_timeout reference](https://sqlite.org/c3ref/busy_timeout.html) -- confirms Python timeout mapping

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- tenacity is the clear choice, already decided in CONTEXT.md
- Architecture: HIGH -- existing code boundaries are clear, integration points identified from source reading
- Pitfalls: HIGH -- based on direct code inspection of all collectors and error handling patterns
- Error categorization: MEDIUM -- Xueqiu 400 edge case needs runtime validation

**Research date:** 2026-03-31
**Valid until:** 2026-04-30 (stable domain, no fast-moving dependencies)
