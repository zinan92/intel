# Park Intel Source Layer Redesign — Execution Log

**Date:** 2026-03-13
**Baseline:** 31 passed
**Goal:** Remove retired collectors, introduce ACTIVE_SOURCES, rebuild RSS, add 4 new collectors

---

## Checklist

| # | Chunk | Status |
|---|-------|--------|
| 1 | Remove retired collectors (youtube, substack, twitter) | `done` |
| 2 | ACTIVE_SOURCES registry + /api/health semantics | `done` |
| 3 | RSS collector — config-driven (RSS_FEEDS in config.py) | `done` |
| 4 | ClawFeed collector | `done` |
| 5 | Reddit collector | `done` |
| 6 | GitHub Release collector | `done` |
| 7 | Webpage Monitor collector | `done` |
| 8 | Scheduler — register new, deregister retired | `done` (done as part of chunk 1) |
| 9 | Tests — all new test files | `done` |

---

## Log

### 2026-03-13T00:00 — Baseline verification
- Ran: `.venv/bin/python -m pytest tests/ -q`
- Result: **31 passed** ✓
- Next: Chunk 1

---

### Chunk 1 — Remove retired collectors
- Files changed: `scheduler.py`, `config.py`, deleted `collectors/youtube.py`, `collectors/substack.py`, `collectors/twitter.py`
- Removed: `twitter_interval_hours`, `substack_interval_hours`, `youtube_interval_hours` from `SchedulerConfig`
- Added: `clawfeed_interval_hours`, `reddit_interval_hours`, `github_release_interval_hours`, `webpage_monitor_interval_hours` to `SchedulerConfig`
- Removed: `TWITTER_TIMELINE_COUNT`, `SUBSTACK_FEEDS`, `YOUTUBE_CHANNELS` from config.py
- Replaced bird CLI check with clawfeed CLI check in `_check_dependencies`
- Added 4 new static runner methods; removed 3 retired ones
- Verification: `.venv/bin/python -m pytest tests/ -q` → **31 passed** ✓

### Chunk 2 — ACTIVE_SOURCES registry + /api/health semantics
- Files changed: `config.py` (added `ACTIVE_SOURCES`), `api/routes.py` (rewrote `health()`)
- Created: `tests/test_health_active_sources.py` (3 tests)
- health() now iterates `config.ACTIVE_SOURCES`; retired sources excluded
- `/api/articles/sources` unchanged (remains DB-historical)
- Verification: `tests/test_health_active_sources.py` → **3 passed**; full suite → **34 passed** ✓

### Chunk 3 — RSS collector config-driven
- Files changed: `config.py` (added `RSS_FEEDS` — 52 feeds), `collectors/rss.py` (rewritten)
- Old hardcoded `FEEDS` removed; collector reads `config.RSS_FEEDS`
- category field mapped into article tags
- source_id uses SHA-256 of URL (deterministic)
- Created: `tests/test_rss_collector.py` (5 tests)
- Verification: **5 passed** ✓

### Chunk 4 — ClawFeed collector
- Files created: `collectors/clawfeed.py`
- CLI-present and CLI-missing paths tested
- source_id: uses item id > URL hash > title+author hash
- Created: `tests/test_clawfeed.py` (8 tests)
- Verification: **8 passed** ✓

### Chunk 5 — Reddit collector
- Files created: `collectors/reddit.py`
- Uses `https://www.reddit.com/r/{sub}/top/.rss?t=day&limit=25`
- Per-run dedup by URL across subreddits
- source_id: SHA-256 of entry id or URL
- Created: `tests/test_reddit.py` (6 tests)
- Verification: **6 passed** ✓

### Chunk 6 — GitHub Release collector
- Files created: `collectors/github_release.py`
- Auth: includes Bearer token if `GITHUB_TOKEN` set; proceeds unauthenticated otherwise
- source_id: release id > repo+tag hash
- 404 repos skipped gracefully
- Created: `tests/test_github_release.py` (8 tests)
- Verification: **8 passed** ✓

### Chunk 7 — Webpage Monitor collector
- Files created: `collectors/webpage_monitor.py`
- Supports type=scrape (blog URL extraction) and type=github_commits (doc change monitoring)
- State file: `data/webpage_monitor_state.json`
- First-run dedup: only unseen URLs/SHAs yielded
- Created: `tests/test_webpage_monitor.py` (10 tests)
- Verification: **10 passed** ✓

### Final full suite
- Ran: `.venv/bin/python -m pytest tests/ -q`
- Result: **71 passed** ✓ (was 31; +40 new tests)

---

---

### Code Review Fixes (2026-03-13)

Four issues identified by code reviewer. All fixed in a single pass.

**Fix 1 — LLM tagger broken at runtime**
- Problem: `_run_llm_tagger()` called `tagger_main()` which uses argparse and calls `sys.exit()` when no flags are given. `SystemExit` is not caught by `except Exception`.
- Fix: extracted `run_tagger(backfill, limit, prefiltered, batch_size)` from `scripts/run_llm_tagger.py`. `main()` now calls `run_tagger`. `_run_llm_tagger()` now calls `run_tagger(limit=50)` directly.
- Files: `scripts/run_llm_tagger.py`, `scheduler.py`

**Fix 2 — run_collectors.py broken**
- Problem: still imported `collectors.substack`, `collectors.twitter`, `collectors.youtube` (deleted).
- Fix: rewrote imports and `COLLECTORS` dict to match the 10 active sources.
- Files: `scripts/run_collectors.py`
- Verified: `.venv/bin/python scripts/run_collectors.py --help` works.

