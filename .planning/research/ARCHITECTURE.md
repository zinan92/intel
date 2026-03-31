# Architecture Patterns

**Domain:** Health monitoring, retry logic, and persistent deployment for an existing FastAPI + APScheduler data pipeline
**Researched:** 2026-03-31

## Recommended Architecture

### Overview

Add three capabilities to the existing pipeline without restructuring it:

1. **Retry with error recording** at the adapter dispatch layer
2. **Health metrics in SQLite** via a new `collector_runs` table
3. **Health dashboard API + frontend** reading from that table
4. **launchd** for persistent macOS deployment

The guiding principle: health observability is a **read path over existing execution**, not a new execution engine. The scheduler and adapter layers already exist; we instrument them rather than replace them.

### System Diagram

```
                    launchd (com.park-intel.service)
                         |
                         | KeepAlive, auto-restart
                         v
                    uvicorn main:app (port 8001)
                         |
              +----------+----------+
              |                     |
         FastAPI API         CollectorScheduler
              |               (APScheduler)
              |                     |
   +----------+------+       _run_source_type()
   |          |       |             |
health_routes ui_routes routes   For each instance:
   |                          collect_from_source()
   |                                |
   |                     retry_with_recording()  <-- NEW
   |                                |
   |                          adapter function
   |                                |
   |                          collector.collect()
   |                                |
   |                          BaseCollector.save()
   |                                |
   +----------- SQLite ------------+
               |         |
          articles   collector_runs  <-- NEW table
```

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `collector_runs` table | Persist per-run metrics (success, error, duration, counts) | Written by scheduler, read by health API |
| `retry_with_recording()` | Wrap adapter calls with tenacity retry + record outcome | Called by `_run_source_type()`, calls adapters |
| `api/health_routes.py` | New router with health dashboard endpoints | Reads `collector_runs` table, reads `_last_results` |
| Health Dashboard (frontend) | Visual display of source health, trends, anomalies | Calls health API endpoints |
| `launchd` plist | Process supervision, auto-restart, boot persistence | Launches uvicorn, writes stdout/stderr to logs |

## Where Retry Logic Hooks In

**Decision: Adapter dispatch layer, not BaseCollector or scheduler.**

Rationale:
- **Not BaseCollector** -- BaseCollector.save() handles DB writes, which are local and don't need retry. The external HTTP calls happen in collector.collect() which is called by adapters. Putting retry in BaseCollector would retry DB saves (wrong target).
- **Not scheduler level** -- `_run_source_type()` loops over multiple instances. Retrying at this level would re-run ALL instances if one fails. Too coarse.
- **Adapter dispatch is the right boundary** -- `collect_from_source()` in `sources/adapters.py` is the single chokepoint where external HTTP calls happen. It already has try/except. Wrapping this with retry targets exactly the transient HTTP failures.

### Implementation Pattern

```python
# sources/adapters.py — modified collect_from_source()

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout, OSError)),
    reraise=True,
)
def _call_adapter_with_retry(adapter: AdapterFn, record: dict) -> list[dict]:
    """Retry transient network errors only. Non-network errors fail immediately."""
    return adapter(record)


def collect_from_source(record: dict[str, Any]) -> list[dict[str, Any]]:
    adapter = get_adapter(record["source_type"])
    if adapter is None:
        return []
    try:
        return _call_adapter_with_retry(adapter, record)
    except Exception:
        logger.exception("Adapter failed after retries for %s", record.get("source_key"))
        return []
```

**Key design choices:**
- Retry only on `ConnectionError`, `Timeout`, `OSError` -- not `ValueError`, `JSONDecodeError`, or `KeyError` which indicate bugs or bad data
- 3 attempts max (1 initial + 2 retries), exponential backoff 2s/4s
- `reraise=True` so the outer try/except still catches and logs
- Tenacity 9.x is the standard Python retry library (latest 9.1.4, actively maintained)

## Where Health Metrics Are Stored

**Decision: New SQLite table `collector_runs`, not in-memory, not a separate store.**

