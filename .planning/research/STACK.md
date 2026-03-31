# Technology Stack

**Project:** Park-Intel Reliability & Open-Source Milestone
**Researched:** 2026-03-31
**Mode:** Ecosystem (adding reliability layer to existing FastAPI + React + SQLite pipeline)

## Existing Stack (Keep As-Is)

These are already in the project and should not change:

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.13.7 | Backend runtime |
| FastAPI | 0.100.0+ | REST API framework |
| SQLAlchemy | 2.0+ | ORM / database access |
| SQLite | 3.x (WAL mode) | Data store |
| APScheduler | 3.10.0+ | Background job scheduling |
| React | 18.3.1 | Frontend UI |
| TypeScript | 5.6.3 | Frontend type safety |
| Vite | 5.4.10 | Frontend build tool |
| Tailwind CSS | 3.4.15 | Styling |
| TanStack Query | 5.60.5 | Server state management |
| D3 | 7.9.0 | Event Constellation visualization |

## New Dependencies: Backend

### Retry & Resilience

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| tenacity | 9.1.4 | Retry with exponential backoff for all collectors | De facto standard for Python retry. 170M+ monthly PyPI downloads. Decorator-based API fits cleanly onto existing `BaseCollector` methods. Supports async, custom stop/wait strategies, and per-exception retry filtering. No real competitor -- `backoff` has 1/10th the downloads and fewer features. | HIGH |
| pybreaker | 1.4.1 | Circuit breaker for external API calls (Xueqiu, GitHub, Yahoo Finance) | Prevents cascading failures when external sources are down. Lightweight (single module), well-maintained, 1.4.1 released Sep 2025. Use for sources with rate limits or auth dependencies -- when a source fails N times, stop hammering it for a cooldown period. | MEDIUM |

**Why tenacity over backoff:** tenacity has 10x the adoption, active maintenance (last release Feb 2026), richer API (retry_if_exception_type, wait_exponential_jitter, before/after callbacks for logging), and native async support. backoff is simpler but lacks the composability needed for 10+ heterogeneous collectors.

**Why pybreaker over aiobreaker:** The existing collectors use synchronous `requests` (not `httpx` async). pybreaker works with sync code directly. aiobreaker is a fork for async-only -- unnecessary complexity here. If collectors migrate to async later, pybreaker 1.4+ supports both patterns.

**Why NOT a full resilience framework (e.g., resilience4j-style):** Python ecosystem does not have a mature all-in-one resilience library. tenacity + pybreaker is the idiomatic Python approach -- compose small libraries rather than adopt a monolith.

### Structured Logging

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| structlog | 25.5.0 | Structured JSON logging for collectors, scheduler, and API | Current codebase likely uses basic `logging` or `print`. structlog adds key-value context (source_name, collector_type, attempt_number) to every log line, making health monitoring queryable. JSON output integrates with any log viewer. 25.5.0 released Oct 2025, mature and stable. | HIGH |

**Why structlog over loguru:** structlog produces machine-parseable JSON by default, which the health dashboard API can query. loguru is prettier for human reading but harder to aggregate programmatically. For a monitoring-focused milestone, structured output wins.

### Health Monitoring (Backend)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| (custom, no library) | -- | Health check API endpoints and collector run history | The existing `/api/health` endpoint already provides registry-driven source health. Extend it with run history tracking (last_run, last_success, last_error, consecutive_failures) stored in a new SQLite table. No external library needed -- FastAPI health check libraries (fastapi-health, fastapi-healthchecks) add Kubernetes liveness/readiness patterns that are irrelevant for a self-hosted single-process app. | HIGH |

**What to build, not install:**
- `collector_runs` table: source_name, started_at, finished_at, status (success/error), error_message, articles_collected
- `/api/health/sources` endpoint: per-source health with freshness, error rate, trend
- `/api/health/scheduler` endpoint: thread status, next scheduled runs, missed runs

### Open-Source Packaging

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| pyproject.toml | (PEP 621) | Project metadata and dependency declaration | Standard since PEP 621. Replace `requirements.txt` with a proper `pyproject.toml` using setuptools backend. This is the 2025/2026 standard for any open-source Python project -- Poetry/Hatch are alternatives but add tooling complexity for contributors. setuptools with pyproject.toml is zero-new-tooling. | HIGH |
| python-dotenv | 1.0+ (existing) | .env file loading | Already in stack. Add `.env.example` with all variables documented (required vs optional). | HIGH |

