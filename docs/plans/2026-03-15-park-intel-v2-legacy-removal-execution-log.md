# Park Intel V2.1 — Legacy Removal Execution Log

**Branch:** `v2.1/legacy-removal-canonicalization`
**Started:** 2026-03-15
**Plan:** `docs/plans/2026-03-15-park-intel-v2-legacy-removal.md`

## Checklist

### Batch 1 — Canonical write path + migration tests
- [x] Task 1: Write failing tests for target end state
- [x] Task 2: Update collectors/adapter save paths for canonical V2 names
- [x] Task 3: Add idempotent migration for `articles.source` canonicalization

### Batch 2 — Remove runtime source-name translation
- [x] Task 4: Remove `_V2_TO_LEGACY_SOURCE` and `_legacy_source_name()`
- [x] Task 5: Remove legacy fallback keys from `_SOURCE_KIND` and `_SOURCE_WEIGHT`

### Batch 3 — Canonical bootstrap/seed
- [x] Task 6: Replace `config.ACTIVE_SOURCES` legacy names with canonical V2 names

### Batch 4 — Final cleanup and optional module rename
- [x] Task 7: Clean implementation-language leakage (logs, comments, optional file rename)
- [x] Task 8: Final parity and regression sweep

## Baseline

- **Date:** 2026-03-15
- **Tests:** 231 passed, 1 failed (pre-existing flaky `test_health_no_data_status_for_fresh_source`)
- **Branch created from:** `main`

## Preflight Findings

### Collector source attributes (write path)
- `collectors/clawfeed.py:21` → `source = "clawfeed"` (legacy)
- `collectors/github_trending.py:18` → `source = "github"` (legacy)
- `collectors/webpage_monitor.py:48` → `source = "webpage_monitor"` (legacy)
- All collectors set `"source": self.source` in article dicts
- `base.py:48` uses `data.get("source", self.source)` — dict value overrides class attr
- Therefore: fixing collector class `source` attributes fixes the write path

### Runtime shims to remove
- `api/routes.py:34-43` — `_V2_TO_LEGACY_SOURCE`, `_legacy_source_name()`
- `api/ui_routes.py:44-46,70-72` — legacy keys in `_SOURCE_KIND`, `_SOURCE_WEIGHT`
- `api/ui_routes.py:229,238,254,303,506,513,529,548,562` — imports/calls to `_legacy_source_name`

### Bootstrap (config.py)
- `ACTIVE_SOURCES` lines 88,91,94 use `clawfeed`, `github`, `webpage_monitor`
- `sources/seed.py:29-33` has `_SOURCE_TYPE_MAP` for normalization + reverse-mapping

---

## Execution Log

### Batch 1 — Canonical write path + migration tests

#### Task 1 — Write failing tests (RED)
- **Timestamp:** 2026-03-15
- **Files created:**
  - `tests/test_source_canonicalization.py` — 6 tests for collector source attrs + article dicts + no-legacy sweep
  - `tests/test_article_source_migration.py` — 9 tests for migration (rewrite, idempotent, no-delete, no-alter)
- **Result:** 6 failed (canonicalization), migration tests errored on missing `migrate_article_sources`
- **Status:** RED confirmed

#### Task 2 — Fix collector source attributes (GREEN)
- **Timestamp:** 2026-03-15
- **Files changed:**
  - `collectors/clawfeed.py:21` — `source = "clawfeed"` → `"social_kol"`
  - `collectors/github_trending.py:18` — `source = "github"` → `"github_trending"`
  - `collectors/webpage_monitor.py:48` — `source = "webpage_monitor"` → `"website_monitor"`
  - `tests/test_clawfeed.py:124` — updated assertion `"clawfeed"` → `"social_kol"`
  - `tests/test_webpage_monitor.py:155` — updated assertion `"webpage_monitor"` → `"website_monitor"`
- **Tests run:** `pytest -q` full suite
- **Result:** 246 passed, 1 failed (pre-existing)

#### Task 3 — Add idempotent migration
- **Timestamp:** 2026-03-15
- **Files changed:**
  - `db/migrations.py` — added `_LEGACY_TO_CANONICAL` dict + `migrate_article_sources()` function
- **Tests run:** `pytest -q tests/test_article_source_migration.py` — 9 passed
- **Result:** GREEN confirmed

#### Batch 1 Review Feedback — Migration wiring + tautological test fix
- **Timestamp:** 2026-03-15
- **Issue 1:** `migrate_article_sources()` was dead code — not called from any startup path
  - **Fix:** Added `_canonicalize_article_sources()` to `db/database.py`, called from `init_db()` after seed
  - **Files changed:** `db/database.py` (added helper + wired into `init_db`)
  - **Test added:** `TestMigrationWiredToStartup::test_init_db_canonicalizes_legacy_articles` in `test_article_source_migration.py`
- **Issue 2:** `test_github_trending_articles_have_canonical_source` was tautological — mocked `collect()` itself
  - **Fix:** Now mocks `_search_recent_repos` + `_get_readme_content`, letting the real `collect()` build article dicts using `self.source`
  - **Files changed:** `tests/test_source_canonicalization.py`
