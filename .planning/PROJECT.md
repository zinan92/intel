# Park-Intel

## What This Is

An open-source qualitative signal pipeline that collects frontier-tech, macro, and market content from 10+ source types (RSS, HackerNews, Reddit, GitHub, etc.), enriches articles with keyword tags and LLM-based relevance scoring, clusters them into narrative events, and serves everything through a REST API with a feed-first frontend workbench. Ships with a health dashboard for monitoring source freshness, automatic retry for transient failures, and launchd-based persistent deployment.

## Core Value

Anyone can clone, configure, and run a self-hosted market intelligence pipeline with zero-config core sources and a health dashboard that makes data freshness visible at a glance.

## Requirements

### Validated

- ✓ Multi-source data collection (10 source types) — existing
- ✓ Registry-driven scheduler (APScheduler, per-source-type jobs) — existing
- ✓ Keyword tagging (13 categories, regex-based) — existing
- ✓ LLM-based relevance scoring and narrative tagging (Claude) — existing
- ✓ Ticker extraction (cashtag, alias, source-provided) — existing
- ✓ Event aggregation (48h narrative_tag clustering, signal scoring) — existing
- ✓ User personalization (topic weights, personalized feed ranking) — existing
- ✓ Quant bridge (async price snapshots from quant-data-pipeline) — existing
- ✓ REST API (articles, events, signals, users, health) — existing
- ✓ Feed-first React frontend workbench — existing
- ✓ 283+ test suite — existing
- ✓ Collector error categorization (transient/auth/parse/config) — v1.0
- ✓ CollectorRun persistent model with retry tracking — v1.0
- ✓ Tenacity retry (3 attempts, exponential backoff + jitter) — v1.0
- ✓ Health API (/api/health/sources, /api/health/summary) — v1.0
- ✓ Scheduler heartbeat with crash detection — v1.0
- ✓ Per-source freshness policy (expected_freshness_hours) — v1.0
- ✓ /health dashboard with color-coded source cards — v1.0
- ✓ Volume anomaly detection (50% threshold) — v1.0
- ✓ launchd LaunchAgent with auto-restart — v1.0
- ✓ CORS hardened to localhost, dev/prod mode — v1.0
- ✓ .env.example, zero-config core sources, README rewrite — v1.0

### Active

(None — v1.0 milestone shipped. Define next milestone requirements via `/gsd:new-milestone`)

### Out of Scope

- Multi-user authentication — open-source tool, users deploy their own instance
- Database migration to PostgreSQL — SQLite sufficient for single-user self-hosted
- Telegram/Slack notifications — dashboard is sufficient for monitoring
- SaaS hosting / managed service — users self-host
- Mobile app — web dashboard only
- Vercel deployment — needs persistent process + disk, not suitable for serverless

## Context

- This is stage 02 (情报采集) in an 8-stage trading pipeline
- Repo: github.com/zinan92/intel (was qualitative-data-pipeline, renamed 2026-03-31)
- Local path: ~/work/trading-co/park-intel, port 8001
- Frontend: React + TypeScript + Vite on port 5174
- Backend: FastAPI + SQLAlchemy + SQLite + APScheduler
- Data last updated March 22 — service was not running persistently
- Production readiness audit identified: no auth (acceptable for open-source), silent collector failures, no deployment config, CORS wide open, no rate limiting, no monitoring dashboard
- 27 test collection errors need fixing
- `.env` contains live Xueqiu cookies/tokens — must not be committed

## Constraints

- **Tech stack**: Keep existing FastAPI + React stack — no framework migration
- **Database**: Stay on SQLite — simplest for self-hosted deployment
- **LLM dependency**: Claude API is optional (LLM tagging degrades gracefully without it)
- **Zero-config core**: RSS, HackerNews, Reddit must work without any API keys or tokens
- **Backward compatibility**: Existing data in park_intel.db must not be lost during upgrades

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Open-source tool, not SaaS | Users self-host, no auth complexity needed | — Pending |
| Core sources zero-config | Lower barrier to entry, RSS/HN/Reddit need no tokens | — Pending |
| SQLite over Postgres | Simpler deployment, sufficient for single-user | — Pending |
| launchd for persistence | macOS native, no Docker dependency for local dev | — Pending |
| Health Dashboard over Telegram alerts | Visual monitoring, no external service dependency | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-31 after v1.0 milestone*
