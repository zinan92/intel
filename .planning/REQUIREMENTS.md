# Requirements: Park-Intel Reliability & Open-Source

**Defined:** 2026-03-31
**Core Value:** Anyone can clone, configure, and run a self-hosted market intelligence pipeline with zero-config core sources and a health dashboard that makes data freshness visible at a glance.

## v1 Requirements

### Foundation

- [ ] **FOUND-01**: CollectorRun model persists every collection execution (source_type, status, articles_fetched, articles_saved, duration_ms, error_message, retry_count)
- [ ] **FOUND-02**: Idempotent migration adds collector_runs table without breaking existing data
- [ ] **FOUND-03**: SQLite busy_timeout set to 5000ms to prevent write contention
- [ ] **FOUND-04**: Database session isolation fixed (no shared sessions across threads)

### Retry & Error Handling

- [ ] **RETRY-01**: Transient failures (timeout, connection error, rate limit) automatically retry with exponential backoff and jitter (3 attempts, 2s/4s base)
- [ ] **RETRY-02**: Non-transient failures (401/403 auth, parse errors, missing config) are NOT retried
- [ ] **RETRY-03**: Errors categorized into 4 types: transient, auth, parse, config
- [ ] **RETRY-04**: Every collection attempt (success or failure) writes a CollectorRun row
- [ ] **RETRY-05**: Exhausted retries log to dead_letters table with full context (URL, error, attempt count)
- [ ] **RETRY-06**: Structured JSON logging via structlog replaces basic logging for collector layer

### Health API

- [ ] **HLTH-01**: GET /api/health/sources returns per-source current status (ok/stale/degraded/error/disabled) with freshness age, article counts, last error
- [ ] **HLTH-02**: GET /api/health/history returns time-series data for collection volume charts (last 7/30 days)
- [ ] **HLTH-03**: GET /api/health/errors returns recent failures with error category and context
- [ ] **HLTH-04**: GET /api/health/summary returns aggregate stats (total sources, healthy count, degraded count, total articles 24h)
- [ ] **HLTH-05**: Scheduler heartbeat updates a timestamp every 5 minutes; health endpoint reports scheduler alive/dead
- [ ] **HLTH-06**: Per-source freshness policy (expected_freshness_hours column in source_registry) replaces hardcoded 24h threshold
- [ ] **HLTH-07**: Startup boot log lists active sources, skipped sources (with reason), and scheduler start time

### Dashboard

- [ ] **DASH-01**: Health dashboard page at /health shows all source statuses at a glance (color-coded: green/yellow/red)
- [ ] **DASH-02**: Each source card shows: status indicator, freshness ("2h ago"), 24h article count, last error (if any)
- [ ] **DASH-03**: Volume trend sparklines per source (7-day history)
- [ ] **DASH-04**: Error log section showing recent failures with error type and timestamp
- [ ] **DASH-05**: Overall banner showing system health (e.g., "8/10 sources healthy")
- [ ] **DASH-06**: Anomaly flag when source volume drops below 50% of 7-day rolling average
- [ ] **DASH-07**: Disabled sources shown with reason and instructions to enable (graceful degradation)

### Deployment

- [ ] **DEPL-01**: launchd LaunchAgent plist with KeepAlive, absolute paths, log file paths
- [ ] **DEPL-02**: Wrapper script activates venv and starts uvicorn (no reload flag)
- [ ] **DEPL-03**: Management scripts: install-service.sh, uninstall-service.sh, status.sh
- [ ] **DEPL-04**: Service auto-restarts on crash

### Open-Source Packaging

- [ ] **OPEN-01**: .env.example with all environment variables documented (required vs optional)
- [ ] **OPEN-02**: pyproject.toml replaces requirements.txt (PEP 621)
- [ ] **OPEN-03**: scripts/check_setup.py validates: Python version, dependencies, .env exists, required vs optional tokens, database writable, ports available
- [ ] **OPEN-04**: Core sources (RSS, HackerNews, Reddit) work without any API keys
- [ ] **OPEN-05**: Optional sources skip gracefully with clear log message when tokens missing
- [ ] **OPEN-06**: No hardcoded absolute paths (audit and remove all /Users/ references)
- [ ] **OPEN-07**: CORS restricted to localhost by default (configurable via env var)
- [ ] **OPEN-08**: README rewritten for open-source audience (quick start, architecture, contributing guide)
- [ ] **OPEN-09**: Fresh-clone CI test validates clone → install → run → health check passes

## v2 Requirements

### Enhanced Monitoring

- **MON-01**: Historical freshness timeline (30-day view of per-source freshness)
- **MON-02**: Source dependency health (ping quant bridge and Claude API)
- **MON-03**: Collector performance metrics (p50/p95 duration per source)

### Extended Deployment

- **EXDP-01**: Docker support (Dockerfile + docker-compose.yml)
- **EXDP-02**: systemd service file for Linux deployments

## Out of Scope

| Feature | Reason |
|---------|--------|
| Multi-user authentication | Open-source self-hosted tool; users deploy their own instance |
| PostgreSQL migration | SQLite sufficient for single-user self-hosted |
| Telegram/Slack alerts | Dashboard monitoring is sufficient |
| ML anomaly detection | Simple statistical threshold (50% drop) covers 90% of cases |
| Prometheus/Grafana | Over-engineering for single-user; built-in dashboard sufficient |
| SaaS hosting | Users self-host |
| Data lineage visualization | Linear pipeline, no DAG to visualize |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| FOUND-01 | Phase 1 | Pending |
| FOUND-02 | Phase 1 | Pending |
| FOUND-03 | Phase 1 | Pending |
| FOUND-04 | Phase 1 | Pending |
| RETRY-01 | Phase 2 | Pending |
| RETRY-02 | Phase 2 | Pending |
| RETRY-03 | Phase 2 | Pending |
| RETRY-04 | Phase 2 | Pending |
| RETRY-05 | Phase 2 | Pending |
| RETRY-06 | Phase 2 | Pending |
| HLTH-01 | Phase 3 | Pending |
| HLTH-02 | Phase 3 | Pending |
| HLTH-03 | Phase 3 | Pending |
| HLTH-04 | Phase 3 | Pending |
| HLTH-05 | Phase 3 | Pending |
| HLTH-06 | Phase 3 | Pending |
| HLTH-07 | Phase 3 | Pending |
| DASH-01 | Phase 4 | Pending |
| DASH-02 | Phase 4 | Pending |
| DASH-03 | Phase 4 | Pending |
| DASH-04 | Phase 4 | Pending |
| DASH-05 | Phase 4 | Pending |
| DASH-06 | Phase 4 | Pending |
| DASH-07 | Phase 4 | Pending |
| DEPL-01 | Phase 5 | Pending |
| DEPL-02 | Phase 5 | Pending |
| DEPL-03 | Phase 5 | Pending |
| DEPL-04 | Phase 5 | Pending |
| OPEN-01 | Phase 5 | Pending |
| OPEN-02 | Phase 5 | Pending |
| OPEN-03 | Phase 5 | Pending |
| OPEN-04 | Phase 5 | Pending |
| OPEN-05 | Phase 5 | Pending |
| OPEN-06 | Phase 5 | Pending |
| OPEN-07 | Phase 5 | Pending |
| OPEN-08 | Phase 5 | Pending |
| OPEN-09 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 33 total
- Mapped to phases: 33
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-31*
*Last updated: 2026-03-31 after initial definition*