**Why setuptools over Poetry/Hatch for this project:** Contributors should be able to `pip install -e .` without learning a new tool. Poetry adds a lock file and resolver that is overkill for an application (not a library). Hatch is great but less familiar. setuptools + pyproject.toml is the lowest-friction path for open-source contributors.

## New Dependencies: Frontend

### Health Dashboard Visualization

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| recharts | 3.8.1 | Health dashboard charts (collection volume trends, error rates, freshness timeline) | Built on D3 (already in project) but provides React-native declarative components. Line charts, bar charts, and area charts for health metrics without writing raw D3. D3 7.9 is already in the project for Event Constellation (complex force-directed graph) -- use D3 for that, Recharts for standard dashboard charts. 3.8.1 released Mar 2026. | HIGH |

**Why Recharts over raw D3 for the health dashboard:** D3 is already in the project but is overkill for standard line/bar charts. Recharts wraps D3 in React components, meaning health dashboard charts are 10-20 lines of JSX instead of 100+ lines of D3 bindigns. Reserve raw D3 for the Constellation visualization where custom force-directed layouts justify the complexity.

**Why Recharts over Nivo/Victory/Chart.js:**
- Nivo: Heavier bundle, more opinionated styling, harder to theme with Tailwind
- Victory: Smaller ecosystem, less active development
- Chart.js (react-chartjs-2): Canvas-based (not SVG), harder to style consistently with Tailwind + existing D3 SVG patterns

### No New Frontend Dependencies for Health Dashboard UI

The existing stack (React + Tailwind + TanStack Query + Radix UI) is sufficient for the health dashboard UI:
- TanStack Query for polling health endpoints (refetchInterval for auto-refresh)
- Radix UI for status indicators, tooltips, dialogs
- Tailwind for layout and status color coding

## Infrastructure

### Service Persistence (macOS launchd)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| launchd (LaunchAgent) | macOS native | Keep park-intel running persistently, auto-restart on crash | macOS native, no Docker/systemd dependency. LaunchAgent (user-level, not daemon) is correct for a personal dev tool. PROJECT.md already specifies this decision. | HIGH |

**Key launchd configuration decisions:**

1. **LaunchAgent, not LaunchDaemon**: LaunchAgent runs in user session (has network, display access). LaunchDaemon runs as root at boot -- wrong for a user tool.

2. **Plist location**: `~/Library/LaunchAgents/com.park-intel.api.plist`

3. **KeepAlive: true** with `SuccessfulExit: false`: Restart only on crashes, not clean exits. This prevents restart loops if the user intentionally stops the service.

4. **Environment variables**: Use `EnvironmentVariables` dict in plist to pass API keys, or source from .env via a wrapper script.

5. **Logging**: `StandardOutPath` and `StandardErrorPath` to `~/Library/Logs/park-intel/`. Pair with structlog JSON output for queryable logs.

6. **Wrapper script**: Create `scripts/park-intel-service.sh` that activates the venv and runs `python main.py`. Plist calls this script. This avoids hardcoding absolute venv paths in plist XML.

**Template plist (to be generated by setup script):**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" ...>
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.park-intel.api</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>PARK_INTEL_DIR/scripts/park-intel-service.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>PARK_INTEL_DIR</string>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>HOME/Library/Logs/park-intel/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>HOME/Library/Logs/park-intel/stderr.log</string>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
```

**Management commands (provide as Makefile targets or CLI):**
```bash
# Install service
scripts/install-service.sh

