# Park Intel Source Architecture v2 — Execution Log

**Date:** 2026-03-15
**Branch:** `feature/source-architecture-v2`
**Worktree:** `.worktrees/source-arch-v2`

## Checklist

- [x] Task 1: Add the Source Registry schema
- [x] Task 2: Add the source registry service layer
- [x] Task 3: Seed the registry from the current config
- [x] Task 4: Add the source resolver
- [x] Task 5: Introduce adapter contracts keyed by source type
- [x] Task 6: Migrate scheduler and health to registry-driven runtime
- [x] Task 7: Remove product-facing source leakage from UI read models
- [x] Task 8: Remove legacy source config coupling

## Preflight

| Item | Result |
|------|--------|
| Design spec read | Done |
| Implementation plan read | Done |
| config.py read | Done — 10 active sources, type-specific config arrays |
| scheduler.py read | Done — reads ACTIVE_SOURCES, maps to runner methods |
| db/models.py read | Done — Article model only |
| db/migrations.py read | Done — column-add migrations for articles |
| api/routes.py read | Done — health iterates ACTIVE_SOURCES |
| api/ui_routes.py read | Done — _SOURCE_KIND/_SOURCE_WEIGHT include clawfeed |
| collectors/base.py read | Done — BaseCollector abstract class |
| All collectors read | Done — 10 collectors, each reads from config directly |
| Baseline tests | **118 passed**, 131 warnings (utcnow deprecations) |

## Execution Log

### Task 1: Add the Source Registry schema

**Status:** COMPLETE
**Commit:** `e675cec`

| Step | Action | Result |
|------|--------|--------|
| 1 | Write 9 failing tests for SourceRegistry model | ImportError — model doesn't exist |
| 2 | Add SourceRegistry model to `db/models.py` | 12 columns, 2 indexes |
| 3 | Add table-level migration to `db/migrations.py` | `_table_exists()` + conditional create |
| 4 | Fix test: `columns` → `column_names` in inspector API | Minor test fix |
| 5 | Run tests | **9 passed** |
| 6 | Full suite | **127 passed** |

**Files changed:**
- `db/models.py` — added SourceRegistry class
- `db/migrations.py` — added `_table_exists()` and source_registry table migration
- `tests/test_source_registry_model.py` — new (9 tests)

**Deviations:** Test used `idx["columns"]` but SQLAlchemy inspector returns `idx["column_names"]`. Fixed in test.

---

### Task 2: Add the source registry service layer

**Status:** COMPLETE
**Commit:** `b75032c`

| Step | Action | Result |
|------|--------|--------|
| 1 | Write 11 failing tests for service functions | ModuleNotFoundError |
| 2 | Create `sources/__init__.py` and `sources/registry.py` | 5 service functions |
| 3 | Run tests | **11 passed** |
| 4 | Full suite | **138 passed** |

**Files changed:**
- `sources/__init__.py` — new package
- `sources/registry.py` — list_active_sources, list_all_sources, get_source_by_key, upsert_source, retire_source
- `tests/test_source_registry_service.py` — new (11 tests)

**Deviations:** None.

---

### Post-review fix: three service-layer bugs

**Status:** COMPLETE
**Commit:** `6fe7af8`
**Triggered by:** User code review of Batch 1

| Bug | Root cause | Fix |
|-----|-----------|-----|
| Partial update erases config | `payload.get("config", {})` always produces a value | Sentinel pattern — only update config_json when `config` key is present |
| Non-dict config produces invalid JSON | `str(config_raw)` instead of `json.dumps()` | Always use `json.dumps()` via `_serialize_config()` |
| Active source retains stale retired_at | `upsert_source` never clears `retired_at` on reactivation | Clear `retired_at` when `is_active` is set to 1 |

**Files changed:**
- `sources/registry.py` — sentinel pattern, `_serialize_config()`, retired_at clearing
- `tests/test_source_registry_service.py` — 4 new regression tests (15 total)

**Tests:** 142 passed (118 baseline + 24 new)

---

### Batch 1 Complete (Tasks 1–2 + fixes)

**Tests:** 142 passed (118 baseline + 24 new)
**Commits:** 3 (e675cec, b75032c, 6fe7af8)
**No plan/code mismatches.**
**No V1 behavior changes.**

---

## Batch 2 (Tasks 3–4)

### Task 3: Seed the registry from the current config

**Status:** IN PROGRESS
**Started:** 2026-03-15

#### Normalization rules
- `clawfeed` → `social_kol`
- `github` → `github_trending`
- `webpage_monitor` → `website_monitor`
- All other source names preserved as-is