- **Tests run:** `pytest -q` full suite
- **Result:** 247 passed, 1 failed (pre-existing flaky)

#### Batch 1 Summary
- **Total tests:** 247 passed, 1 failed (pre-existing flaky)
- **New tests added:** 16 (6 canonicalization + 10 migration)
- **Regressions found and fixed:** 2 (existing tests asserting legacy names)
- **Deviation from plan:** migration wiring was not in the original plan but required for correctness

### Batch 2 — Remove runtime source-name translation

#### Task 4 — Remove `_V2_TO_LEGACY_SOURCE` and `_legacy_source_name()`
- **Timestamp:** 2026-03-15
- **Files changed:**
  - `api/routes.py` — deleted `_V2_TO_LEGACY_SOURCE` dict (lines 32-38), `_legacy_source_name()` function (lines 41-43), updated health endpoint to query by `source_type` directly
  - `api/ui_routes.py` — removed all 6 `from api.routes import _legacy_source_name` imports and all legacy-name translation calls in: `_build_source_health`, `get_feed`, `get_sources`, `get_source_detail`
- **Callers updated:** health, feed source filter, source_health context, sources list, source detail — all now query `Article.source` directly by canonical V2 name

#### Task 5 — Remove legacy fallback keys from `_SOURCE_KIND` and `_SOURCE_WEIGHT`
- **Timestamp:** 2026-03-15
- **Files changed:**
  - `api/ui_routes.py` — removed `"webpage_monitor"`, `"github"`, `"clawfeed"` from `_SOURCE_KIND` and `_SOURCE_WEIGHT`
- **Verification:**
  - `grep` for `_legacy_source_name` and `_V2_TO_LEGACY_SOURCE` in `api/` → zero matches
  - `grep` for `"clawfeed"`, `"github"`, `"webpage_monitor"` in `api/` → zero matches
- **Tests run:** `pytest -q` full suite → 247 passed, 1 failed (pre-existing flaky)
- **Frontend build:** `npm run build` → success (153 modules, 706ms)

#### Batch 2 Review Feedback — Fail-fast canonicalization
- **Timestamp:** 2026-03-15
- **Issue:** `_canonicalize_article_sources()` swallowed exceptions, but with shims removed, a failed migration means historical data is silently invisible
- **Fix:** Removed `except Exception` catch in `db/database.py:54` — exceptions now propagate through `init_db()`, preventing app startup with uncanonicalized data
- **Files changed:** `db/database.py`
- **Test added:** `TestMigrationWiredToStartup::test_init_db_fails_fast_if_canonicalization_errors` — patches `migrate_article_sources` to raise, asserts `init_db()` propagates the exception
- **Tests run:** `pytest -q` full suite → 248 passed, 1 failed (pre-existing flaky)

#### Batch 2 Summary
- **Total tests:** 248 passed, 1 failed (pre-existing flaky)
- **Shims removed:** `_V2_TO_LEGACY_SOURCE`, `_legacy_source_name()`, 3 legacy keys each in `_SOURCE_KIND` and `_SOURCE_WEIGHT`
- **Invariant enforced:** canonicalization failure is now fatal at startup
- **No regressions introduced**

### Batch 3 — Canonical bootstrap/seed

#### Task 6 — Canonicalize bootstrap config
- **Timestamp:** 2026-03-15
- **Files changed:**
  - `config.py` — renamed `ACTIVE_SOURCES` → `SOURCE_BOOTSTRAP`, canonicalized 3 legacy names: `"github"` → `"github_trending"`, `"clawfeed"` → `"social_kol"`, `"webpage_monitor"` → `"website_monitor"`
  - `sources/seed.py` — removed `_SOURCE_TYPE_MAP` dict (legacy→V2 normalization, no longer needed), simplified `_interval_for_type()` to direct lookup on `cfg.SOURCE_BOOTSTRAP`, updated module docstring
- **What was removed:**
  - `_SOURCE_TYPE_MAP` — the last legacy name normalization map in the codebase
  - Reverse-mapping logic in `_interval_for_type()`
- **Verification:**
  - `grep` for `ACTIVE_SOURCES` in non-test `.py` files → zero matches
  - `grep` for `"clawfeed"`, `"github"` (bare), `"webpage_monitor"` in `config.py` → zero matches
  - `grep` for `_SOURCE_TYPE_MAP` → zero matches
- **Tests run:** `pytest -q` full suite → 248 passed, 1 failed (pre-existing flaky)

#### Batch 3 Summary
- **Total tests:** 248 passed, 1 failed (pre-existing flaky)
- **Bootstrap is now fully canonical** — no legacy source names remain in seed data
- **No deviations from plan**
- **No regressions introduced**

### Batch 4 — Final cleanup and module rename