# Start/stop/status
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.park-intel.api.plist
launchctl bootout gui/$(id -u)/com.park-intel.api
launchctl print gui/$(id -u)/com.park-intel.api
```

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Retry | tenacity 9.1.4 | backoff | 1/10th adoption, fewer features, no jitter built-in |
| Circuit breaker | pybreaker 1.4.1 | aiobreaker | Collectors are sync; aiobreaker adds async complexity for no benefit |
| Circuit breaker | pybreaker 1.4.1 | circuitbreaker (PyPI) | Less maintained, fewer features than pybreaker |
| Logging | structlog 25.5.0 | loguru | Pretty but not machine-parseable by default; structlog JSON better for health dashboard |
| Health monitoring | Custom endpoints | Prometheus + Grafana | Massive overkill for single-user self-hosted app; adds external service dependencies |
| Health monitoring | Custom endpoints | fastapi-health | Designed for K8s liveness probes, not source-level health tracking |
| Dashboard charts | Recharts 3.8.1 | Raw D3 | D3 is 5-10x more code for standard charts; save D3 for Constellation |
| Dashboard charts | Recharts 3.8.1 | Nivo | Heavier bundle, harder Tailwind integration |
| Packaging | setuptools + pyproject.toml | Poetry | Adds tooling dependency for contributors; app not library |
| Packaging | setuptools + pyproject.toml | Hatch | Less familiar to most Python devs |
| Service persistence | launchd LaunchAgent | Docker | Adds container runtime dependency; overkill for local dev tool |
| Service persistence | launchd LaunchAgent | supervisord | External dependency; launchd is native on macOS |
| Service persistence | launchd LaunchAgent | systemd | Linux-only; project targets macOS |

## Anti-Recommendations (Do NOT Use)

| Technology | Why Not |
|------------|---------|
| Prometheus + Grafana | Requires running 2 additional services. For a single-user self-hosted tool, custom health endpoints rendered in the existing React app are simpler and sufficient. |
| Celery | APScheduler already handles background scheduling. Celery adds Redis/RabbitMQ dependency for no benefit in a single-process app. |
| Sentry | External SaaS dependency. structlog + custom error tracking in SQLite is sufficient and keeps the tool fully self-hosted. |
| Docker for development | PROJECT.md explicitly excludes Docker dependency. launchd is simpler for macOS local deployment. |
| FastAPI BackgroundTasks for scheduling | APScheduler already does this with cron-like scheduling. BackgroundTasks are for per-request fire-and-forget, not periodic jobs. |

## Installation

### Backend (new dependencies only)

```bash
pip install tenacity==9.1.4 pybreaker==1.4.1 structlog==25.5.0
```

### Frontend (new dependencies only)

```bash
cd frontend && npm install recharts@3.8.1
```

### Full project install (post pyproject.toml migration)

```bash
# Clone and setup
git clone https://github.com/zinan92/intel.git park-intel
cd park-intel
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Frontend
cd frontend && npm install

# Configure
cp .env.example .env
# Edit .env with your API keys (all optional for core sources)

# Run
python main.py
```

## Version Pinning Strategy

For open-source projects, pin major.minor but allow patch updates:

```toml
# pyproject.toml
[project]
dependencies = [
    "fastapi>=0.100,<1.0",
    "sqlalchemy>=2.0,<3.0",
    "uvicorn>=0.23,<1.0",
    "apscheduler>=3.10,<4.0",
    "tenacity>=9.1,<10.0",
    "pybreaker>=1.4,<2.0",
    "structlog>=25.0,<26.0",
    "feedparser>=6.0",
    "requests>=2.31",
    "httpx>=0.27",
    "python-dotenv>=1.0",
    "anthropic>=0.40",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "ruff>=0.4",
]
```

## Sources

- [tenacity on PyPI](https://pypi.org/project/tenacity/) - v9.1.4, Feb 2026
- [tenacity documentation](https://tenacity.readthedocs.io/)
- [pybreaker on PyPI](https://pypi.org/project/pybreaker/) - v1.4.1, Sep 2025
- [pybreaker on GitHub](https://github.com/danielfm/pybreaker)
- [structlog documentation](https://www.structlog.org/) - v25.5.0
- [recharts on npm](https://www.npmjs.com/package/recharts) - v3.8.1, Mar 2026
- [recharts on GitHub](https://github.com/recharts/recharts)
- [Python Packaging User Guide - pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
- [launchd.plist man page](https://keith.github.io/xcode-man-pages/launchd.plist.5.html)
- [launchd tutorial](https://www.launchd.info/)
- [Python Packaging Best Practices 2026](https://dasroot.net/posts/2026/01/python-packaging-best-practices-setuptools-poetry-hatch/)

---

*Stack research: 2026-03-31*