#### Source instance mapping
- `RSS_FEEDS` (47 entries) → 47 `rss` instances
- `REDDIT_SUBREDDITS` (13 entries) → 13 `reddit` instances
- `CLAWFEED_KOL_LIST` (22 handles) → 1 `social_kol` curated stream (handles in config)
- `GITHUB_RELEASE_REPOS` (4 entries) → 4 `github_release` instances
- `WEBPAGE_MONITORS` (2 entries) → 2 `website_monitor` instances
- `hackernews` → 1 instance (config includes search keywords)
- `xueqiu` → 1 instance (config includes KOL IDs)
- `yahoo_finance` → 1 instance (config includes tickers + keywords)
- `google_news` → 1 instance (config includes queries)
- `github_trending` → 1 instance (no per-instance config)

#### Steps completed

| Step | Action | Result |
|------|--------|--------|
| 1 | Write 25 failing tests for seed | ModuleNotFoundError |
| 2 | Implement `sources/seed.py` | 72 instances seeded from config |
| 3 | Wire into `db/database.py:init_db()` | Insert-only call |
| 4 | Run tests | **25 passed** |
| 5 | Full suite | **167 passed** |
| 6 | Commit | `cc8a793` |

**Files changed:**
- `sources/seed.py` — new: seed_source_registry() + per-type seed helpers
- `db/database.py` — added _seed_registry_if_needed() to init_db()
- `tests/test_source_registry_seed.py` — new (25 tests)

**Status:** COMPLETE

---

### Task 4: Add the source resolver

**Status:** COMPLETE
**Commit:** `7ac950a`

| Step | Action | Result |
|------|--------|--------|
| 1 | Write 20 failing tests for resolver | ModuleNotFoundError |
| 2 | Implement `sources/resolver.py` | URL → source_type classifier |
| 3 | Run tests | **20 passed** |
| 4 | Full suite | **187 passed** |

**Files changed:**
- `sources/resolver.py` — new: resolve_source() with Reddit, HN, GitHub, RSS, fallback
- `tests/test_source_resolver.py` — new (20 tests)

**Resolver coverage:**
- Reddit URLs → `reddit` (subreddit extraction from path)
- HN URLs → `hackernews`
- GitHub `/trending` → `github_trending`
- GitHub `/owner/repo/releases` → `github_release` (explicit releases path only)
- GitHub `/owner/repo` → `website_monitor` (generic repo, not release monitor)
- RSS/Atom pattern URLs → `rss`
- Everything else → `website_monitor` (fallback)

**No user-facing API/UI changes.** Resolver is internal-only.

---

### Post-review fix: three design issues

**Status:** COMPLETE
**Commit:** `ba61f49`
**Triggered by:** User code review of Batch 2

| Issue | Root cause | Fix |
|-------|-----------|-----|
| Seed overwrites DB state on every boot | `upsert_source()` pushes config values into existing rows | `_insert_if_missing()` — skip if key exists |
| social_kol at wrong granularity (one row per handle) | Copied old account-level model into V2 | One curated stream record with handles list in config |
| Generic GitHub repo URLs classified as github_release | `/owner/repo` matched without requiring `/releases` | Only match explicit `/releases` path |

**Files changed:**
- `sources/seed.py` — insert-only via `_insert_if_missing()`, social_kol single stream
- `sources/resolver.py` — require `/releases` in path for github_release
- `tests/test_source_registry_seed.py` — updated for stream model, added DB-edit survival test
- `tests/test_source_resolver.py` — updated generic repo URL expectation

**Tests:** 189 passed (118 baseline + 71 new)

---

### Cleanup: dead code + docstring

**Commit:** `6fa07cc`
- Removed unused `_normalize_type()` from seed.py
- Fixed `_seed_registry_if_needed()` docstring accuracy

---

### Batch 2 Complete (Tasks 3–4 + fixes + cleanup)

**Tests:** 189 passed (118 baseline + 71 new)
**Commits:** 5 (cc8a793, 7ac950a, ba61f49, 6fa07cc)
**No plan/code mismatches.**
**No V1 behavior changes — runtime still reads config.ACTIVE_SOURCES.**

---

## Batch 3 (Tasks 5–6)

### Task 5: Introduce adapter contracts keyed by source type

**Status:** COMPLETE
**Commit:** `3368713`

| Step | Action | Result |
|------|--------|--------|
| 1 | Write 10 failing tests for adapters | ModuleNotFoundError |
| 2 | Implement `sources/adapters.py` | 10 adapter functions + dispatch |
| 3 | Run tests | **10 passed** |
| 4 | Full suite | **199 passed** |

**Files changed:**
- `sources/adapters.py` — new: collect_from_source(), get_adapter(), 10 per-type adapters
- `tests/test_source_adapters.py` — new (10 tests)

---

### Task 6: Migrate scheduler and health to registry-driven runtime

**Status:** COMPLETE
**Commit:** `4b90fa4`

