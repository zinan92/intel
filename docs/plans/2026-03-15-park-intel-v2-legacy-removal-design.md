# Park Intel V2.1 — Legacy Removal and Source Canonicalization

**Status:** Proposed  
**Date:** 2026-03-15  
**Applies to:** `/Users/wendy/work/trading-co/park-intel`

## Intent

Remove the remaining V2 compatibility layer so the runtime, storage, and internal source model all use the same canonical source names and registry-driven architecture.

This is explicitly a cleanup/refactor phase, not a user-facing feature phase.

## Why now

V2 established the registry as the runtime source of truth, but several legacy bridges remain:

- `Article.source` still stores legacy names such as `clawfeed`, `github`, and `webpage_monitor`
- `api/routes.py` still relies on `_V2_TO_LEGACY_SOURCE` and `_legacy_source_name()`
- `api/ui_routes.py` still carries legacy keys in `_SOURCE_KIND` and `_SOURCE_WEIGHT`
- `config.ACTIVE_SOURCES` still exists in a legacy-shaped format as seed bootstrap data
- `collectors/clawfeed.py` still exposes an implementation-oriented file name

These shims keep the system working, but they blur the architecture. The codebase is now ready for a one-time canonicalization pass because:

- the project is not yet in production
- temporary breakage during implementation is acceptable
- data migration is lower cost now than after further feature work

## Design goal

After this phase:

1. `SourceRegistry.source_type` is the only canonical source naming system
2. `Article.source` stores canonical V2 source names
3. runtime code does not need V2-to-legacy source mapping
4. UI read models do not carry legacy source-name compatibility branches
5. seed/bootstrap input uses canonical V2 names
6. implementation-oriented names are minimized in code structure

## Canonical source names

The canonical internal source names are:

- `rss`
- `reddit`
- `github_release`
- `website_monitor`
- `social_kol`
- `hackernews`
- `xueqiu`
- `yahoo_finance`
- `google_news`
- `github_trending`

The following names become invalid as runtime/storage names:

- `clawfeed`
- `github`
- `webpage_monitor`

## Non-goals

- redesign the frontend product shell
- add new source types
- add user-configurable source management
- solve the underlying ClawFeed CLI limitations
- remove the internal `/sources/:name` debug route unless it blocks canonicalization

## Required outcomes

### 1. Article storage is canonical

All new writes to `articles.source` must use canonical V2 names only.

Historical rows with legacy names must be rewritten in place:

- `clawfeed` -> `social_kol`
- `github` -> `github_trending`
- `webpage_monitor` -> `website_monitor`

The target state is that no row in `articles.source` uses those three legacy names.

### 2. Mapping shim is removed

The following should be deleted:

- `_V2_TO_LEGACY_SOURCE`
- `_legacy_source_name()`

Any query or runtime path that still depends on them should instead operate directly on canonical `Article.source` values.

### 3. UI metadata tables are canonical

`api/ui_routes.py` should only contain canonical keys in:

- `_SOURCE_KIND`
- `_SOURCE_WEIGHT`

Legacy fallback entries should be removed once article storage is canonicalized.

### 4. Seed/bootstrap is canonical

`config.ACTIVE_SOURCES` should no longer be the source bootstrap shape if it continues to encode legacy names.

The bootstrap layer should be replaced by one canonical V2-oriented definition, for example:

- `SOURCE_BOOTSTRAP`
- `SOURCE_REGISTRY_BOOTSTRAP`
- or a dedicated module under `sources/`

The important constraint is that bootstrap data uses canonical names only.

### 5. File/module naming becomes clearer

Where low-risk, implementation-oriented names should be aligned with domain-oriented naming.

Minimum target:

- remove code comments and runtime messages that treat `clawfeed` as the source identity

Preferred target if low-risk:

- rename `collectors/clawfeed.py` to a more domain-oriented module such as `collectors/social_kol.py`

If the module rename is too disruptive for this phase, it may be deferred, but runtime naming must still be canonical.

## Migration strategy

Because the system is not yet in production, prefer a direct, explicit migration over long-lived compatibility code.

Recommended migration order:

1. make all writers emit canonical source names
2. add a one-time data migration for existing rows
3. verify there are zero legacy `Article.source` values left
4. remove mapping shims
5. remove legacy fallback entries from UI metadata maps
6. replace legacy bootstrap config with canonical bootstrap data

## Data migration contract

The migration must be idempotent and safe to rerun.

It should:

- update `articles.source` values in place
- report counts per rewritten source name
- leave unrelated rows untouched

It must not:

- delete articles
- rewrite `source_id` unless required by a proven dedup conflict
- alter user-facing content fields

## Verification gates

This phase is complete only if all of the following are true:

1. no `Article.source` rows remain with `clawfeed`, `github`, or `webpage_monitor`
2. `_V2_TO_LEGACY_SOURCE` and `_legacy_source_name()` are gone
3. `_SOURCE_KIND` and `_SOURCE_WEIGHT` contain canonical keys only
4. scheduler, health, feed, sources, and source detail work without legacy source-name translation
5. bootstrap/seed input uses canonical source names only
6. full backend test suite passes
7. frontend build passes

## Risks

### Canonicalization regression

Changing article source names can break feed filters, health, source pages, and tests if any hidden assumptions remain.

Mitigation:

- write explicit migration and parity tests first
- verify endpoints before removing shims

### Seed/runtime drift during transition

Changing bootstrap definitions can break seeding if source names diverge from scheduler expectations.

Mitigation:

- migrate bootstrap data and seed logic in the same batch

### Over-cleanup

Trying to rename every implementation detail in one pass can slow down the high-value cleanup.

Mitigation:

- prioritize storage/runtime canonicalization first
- treat module renames as secondary unless low-risk

## Success definition

Park Intel should emerge from this phase with one clean internal source language. Registry, storage, runtime, and UI read models should all agree on the same canonical source names, and no compatibility translation layer should remain in the main execution path.