Rationale:
- **Not in-memory (`_last_results` dict)** -- Already exists but loses history on restart. Dashboard needs trends (last 7 days of collection volume). In-memory only shows the most recent run.
- **Not a separate store (Redis, separate file)** -- Adds deployment complexity for a self-hosted tool. SQLite is already the database. One more table is zero additional infrastructure.
- **SQLite `collector_runs` table** -- Append-only log of every collection run. Cheap to query for dashboard. Natural fit with existing SQLAlchemy setup.

### Table Schema

```python
class CollectorRun(Base):
    """Immutable log of each collector execution."""
    __tablename__ = "collector_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False)     # e.g. "rss", "reddit"
    source_key: Mapped[str | None] = mapped_column(String)               # e.g. "rss-techcrunch"
    status: Mapped[str] = mapped_column(String, nullable=False)          # "success", "partial", "error"
    articles_fetched: Mapped[int] = mapped_column(Integer, default=0)
    articles_saved: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_collector_runs_type_time", "source_type", "completed_at"),
        Index("idx_collector_runs_status", "status"),
    )
```

**Key design choices:**
- Append-only (immutable records, never updated)
- `source_key` nullable because some runs are type-level (when the scheduler runs all instances of a type)
- `retry_count` tracks how many retries occurred before success/failure
- Indexed on `(source_type, completed_at)` for dashboard time-range queries
- `status` is an enum-like string: "success" / "partial" (some instances failed) / "error" (all failed)

### Recording integration point

Recording happens in `_run_source_type()` in `scheduler.py`, which already tracks per-run results. The change: after computing `CollectorResult`, also INSERT a `CollectorRun` row. This keeps `_last_results` in-memory dict for the existing `/api/health` endpoint (backward compatible) while adding persistent history.

### Retention

A scheduled cleanup job (weekly) deletes `collector_runs` rows older than 30 days. At ~10 source types x ~6 runs/day = ~60 rows/day = ~1,800 rows/month. Negligible for SQLite.

## How the Dashboard Queries Health Data

**Decision: New `api/health_routes.py` router with dedicated endpoints.**

The existing `/api/health` endpoint returns a simple status check. The dashboard needs richer queries. Rather than overloading the existing endpoint, add a new router.

### New API Endpoints

| Endpoint | Purpose | Query Pattern |
|----------|---------|---------------|
| `GET /api/health/sources` | Per-source current status with last run info | JOIN `collector_runs` (latest per type) + `source_registry` (active sources) + `articles` (freshness) |
| `GET /api/health/history?source_type=rss&days=7` | Time-series of collection runs for trend charts | SELECT from `collector_runs` WHERE source_type=? AND completed_at >= ? |
| `GET /api/health/errors?days=3` | Recent failures with error messages | SELECT from `collector_runs` WHERE status IN ('error','partial') ORDER BY completed_at DESC |
| `GET /api/health/summary` | Aggregate dashboard stats (success rate, total articles, uptime) | Aggregate queries on `collector_runs` |

### Response Shapes

```python
# GET /api/health/sources
{
    "sources": [
        {
            "source_type": "rss",
            "display_name": "RSS Feeds",
            "status": "ok",              # ok / stale / error / no_data
            "last_run_at": "2026-03-31T10:00:00Z",
            "last_run_status": "success",
            "articles_last_24h": 42,
            "last_article_at": "2026-03-31T09:45:00Z",
            "age_hours": 0.3,
            "success_rate_7d": 0.95,      # from collector_runs
            "avg_articles_per_run": 12.5,
            "is_active": true
        }
    ]
}

# GET /api/health/history?source_type=rss&days=7
{
    "source_type": "rss",
    "runs": [
        {
            "started_at": "...",
            "status": "success",
            "articles_fetched": 15,
            "articles_saved": 8,
            "duration_seconds": 3.2,
            "retry_count": 0
        }
    ]
}
```

### Frontend Dashboard Components

The health dashboard is a new page in the existing React frontend:

| Component | Data Source | What It Shows |
|-----------|------------|---------------|
| SourceStatusGrid | `/api/health/sources` | Card per source with color-coded status (green/yellow/red) |
| CollectionTimeline | `/api/health/history` | Sparkline chart per source showing volume over time |
| ErrorLog | `/api/health/errors` | Scrollable list of recent failures with error messages |
| OverallBanner | `/api/health/summary` | Top-level "all systems nominal" / "3 sources degraded" |

Use TanStack Query (already in the frontend) with 60-second polling interval. No WebSocket needed -- health data is low-frequency.

## How launchd Integrates

**Decision: User-level LaunchAgent, not system-level LaunchDaemon.**

Rationale: park-intel runs as a user tool, not a system service. User-level agents start at login, don't need root, and have access to user environment (`.env` file, data directory).

### Plist Location and Structure

```
~/Library/LaunchAgents/com.park-intel.service.plist
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.park-intel.service</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/.venv/bin/python</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>main:app</string>
        <string>--host</string>
        <string>127.0.0.1</string>
        <string>--port</string>
        <string>8001</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/wendy/work/trading-co/park-intel</string>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/wendy/work/trading-co/park-intel/logs/launchd-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/wendy/work/trading-co/park-intel/logs/launchd-stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONDONTWRITEBYTECODE</key>
        <string>1</string>
    </dict>
</dict>
</plist>
```

### Integration with existing startup flow

The existing flow: `python main.py` -> uvicorn -> FastAPI lifespan -> `init_db()` + `CollectorScheduler.start()`.

With launchd, the flow becomes: `launchd` -> `.venv/bin/python -m uvicorn main:app` -> same FastAPI lifespan. Nothing changes in the application code. The lifespan handler already handles DB init and scheduler startup/shutdown.