| Step | Action | Result |
|------|--------|--------|
| 1 | Write 9 registry-driven scheduler/health tests | All pass (registry layer already supports) |
| 2 | Rewrite `scheduler.py` — registry-driven `_register_jobs` + `_run_source_type` | Removed all static runner methods |
| 3 | Migrate `api/routes.py` health to use `list_active_sources()` | Added `_V2_TO_LEGACY_SOURCE` mapping |
| 4 | Migrate `api/ui_routes.py` `_build_source_health`, `get_sources`, `get_source_detail` | All registry-driven |
| 5 | Update `test_health_active_sources.py` for registry-driven health | 4 tests |
| 6 | Update `test_ui_regressions.py` for v2 source types | 3 tests updated |
| 7 | Full suite | **209 passed** |

**Files changed:**
- `scheduler.py` — complete rewrite: registry-driven dispatch via adapters
- `api/routes.py` — health reads from registry, maps v2→legacy for DB queries
- `api/ui_routes.py` — sources/health endpoints migrated from config to registry
- `tests/test_health_active_sources.py` — rewritten for registry
- `tests/test_source_registry_scheduler.py` — new (9 tests)
- `tests/test_ui_regressions.py` — updated 3 tests for v2 type names

**Key design decisions:**
- One APScheduler job per source_type (not per instance) — matches V1 behavior
- `_V2_TO_LEGACY_SOURCE` maps v2 types to legacy article.source DB values
- `_ArticleSaver` wraps BaseCollector.save() for adapter-produced articles

---

### Post-review fix: three consistency issues

**Status:** COMPLETE
**Commit:** `3fc60a1`
**Triggered by:** User code review of Batch 3

| Issue | Root cause | Fix |
|-------|-----------|-----|
| social_kol adapter ignores registry handles | `_adapt_social_kol` called `collect()` without config | Reads `config.handles`, filters articles post-collection |
| Feed filter silently wrong for V2 names | `Article.source == source` without V2→legacy mapping | Added `_legacy_source_name()` call in feed filter |
| `_SOURCE_KIND`/`_SOURCE_WEIGHT` missing V2 names | Only legacy names in maps | Added V2 names as primary, kept legacy as fallback |

**Files changed:**
- `sources/adapters.py` — social_kol adapter uses registry handles
- `api/ui_routes.py` — V2 names in maps, legacy mapping in feed filter

**Tests:** 209 passed

---

### Fix: blank-author bypass in social_kol filter

**Commit:** `3bdf366`
- Blank/None author no longer bypasses curated-handle filter
- Regression test covers blank, None, and non-configured authors

**Tests:** 210 passed

---

### Batch 3 Complete (Tasks 5–6 + fixes)

**Tests:** 210 passed (118 baseline + 92 new)
**Commits:** 5 (3368713, 4b90fa4, 6fa07cc, 3fc60a1, 3bdf366)
**Runtime behavior changed:** scheduler and health now registry-driven.
**Legacy compat:** `_V2_TO_LEGACY_SOURCE` ensures existing articles still queryable.
**Source-kind/weight maps:** Both V2 and legacy names resolve correctly.

---

## Batch 4 (Tasks 7–8)

### Task 7: Remove product-facing source leakage from UI read models

**Status:** COMPLETE
**Commit:** `e440513`

| Step | Action | Result |
|------|--------|--------|
| 1 | Write 11 source-hidden contract tests | All pass (V2 migration already cleaned leakage) |
| 2 | Verify no `clawfeed` in frontend code | Clean |
| 3 | Full suite | **221 passed** |

**Files changed:**
- `tests/test_ui_source_hidden_semantics.py` — new (11 tests)

Backend tests passed immediately (earlier batches already migrated API contracts).

**Post-review:** Frontend still exposed sources in primary UI.
**Commit:** `698065c`

| Change | File | Detail |
|--------|------|--------|
| Remove Sources nav section | `Sidebar.tsx` | No more source list or `/sources/:name` links |
| Replace "Sources" with "Pipeline" | `ContextRail.tsx` | Aggregate health dots + ok/total count, no source names |
| Preserve `/sources/:name` route | `App.tsx` | Internal/debug path, not linked from primary nav |

**Frontend build:** Clean (tsc + vite)

---

### Task 8: Remove legacy source config coupling

**Status:** COMPLETE
**Commit:** `6d12b57`

| Step | Action | Result |
|------|--------|--------|
| 1 | Write 11 parity tests | All pass |
| 2 | Mark `config.ACTIVE_SOURCES` as seed-only bootstrap | Comment updated |
| 3 | Rewrite `CLAUDE.md` for V2 architecture | Done |
| 4 | Full suite | **232 passed** |
| 5 | Frontend build | Clean (tsc + vite) |

**Files changed:**
- `config.py` — ACTIVE_SOURCES comment updated to seed-only
- `CLAUDE.md` — rewritten for V2 registry-driven architecture
- `tests/test_source_registry_parity.py` — new (11 tests)