#### Task 7 — Clean implementation-language leakage + file rename
- **Timestamp:** 2026-03-15
- **File rename:** `collectors/clawfeed.py` → `collectors/social_kol.py`
  - Class: `ClawFeedCollector` → `SocialKolCollector`
  - `source_id` prefix: `clawfeed_` → `social_kol_`
  - Log messages: `ClawFeed:` → `social_kol:`
  - Old file deleted
- **Config rename:** `config.py` `CLAWFEED_KOL_LIST` → `SOCIAL_KOL_HANDLES`
- **Docstring fixes:** `sources/seed.py` — removed "replaces clawfeed" from `_seed_social_kol` docstring, fixed "from legacy config" → "from bootstrap config" in `seed_source_registry`
- **Test data fixes:**
  - `tests/test_ui_feed_api.py:58` — `source="clawfeed"` → `"social_kol"`
  - `tests/test_ui_topics_api.py:57` — `source="clawfeed"` → `"social_kol"`
  - `tests/test_source_adapters.py` — updated mock paths and `"source"` values
- **Import updates:** `sources/adapters.py`, `collectors/__init__.py`, `scripts/run_collectors.py`, `tests/test_clawfeed.py`, `tests/test_source_canonicalization.py`, `tests/test_source_adapters.py`
- **Scripts:** `scripts/run_collectors.py` — `"clawfeed"` → `"social_kol"`, `"github"` → `"github_trending"`, `"webpage_monitor"` → `"website_monitor"`
- **Intentionally kept:** `scheduler.py:189-190` references to `clawfeed` CLI binary — this is the external tool name, not a source identity

#### Task 8 — Final parity and regression sweep
- **Timestamp:** 2026-03-15
- **Verification results:**
  - `_V2_TO_LEGACY_SOURCE` in `.py` files → **zero matches**
  - `_legacy_source_name` in `.py` files → **zero matches**
  - `_SOURCE_TYPE_MAP` in `.py` files → **zero matches**
  - `CLAWFEED_KOL_LIST` in `.py` files → **zero matches**
  - `"clawfeed"` in `api/`, `sources/`, `config.py` → **zero matches**
  - `"webpage_monitor"` in `api/`, `sources/`, `config.py` → **zero matches**
  - bare `"github"` (not `github_release`/`github_trending`) in runtime code → **zero matches**
  - `clawfeed` in `scheduler.py` → **2 matches** (external CLI binary check — intentional)
  - `collectors/clawfeed.py` → **deleted**
  - Frontend `src/` for legacy names → **zero matches**
- **Tests run:** `pytest -q` full suite → 248 passed, 1 failed (pre-existing flaky)
- **Frontend build:** `npm run build` → success (153 modules, 694ms)

---

## Final Summary

### What was implemented
1. Collector source attributes canonicalized (`social_kol`, `github_trending`, `website_monitor`)
2. Idempotent migration `migrate_article_sources()` for historical `Article.source` rows
3. Migration wired into `init_db()` startup path (fail-fast)
4. `_V2_TO_LEGACY_SOURCE` and `_legacy_source_name()` shim deleted
5. Legacy fallback keys removed from `_SOURCE_KIND` and `_SOURCE_WEIGHT`
6. `config.ACTIVE_SOURCES` renamed to `SOURCE_BOOTSTRAP` with canonical names
7. `_SOURCE_TYPE_MAP` normalization map removed from `sources/seed.py`
8. `collectors/clawfeed.py` → `collectors/social_kol.py` (class, source_id prefix, logs)
9. `config.CLAWFEED_KOL_LIST` → `config.SOCIAL_KOL_HANDLES`
10. `scripts/run_collectors.py` canonicalized

### What was verified
- No runtime path depends on `_V2_TO_LEGACY_SOURCE`
- No runtime path depends on `_legacy_source_name()`
- No canonical runtime map contains `clawfeed`, `github`, or `webpage_monitor`
- `Article.source` canonicalization runs at startup (fail-fast)
- Seeding uses canonical V2 names only
- 248 tests pass, frontend builds

### Shims removed
- `_V2_TO_LEGACY_SOURCE` (api/routes.py)
- `_legacy_source_name()` (api/routes.py)
- `_SOURCE_TYPE_MAP` (sources/seed.py)
- Legacy keys in `_SOURCE_KIND` (3 entries)
- Legacy keys in `_SOURCE_WEIGHT` (3 entries)

### Intentionally kept
- `scheduler.py:189-190` — `clawfeed` CLI binary availability check (external tool name, not source identity)
- `collectors/social_kol.py` — docstring "via the clawfeed CLI", log messages "clawfeed export failed", "Failed to parse clawfeed output", "clawfeed CLI not available", "clawfeed export timed out" (all refer to the external CLI binary, not to a source identity; the tool is genuinely called `clawfeed`)
- `db/migrations.py` `_LEGACY_TO_CANONICAL` (migration data — must know legacy names to rewrite them)
- Test files that test migration behavior (must reference legacy names as test input)

### Branch status
- **Branch:** `v2.1/legacy-removal-canonicalization`
- **Commits:** pending (not yet committed)