**Fix 3 — Test hermeticity (scheduler starts real jobs in tests)**
- Problem: `TestClient(app)` triggers the FastAPI lifespan which starts APScheduler; first job runs at `base_time + 0s`; `test_signals.py` never patched it.
- Fix: added `tests/conftest.py` with `autouse=True` fixture that patches `CollectorScheduler.start` and `.shutdown` for every test.
- Files: `tests/conftest.py`

**Fix 4 — Scheduler/config drift (intervals duplicated)**
- Problem: `SchedulerConfig` repeated interval values that already existed in `config.ACTIVE_SOURCES`. Adding/changing a source in `ACTIVE_SOURCES` would not change what actually gets scheduled.
- Fix: removed all per-source interval fields from `SchedulerConfig` (kept only `llm_tagger_interval_hours` and `timezone`). `_register_jobs()` now reads intervals from `config.ACTIVE_SOURCES`. Added `_SOURCE_RUNNERS` class dict to map source names to runner callables.
- Files: `scheduler.py`
- Verified: all 10 active sources have runners, no missing.

Post-fix verification: **71 passed** ✓

---

---

## Phase 2 — Frontend Feed-First Workbench

| # | Chunk | Status |
|---|-------|--------|
| F0 | Verify preconditions | `done` (71 passed) |
| F1 | Backend /api/ui/* read-model endpoints + tests | `done` |
| F2 | Frontend scaffold (React + Vite) | `done` |
| F3 | Shared types and API client | `done` |
| F4 | Feed page | `done` |
| F5 | Item detail drawer | `done` |
| F6 | Topic and source pages | `done` |
| F7 | Search page | `done` |
| F8 | Responsive polish | `done` |
| F9 | Dev integration and docs | `done` |

---

### Chunk F1 — Backend /api/ui/* endpoints

- Files created: `api/ui_routes.py`, `tests/test_ui_feed_api.py`, `tests/test_ui_topics_api.py`
- Files modified: `main.py` (added `ui_router` import and registration)
- Endpoints implemented:
  - `GET /api/ui/feed` — priority-scored feed, cursor pagination, topic/source/min_relevance/window filters, context modules
  - `GET /api/ui/items/{id}` — full article detail, related items
  - `GET /api/ui/topics` — narrative topic list sorted by count
  - `GET /api/ui/topics/{slug}` — topic drill-down with scored items
  - `GET /api/ui/sources` — source list with kind + count
  - `GET /api/ui/sources/{name}` — source drill-down with scored items
  - `GET /api/ui/search` — keyword search across title/content
- Priority score formula: relevance_component (0–5) + freshness_component (0–2) + momentum_component (0–1) + source_weight + kind_weight
- Cursor format: `"{priority_score:.4f}:{id}"`
- source_kind mapping: github_release→release, rss→blog, hackernews→discussion, clawfeed→post, reddit→discussion
- TDD: 37 tests written first (all failing), then implemented → all 37 pass
- Full suite: **108 passed** ✓ (was 71; +37 new)

---

### Chunks F2–F9 — Frontend

- Directory: `frontend/`
- Stack: React 18 + TypeScript + Vite 5 + Tailwind CSS 3 + TanStack Query v5 + React Router v6 + Radix UI
- Files created:
  - `frontend/package.json`, `vite.config.ts`, `tsconfig.json`, `tailwind.config.js`, `postcss.config.js`, `index.html`
  - `src/vite-env.d.ts`, `src/index.css`, `src/main.tsx`, `src/App.tsx`
  - `src/types/api.ts` — all shared TypeScript types
  - `src/api/client.ts` — typed fetch wrapper for all /api/ui/* endpoints
  - `src/components/TopBar.tsx` — sticky top bar with inline search
  - `src/components/Sidebar.tsx` — topics + sources nav (lg+ breakpoint)
  - `src/components/ContextRail.tsx` — right rail: rising topics + source health
  - `src/components/FeedCard.tsx` — priority-scored feed card
  - `src/components/ItemDrawer.tsx` — Radix Dialog slide-in detail drawer
  - `src/pages/FeedPage.tsx` — infinite scroll feed with relevance/window filters
  - `src/pages/TopicPage.tsx` — topic drill-down
  - `src/pages/SourcePage.tsx` — source drill-down
  - `src/pages/SearchPage.tsx` — keyword search with URL sync
- Vite proxy: `/api` → `http://localhost:8001`
- Build verification: `tsc && vite build` → **✓ built in 685ms**, zero type errors
- Backend tests: **108 passed** ✓ (unchanged)

---

### Phase 2 regression fixes + final verification

- Fixed `/api/ui/sources` to iterate active sources only and exclude retired historical sources from the frontend source list.
- Fixed feed context `source_health` semantics to use active-source health status rather than recent-article presence.
- Fixed `_window_cutoff()` to parse day-based windows such as `7d`.
- Fixed `/api/ui/sources/{name}` to return `last_seen_at` and 404 retired sources.
- Added dedicated regression coverage in `tests/test_ui_regressions.py`.
- Final verification:
  - `.venv/bin/pytest -q` → **118 passed**
  - `cd frontend && npm run build` → **success**

---

## Follow-up Items (Deferred)
- reduce `datetime.utcnow()` deprecation warnings by moving to timezone-aware UTC datetimes
- optional live smoke test against real external sources after deploy
- verify whether `collectors/__init__.py` is needed at all or can be simplified further