**Legacy config dependencies removed from runtime:**
- `scheduler.py` — no longer references `config.ACTIVE_SOURCES`
- `api/routes.py` health — reads from registry, not config
- `api/ui_routes.py` — all source endpoints registry-driven

---

### Batch 4 Complete (Tasks 7–8 + frontend fix)

**Tests:** 232 passed (118 baseline + 114 new)
**Commits:** 3 (e440513, 6d12b57, 698065c)
**Frontend build:** Clean (tsc + vite)
**All 8 tasks complete.**

---

## Final Verification

**Date:** 2026-03-15
**Branch:** `feature/source-architecture-v2`
**Worktree:** `.worktrees/source-arch-v2`

### Test Results

- **Backend:** 232 passed, 153 warnings (all `datetime.utcnow()` deprecations)
- **Frontend:** tsc --noEmit clean, vite build clean (253 kB JS, 17 kB CSS)
- **Total commits:** 14

### All Changed Files (25 files, +2415 / -291 lines)

| File | Change |
|------|--------|
| `db/models.py` | Added `SourceRegistry` model |
| `db/migrations.py` | Added `_table_exists()` + source_registry table migration |
| `db/database.py` | Added `_seed_registry_if_needed()` to `init_db()` |
| `sources/__init__.py` | New package |
| `sources/registry.py` | New: CRUD service (list/get/upsert/retire) |
| `sources/seed.py` | New: insert-only seed from legacy config |
| `sources/resolver.py` | New: URL → source_type classifier |
| `sources/adapters.py` | New: source-type adapter dispatch |
| `scheduler.py` | Rewritten: registry-driven, adapter-based dispatch |
| `api/routes.py` | Health migrated to registry + `_V2_TO_LEGACY_SOURCE` |
| `api/ui_routes.py` | Sources/health/feed migrated to registry, V2 names in maps |
| `config.py` | `ACTIVE_SOURCES` comment updated to seed-only |
| `CLAUDE.md` | Rewritten for V2 architecture |
| `frontend/src/components/Sidebar.tsx` | Removed Sources nav section |
| `frontend/src/components/ContextRail.tsx` | Replaced Sources panel with Pipeline aggregate |
| `tests/test_source_registry_model.py` | New (9 tests) |
| `tests/test_source_registry_service.py` | New (15 tests) |
| `tests/test_source_registry_seed.py` | New (27 tests) |
| `tests/test_source_resolver.py` | New (20 tests) |
| `tests/test_source_adapters.py` | New (11 tests) |
| `tests/test_source_registry_scheduler.py` | New (9 tests) |
| `tests/test_health_active_sources.py` | Rewritten for registry (4 tests) |
| `tests/test_ui_regressions.py` | Updated for V2 names (3 tests changed) |
| `tests/test_ui_source_hidden_semantics.py` | New (11 tests) |
| `tests/test_source_registry_parity.py` | New (11 tests) |

### Explicit Verifications

| Check | Result |
|-------|--------|
| No primary UI endpoint depends on `config.ACTIVE_SOURCES` | Verified (3 source-inspection tests) |
| No primary UI endpoint surfaces `clawfeed` | Verified (5 contract tests) |
| No frontend navigation exposes source lists | Verified (Sidebar Sources section removed) |
| No frontend shows raw source names in primary UI | Verified (ContextRail shows Pipeline aggregate) |
| Scheduler/health work when registry differs from legacy config | Verified (registry is sole runtime truth) |
| Existing article history readable via mapping | Verified (`_V2_TO_LEGACY_SOURCE` shim) |

### Remaining Intentional Compatibility Shims

| Shim | Location | Purpose | Removal condition |
|------|----------|---------|-------------------|
| `_V2_TO_LEGACY_SOURCE` | `api/routes.py` | Maps V2 types to legacy `article.source` DB values | When new articles are stored with V2 source names |
| `_legacy_source_name()` | `api/routes.py` | Used by health, feed, sources for DB queries | Same as above |
| Legacy names in `_SOURCE_KIND`/`_SOURCE_WEIGHT` | `api/ui_routes.py` | Existing article rows carry legacy source values | Same as above |
| `config.ACTIVE_SOURCES` | `config.py` | Seed-only bootstrap data for `sources/seed.py` | When seed reads from external config or is removed |
| `collectors/clawfeed.py` | unchanged | Collector file name is implementation detail | When CLI is renamed or replaced |
| `/sources/:name` route | `App.tsx` | Preserved as internal/debug path (not linked) | When admin UI is built |

### Residual Non-Blockers

- `datetime.utcnow()` deprecation warnings (153) — pre-existing, not introduced by V2
- ClawFeed CLI does not accept per-handle args — adapter filters post-collection
