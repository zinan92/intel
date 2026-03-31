# Roadmap: Park-Intel Reliability & Open-Source

## Overview

Make park-intel reliable and open-source-ready in 3 phases. Fix the silent failures that cause data staleness, add a health view so you can see what's working at a glance, then package it for others to clone and run.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [ ] **Phase 1: Collector Reliability** - Stop swallowing errors, add retry, persist every run
- [x] **Phase 2: Health Visibility** - API endpoints + frontend health page showing source status and anomalies (completed 2026-03-31)
- [ ] **Phase 3: Persistent Run & Open-Source** - launchd service, zero-config core sources, README for public release

## Phase Details

### Phase 1: Collector Reliability
**Goal**: Collectors stop silently failing. Every run is recorded. Transient errors retry automatically.
**Depends on**: Nothing (first phase)
**Requirements**: RELY-01, RELY-02, RELY-03, RELY-04, RELY-05, RELY-06, RELY-07
**Success Criteria** (what must be TRUE):
  1. Running any collector produces a CollectorRun row with status, article counts, duration, and error info
  2. A timeout/connection error retries up to 3 times with backoff; each attempt is recorded
  3. A 401/auth error fails immediately without retry; error category is visible in the run record
  4. Existing data in park_intel.db survives the migration unchanged
**Plans:** 2 plans

Plans:
- [x] 01-01-PLAN.md — Foundation: error types, CollectorRun model, migration, tenacity dependency
- [x] 01-02-PLAN.md — Integration: retry in adapters, recording in scheduler, cleanup job

### Phase 2: Health Visibility
**Goal**: Open /health in a browser and immediately see which sources are working, which are broken, and whether collection volume is normal
**Depends on**: Phase 1
**Requirements**: HLTH-01, HLTH-02, HLTH-03, HLTH-04, HLTH-05, HLTH-06, HLTH-07, HLTH-08, HLTH-09
**Success Criteria** (what must be TRUE):
  1. GET /api/health/sources returns every source with status, freshness, counts, and last error
  2. /health page shows color-coded source cards (green/yellow/red) with freshness and 24h count
  3. Scheduler crash is detectable via health endpoint within 10 minutes
  4. Volume anomaly (50%+ drop from 7-day average) is visually flagged on the source card
  5. Disabled sources appear with reason and enable instructions
**Plans:** 2/2 plans complete

Plans:
- [x] 02-01-PLAN.md — Backend: health API endpoints, migration, heartbeat, boot logging
- [x] 02-02-PLAN.md — Frontend: health page with source cards, banner, nav link

### Phase 3: Persistent Run & Open-Source
**Goal**: Anyone can clone the repo, run one setup command, and have a working pipeline with persistent background service
**Depends on**: Phase 2
**Requirements**: SHIP-01, SHIP-02, SHIP-03, SHIP-04, SHIP-05, SHIP-06, SHIP-07, SHIP-08, SHIP-09
**Success Criteria** (what must be TRUE):
  1. Service auto-restarts after crash (launchd KeepAlive verified)
  2. Core sources (RSS, HackerNews, Reddit) collect articles with zero API keys
  3. A fresh clone on macOS: install deps, start server, GET /api/health returns 200
  4. No hardcoded /Users/ paths in codebase
  5. README quick-start works for an unfamiliar developer
**Plans:** 2 plans

Plans:
- [x] 03-01-PLAN.md — Service: launchd plist, wrapper script, management scripts, CORS hardening, dev/prod mode
- [ ] 03-02-PLAN.md — Packaging: .env.example, core source verification, graceful degradation, README rewrite

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Collector Reliability | 2/2 | Complete | 2026-03-31 |
| 2. Health Visibility | 2/2 | Complete   | 2026-03-31 |
| 3. Persistent Run & Open-Source | 0/2 | Not started | - |