**Key considerations:**
- launchd does NOT source `.bashrc` or `.zshrc`. Environment variables from `.env` are loaded by `python-dotenv` in `config.py`, so this is already handled.
- `KeepAlive: true` means launchd restarts the process if it crashes. Combined with the existing `try/except` in collectors, this provides two-layer resilience: application-level retry (tenacity) for transient errors, process-level restart (launchd) for crashes.
- `--reload` flag must NOT be used in the launchd config (it's for development only).
- Use `127.0.0.1` not `0.0.0.0` since this is a personal tool.

### Management commands (for README/docs)

```bash
# Install
cp deployment/com.park-intel.service.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.park-intel.service.plist

# Start/stop
launchctl start com.park-intel.service
launchctl stop com.park-intel.service

# Uninstall
launchctl unload ~/Library/LaunchAgents/com.park-intel.service.plist

# Check status
launchctl list | grep park-intel

# View logs
tail -f logs/launchd-stdout.log
tail -f logs/launchd-stderr.log
```

## Patterns to Follow

### Pattern 1: Record-then-Report
**What:** Every collector execution writes an immutable `CollectorRun` record. The dashboard only reads these records -- it never computes health status from raw article data alone.
**When:** Any time health status needs to be derived from operational history.
**Why:** Decouples "what happened" (recording) from "how do we display it" (dashboard). The dashboard can be redesigned without touching the scheduler.

### Pattern 2: Decorator-Based Retry
**What:** Use tenacity's `@retry` decorator on the adapter dispatch function, not inline try/except/sleep loops.
**When:** External HTTP calls that can fail transiently.
**Why:** Keeps retry policy declarative and separate from business logic. Easy to adjust parameters without changing call sites.

### Pattern 3: Backward-Compatible Extension
**What:** Keep the existing `/api/health` endpoint unchanged. Add new `/api/health/*` endpoints alongside it.
**When:** Adding monitoring to a system that already has consumers (the existing frontend).
**Why:** Existing frontend code continues working. New dashboard pages use new endpoints. No breaking changes.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Circuit Breaker Overkill
**What:** Implementing a full circuit breaker state machine (open/half-open/closed) for this use case.
**Why bad:** Circuit breakers are for protecting downstream services from being overwhelmed by a flood of requests. Park-intel collectors run every 1-6 hours with ~10 source types. The request volume is too low for circuit breakers to provide value. They add complexity (state management, half-open probing) with no benefit.
**Instead:** Simple retry with backoff + error recording. If a source fails 3 times, it is logged as "error" status. The dashboard shows it. A human investigates. For a personal tool with low-frequency scheduled collection, this is the right granularity.

### Anti-Pattern 2: Health Metrics in a Separate Database
**What:** Using Redis, InfluxDB, or a separate SQLite file for health metrics.
**Why bad:** Adds deployment complexity for a self-hosted tool. Users need to install and manage an additional service. The data volume (60 rows/day) does not justify a time-series database.
**Instead:** One more table in the existing `park_intel.db`. Same backups, same migrations, same tooling.

### Anti-Pattern 3: Retry Inside BaseCollector.save()
**What:** Adding retry logic to the article save loop in BaseCollector.
**Why bad:** `save()` writes to local SQLite. SQLite errors are either constraint violations (expected, handled by IntegrityError catch) or disk/corruption issues (not transient, retry won't help). Retrying DB writes adds latency with no benefit.
**Instead:** Retry only at the external HTTP boundary (adapter layer).

### Anti-Pattern 4: WebSocket for Health Dashboard
**What:** Using WebSocket to push real-time health updates to the dashboard.
**Why bad:** Health data changes every 1-6 hours (collection interval). WebSocket adds complexity (connection management, reconnection logic) for data that updates infrequently.
**Instead:** TanStack Query polling every 60 seconds. Simple, already in the frontend stack, works with existing REST pattern.

## Build Order (Dependencies)

The components have clear dependencies that dictate build order:

```
Phase 1: Foundation (no dependencies)
  1a. CollectorRun model + migration     -- no deps, just a new table
  1b. tenacity retry wrapper             -- no deps, wraps existing adapter function
  
Phase 2: Recording (depends on 1a)
  2a. Modify _run_source_type() to write CollectorRun rows
  2b. Retention cleanup job
  
Phase 3: API (depends on 1a, 2a)
  3a. health_routes.py endpoints         -- reads collector_runs table
  3b. Extend existing /api/health        -- add success_rate from collector_runs
  
Phase 4: Frontend (depends on 3a)
  4a. Health dashboard page              -- calls health API
  4b. Source status cards + error log
  4c. Collection trend sparklines
  
Phase 5: Deployment (independent, can parallel with Phase 3-4)
  5a. launchd plist generation script
  5b. Management commands in Makefile/scripts
  5c. README documentation
```

**Why this order:**
- Phase 1 has no dependencies and enables everything else
- Phase 2 must exist before Phase 3 (API needs data to query)
- Phase 3 must exist before Phase 4 (frontend needs endpoints)
- Phase 5 is independent -- launchd wraps the existing process, no code changes needed. Can be done in parallel with dashboard work.

## Scalability Considerations

| Concern | Current (personal tool) | If multi-instance | Notes |
|---------|------------------------|-------------------|-------|
| collector_runs volume | ~60 rows/day, 30-day retention | Same per instance | SQLite handles this trivially |
| Dashboard query load | 1 user polling every 60s | N/A (single-user tool) | Not a concern |
| SQLite write contention | WAL mode enabled, scheduler writes sequentially | Would need Postgres | Current architecture is correct for single-user |
| Retry thundering herd | 3 retries x 10 types max | N/A | Staggered scheduler start already prevents bunching |

## Sources

- [Tenacity documentation](https://tenacity.readthedocs.io/en/stable/) -- Python retry library (v9.1.4, Feb 2026)
- [Tenacity GitHub](https://github.com/jd/tenacity) -- Source, changelog, examples
- [launchd.info](https://www.launchd.info/) -- Comprehensive launchd reference
- [macOS LaunchAgent guide](https://andypi.co.uk/2023/02/14/how-to-run-a-python-script-as-a-service-on-mac-os/) -- Python service on macOS
- [Uvicorn deployment](https://www.uvicorn.org/) -- Production deployment patterns
- Existing codebase: `scheduler.py`, `sources/adapters.py`, `collectors/base.py`, `api/routes.py`, `db/models.py`

---

*Architecture analysis: 2026-03-31*
