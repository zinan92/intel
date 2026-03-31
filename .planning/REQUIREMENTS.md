# Requirements: Park-Intel Reliability & Open-Source

**Defined:** 2026-03-31
**Core Value:** Anyone can clone, configure, and run a self-hosted market intelligence pipeline with zero-config core sources and a health view that makes data freshness visible at a glance.

## v1 Requirements

### Collector Reliability

- [x] **RELY-01**: CollectorRun model persists every collection execution (source_type, status, articles_fetched, articles_saved, duration_ms, error_message, retry_count)
- [x] **RELY-02**: Idempotent migration adds collector_runs table without breaking existing data
- [x] **RELY-03**: SQLite busy_timeout verified/set to 5000ms
- [x] **RELY-04**: Transient failures (timeout, connection error, rate limit) automatically retry with exponential backoff and jitter (3 attempts)
- [x] **RELY-05**: Non-transient failures (401/403 auth, parse errors, missing config) are NOT retried
- [x] **RELY-06**: Errors categorized into 4 types: transient, auth, parse, config
- [x] **RELY-07**: Every collection attempt (success or failure) writes a CollectorRun row

### Health Visibility

- [x] **HLTH-01**: GET /api/health/sources returns per-source status (ok/stale/degraded/error/disabled) with freshness age, article counts, last error
- [x] **HLTH-02**: GET /api/health/summary returns aggregate stats (total sources, healthy count, degraded count, total articles 24h)
- [x] **HLTH-03**: Scheduler heartbeat updated every 5 minutes; health endpoint reports scheduler alive/dead
- [x] **HLTH-04**: Per-source freshness policy (expected_freshness_hours in source_registry) replaces hardcoded 24h
- [x] **HLTH-05**: Startup boot log lists active sources, skipped sources (with reason), scheduler start time
- [x] **HLTH-06**: Health page at /health shows all source statuses color-coded (green/yellow/red) with freshness, 24h count, last error
- [x] **HLTH-07**: Overall health banner ("8/10 sources healthy")
- [x] **HLTH-08**: Volume anomaly flag when source count drops below 50% of 7-day average (number + color, not charts)
- [x] **HLTH-09**: Disabled sources shown with reason and enable instructions

### Persistent Run & Open-Source

- [x] **SHIP-01**: launchd LaunchAgent plist with KeepAlive, absolute paths, log file paths
- [x] **SHIP-02**: Wrapper script activates venv and starts uvicorn (no reload flag)
- [x] **SHIP-03**: Service auto-restarts on crash
- [ ] **SHIP-04**: .env.example with all environment variables documented (required vs optional)
- [ ] **SHIP-05**: Core sources (RSS, HackerNews, Reddit) work without any API keys
- [ ] **SHIP-06**: Optional sources skip gracefully with clear log message when tokens missing
- [x] **SHIP-07**: No hardcoded absolute paths (audit /Users/ references)
- [x] **SHIP-08**: CORS restricted to localhost by default (configurable via env var)
- [ ] **SHIP-09**: README rewritten for open-source audience (quick start, architecture)

## v2 Requirements

### Enhanced Monitoring

- **MON-01**: Historical freshness timeline (30-day per-source)
- **MON-02**: Source dependency health (ping quant bridge and Claude API)
- **MON-03**: Collector performance metrics (p50/p95 duration)
- **MON-04**: Volume trend sparklines (Recharts)
- **MON-05**: Dead-letter logging for exhausted retries

### Enhanced Packaging

- **PKG-01**: pyproject.toml replaces requirements.txt (PEP 621)
- **PKG-02**: scripts/check_setup.py full validation
- **PKG-03**: Fresh-clone CI test
- **PKG-04**: Docker support (Dockerfile + docker-compose.yml)
- **PKG-05**: systemd service file for Linux
- **PKG-06**: Structured JSON logging (structlog)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Multi-user authentication | Open-source self-hosted tool; users deploy their own instance |
| PostgreSQL migration | SQLite sufficient for single-user self-hosted |
| Telegram/Slack alerts | Health page is sufficient |
| ML anomaly detection | Simple 50% threshold covers 90% of cases |
| Prometheus/Grafana | Over-engineering for single-user |
| SaaS hosting | Users self-host |
| Data lineage visualization | Linear pipeline, no DAG |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| RELY-01 | Phase 1 | Complete |
| RELY-02 | Phase 1 | Complete |
| RELY-03 | Phase 1 | Complete |
| RELY-04 | Phase 1 | Complete |
| RELY-05 | Phase 1 | Complete |
| RELY-06 | Phase 1 | Complete |
| RELY-07 | Phase 1 | Complete |
| HLTH-01 | Phase 2 | Complete |
| HLTH-02 | Phase 2 | Complete |
| HLTH-03 | Phase 2 | Complete |
| HLTH-04 | Phase 2 | Complete |
| HLTH-05 | Phase 2 | Complete |
| HLTH-06 | Phase 2 | Complete |
| HLTH-07 | Phase 2 | Complete |
| HLTH-08 | Phase 2 | Complete |
| HLTH-09 | Phase 2 | Complete |
| SHIP-01 | Phase 3 | Complete |
| SHIP-02 | Phase 3 | Complete |
| SHIP-03 | Phase 3 | Complete |
| SHIP-04 | Phase 3 | Pending |
| SHIP-05 | Phase 3 | Pending |
| SHIP-06 | Phase 3 | Pending |
| SHIP-07 | Phase 3 | Complete |
| SHIP-08 | Phase 3 | Complete |
| SHIP-09 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 25 total
- Mapped to phases: 25
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-31*
*Last updated: 2026-03-31 after Codex review — trimmed from 33 to 25, moved gold-plating to v2*
