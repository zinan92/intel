# Park Intel V2.1 — Legacy Removal and Source Canonicalization Plan

**Status:** Ready for execution  
**Date:** 2026-03-15  
**Depends on:** merged V2 registry-driven architecture on `main`

## Execution rules

- work on a new feature branch
- keep changes incremental and reviewable
- remove compatibility shims only after canonical storage is in place
- prefer direct migration over long-lived dual-path logic
- do not touch unrelated frontend/product polish in this phase

## Success criteria

- `articles.source` stores canonical V2 names only
- no runtime path depends on `_V2_TO_LEGACY_SOURCE` or `_legacy_source_name()`
- no UI metadata table carries legacy source keys
- seed/bootstrap input uses canonical names only
- backend tests pass
- frontend build passes

## Batch 1 — Canonical write path + migration tests

### Task 1

Write failing tests that define the target end state:

- newly collected `social_kol` articles are saved with `source="social_kol"`
- newly collected GitHub trending articles are saved with `source="github_trending"`
- newly collected website monitor articles are saved with `source="website_monitor"`
- migration rewrites legacy `articles.source` values in place
- migration is idempotent

Suggested test files:

- `tests/test_source_canonicalization.py`
- `tests/test_article_source_migration.py`

### Task 2

Update collectors/adapter save paths so new writes use canonical V2 names.

Likely touchpoints:

- `sources/adapters.py`
- any collector that still emits legacy `source`
- any saver path that relies on collector `.source`

Important:

- fix write-time naming first
- do not remove read-time shims in this batch

### Task 3

Add an idempotent migration for `articles.source` canonicalization.

Expected behavior:

- `clawfeed` -> `social_kol`
- `github` -> `github_trending`
- `webpage_monitor` -> `website_monitor`

Likely touchpoints:

- `db/migrations.py`
- migration tests

Verification:

- targeted migration tests pass
- existing article queries still work with shims in place

## Batch 2 — Remove runtime source-name translation

### Task 4

Once migration and canonical writes are in place, remove source-name translation from runtime paths.

Delete:

- `_V2_TO_LEGACY_SOURCE`
- `_legacy_source_name()`

Update affected code:

- `api/routes.py`
- `api/ui_routes.py`

All queries should operate directly on canonical `Article.source` values.

### Task 5

Remove legacy fallback keys from UI metadata maps:

- `_SOURCE_KIND`
- `_SOURCE_WEIGHT`

Only canonical keys should remain.

Verification:

- feed items still compute `source_kind` correctly
- source pages and source health still render correctly

## Batch 3 — Canonical bootstrap/seed

### Task 6

Replace `config.ACTIVE_SOURCES` as the bootstrap input if it still encodes legacy source names.

Target:

- one canonical bootstrap definition using V2 names only

Acceptable shapes:

- new `SOURCE_BOOTSTRAP` in `config.py`
- or dedicated bootstrap module under `sources/`

Update:

- `sources/seed.py`
- related tests

Verification:

- seeding still creates the expected registry rows
- no bootstrap data contains `clawfeed`, `github`, or `webpage_monitor`

## Batch 4 — Final cleanup and optional module rename

### Task 7

Clean remaining implementation-language leakage from comments, docs, and logs.

Required:

- runtime logs should describe `social_kol`, not `clawfeed` as the source identity

Optional if low-risk:

- rename `collectors/clawfeed.py` to `collectors/social_kol.py`
- update imports and tests accordingly

If the rename causes disproportionate churn, defer it and document the reason.

### Task 8

Final parity and regression sweep.

Required checks:

- search the repo for:
  - `_V2_TO_LEGACY_SOURCE`
  - `_legacy_source_name`
  - legacy source keys in runtime maps
- verify there are no runtime references left except intentionally deferred implementation-detail files
- update docs/execution log

## Verification commands

Run after each meaningful batch:

```bash
./.venv/bin/pytest -q
```

Frontend verification at least at the end of Batch 2 and final wrap-up:

```bash
cd frontend
npm run build
```

Recommended targeted checks during execution:

```bash
./.venv/bin/pytest -q tests/test_source_canonicalization.py tests/test_article_source_migration.py
./.venv/bin/pytest -q tests/test_ui_feed_api.py tests/test_ui_regressions.py tests/test_source_registry_parity.py
```

Recommended repo search before declaring completion:

```bash
rg -n "_V2_TO_LEGACY_SOURCE|_legacy_source_name|\"clawfeed\"|\"github\"|\"webpage_monitor\"" api sources scheduler.py config.py frontend/src tests
```

## Expected deliverables

- canonical article source storage
- migration for legacy article rows
- removed runtime mapping shim
- canonical bootstrap definition
- updated tests and execution log
- passing backend tests
- passing frontend build

## Handoff note for coder agent

This phase deliberately prioritizes architectural cleanliness over short-term compatibility. The project is not yet in production, so prefer direct canonicalization over preserving old internal naming conventions.
