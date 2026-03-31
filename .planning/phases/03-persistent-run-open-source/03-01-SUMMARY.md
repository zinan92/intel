---
phase: 03-persistent-run-open-source
plan: 01
subsystem: infra
tags: [launchd, cors, uvicorn, macos, service-management]

# Dependency graph
requires:
  - phase: 02-health-visibility
    provides: working FastAPI app with health dashboard
provides:
  - launchd LaunchAgent plist with KeepAlive auto-restart
  - service management scripts (install/uninstall/status)
  - CORS hardened to localhost-only defaults
  - conditional reload gated behind PARK_INTEL_DEV env var
affects: [03-02-open-source-packaging]

# Tech tracking
tech-stack:
  added: [launchd, launchctl]
  patterns: [env-driven CORS, placeholder-based plist templating]

key-files:
  created:
    - com.park-intel.agent.plist
    - scripts/park-intel-service.sh
    - scripts/install-service.sh
    - scripts/uninstall-service.sh
    - scripts/service-status.sh
  modified:
    - main.py
    - config.py

key-decisions:
  - "CORS defaults to localhost:5174, localhost:8001, 127.0.0.1:8001 — configurable via CORS_ORIGINS env var"
  - "Reload disabled by default; enabled only when PARK_INTEL_DEV=1"
  - "Plist uses __PROJECT_DIR__ placeholder resolved at install time — no hardcoded paths"

patterns-established:
  - "Env-driven CORS: CORS_ORIGINS comma-separated string parsed in config.py"
  - "Plist templating: __PROJECT_DIR__ placeholder replaced by install script via sed"

requirements-completed: [SHIP-01, SHIP-02, SHIP-03, SHIP-07, SHIP-08]

# Metrics
duration: 3min
completed: 2026-03-31
---

# Phase 3 Plan 1: Persistent Service Summary

**launchd LaunchAgent with KeepAlive auto-restart, CORS hardened to localhost defaults, and conditional dev reload**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-31T14:34:34Z
- **Completed:** 2026-03-31T14:37:38Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- CORS restricted from wildcard to localhost-only defaults, configurable via CORS_ORIGINS env var
- Reload gated behind PARK_INTEL_DEV=1 env var (production runs without hot reload)
- launchd plist with KeepAlive=true ensures automatic restart on crash or reboot
- Full service lifecycle scripts: install, uninstall, status
- Zero hardcoded /Users/ paths in any tracked file

## Task Commits

Each task was committed atomically:

1. **Task 1: Production config in main.py + CORS hardening + path audit** - `445cdc4` (feat)
2. **Task 2: launchd plist + wrapper script + management scripts** - `bde4656` (feat)

## Files Created/Modified
- `config.py` - Added CORS_ORIGINS env-driven config
- `main.py` - CORS uses CORS_ORIGINS, reload gated behind PARK_INTEL_DEV
- `com.park-intel.agent.plist` - LaunchAgent template with __PROJECT_DIR__ placeholders
- `scripts/park-intel-service.sh` - Wrapper activating .venv and running uvicorn
- `scripts/install-service.sh` - Resolves paths, copies plist, runs launchctl bootstrap
- `scripts/uninstall-service.sh` - Stops and removes LaunchAgent
- `scripts/service-status.sh` - Shows service state via launchctl print

## Decisions Made
- CORS defaults to localhost:5174, localhost:8001, 127.0.0.1:8001 (covers frontend dev server and API)
- Plist uses __PROJECT_DIR__ placeholder resolved at install time to avoid hardcoded paths
- install-service.sh checks for existing service and unloads before reinstalling

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Pre-existing test failure in test_source_registry_model.py (migration test) confirmed not caused by this plan's changes

## User Setup Required

None - no external service configuration required. Users run `scripts/install-service.sh` to activate.

## Next Phase Readiness
- Service infrastructure complete, ready for open-source packaging (plan 03-02)
- .env.example, graceful degradation, and README rewrite are next

---
*Phase: 03-persistent-run-open-source*
*Completed: 2026-03-31*
