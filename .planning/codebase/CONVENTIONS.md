# Coding Conventions

**Analysis Date:** 2026-03-31

## Naming Patterns

**Files:**
- Python modules: `snake_case` (e.g., `base.py`, `conftest.py`, `test_event_aggregation.py`)
- TypeScript components: `PascalCase` (e.g., `FeedCard.tsx`, `ItemDrawer.tsx`)
- TypeScript utilities: `camelCase` (e.g., `client.ts`, `api.ts`)

**Functions:**
- Python functions: `snake_case` (e.g., `tag_article()`, `run_aggregation()`, `_configure_logging()`)
- Private functions: Leading underscore (e.g., `_no_scheduler()`, `_make_article()`)
- React components: `PascalCase` and exported as function (e.g., `export function FeedPage()`)
- React hooks in API client: `camelCase` (e.g., `feedParams`, `buildQuery`)

**Variables:**
- Python: `snake_case` throughout (e.g., `saved_count`, `db_session`, `source_id`)
- TypeScript: `camelCase` for variables and properties (e.g., `activeUser`, `hasNextPage`, `staleTime`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `HN_MIN_SCORE`, `API_HOST`, `WINDOW_OPTIONS`)
- Type unions: `snake_case_label` for status strings (e.g., `"fading"`, `"no_data"`, `"ok"`)

**Types:**
- TypeScript interfaces: `PascalCase` (e.g., `FeedItem`, `ItemDetail`, `FeedParams`)
- Python dataclass/model names: `PascalCase` (e.g., `Article`, `SourceRegistry`, `Event`)
- Database table names: `snake_case` (e.g., `articles`, `source_registry`, `events`)

## Code Style

**Formatting:**
- TypeScript: Vite project with Tailwind CSS and component co-location
- Python: PEP 8 compliant, no explicit formatter configured (rely on linter)
- HTML/JSX: Four-space indentation in components

**Linting:**
- TypeScript: `tsc --noEmit` type checking, `"strict": true` in tsconfig
- Python: No explicit linter configured; reliance on runtime and test execution
- Type checking: `tsconfig.json` enforces strict mode with `noUnusedLocals` and `noUnusedParameters`

**Imports:**
- TypeScript: Import type utilities from API at top (e.g., `import type { FeedItem } from "../types/api"`)
- Python: Grouped by standard library, third-party, local; no explicit isort configuration
- Python functions: Direct function imports where needed (e.g., `from tagging import tag_article, extract_tickers`)

## Import Organization

**Order:**
1. Standard library imports (e.g., `import json`, `import logging`)
2. Third-party imports (e.g., `from sqlalchemy import`, `from fastapi import`, `import pytest`)
3. Local imports (e.g., `from db.models import`, `from config import`)

**Path Aliases:**
- TypeScript: `@/*` maps to `src/` (configured in `tsconfig.json` baseUrl/paths)
- Python: Absolute imports from project root (e.g., `from db.models import Article`)

**Explicit Typing:**
- TypeScript: `type` imports for interface-only imports (e.g., `import type { FeedItem }`)
- Python: Type annotations on all function signatures (e.g., `def collect(self) -> list[dict[str, Any]]`)

## Error Handling

**Patterns:**

Python:
- Try-catch blocks at critical save points with `IntegrityError` for dedup (`BaseCollector.save()`)
- Rollback on any exception, log with context (see `collectors/base.py` lines 71-76)
- Functions that may fail log exceptions with `logger.exception()` for full traceback
- Network/parsing errors caught gracefully in collectors (e.g., `test_rss_broken_feed_skipped_gracefully`)

TypeScript:
- API client wraps fetch in try-catch with error message including status code (see `api/client.ts` lines 18-24)
- Async/await pattern used throughout; throw on HTTP non-200 response
- React components show loading and error states (see `FeedPage.tsx` lines 77-80)

**Error Messages:**
- Python: Context-aware messages with source name (e.g., `"[%s] Saved %d new articles"` with source and count)
- TypeScript: Include HTTP status in error (e.g., `"API error 404: /api/ui/items/123"`)

## Logging

**Framework:** Python `logging` module with `getLogger(__name__)` pattern

**Patterns:**
- Module-level logger: `logger = logging.getLogger(__name__)` at top of each module
- Log levels used: `INFO` (general flow), `DEBUG` (dedup skipped), `exception()` (errors with traceback)
- Rotating file handler: 10MB max per file, 5 backups, UTF-8 encoding (see `main.py` lines 28-35)
- No console logging in main app; all goes to `logs/park-intel.log`

**Examples:**
- `logger.info("[%s] Saved %d new articles (of %d fetched)", self.source, saved, len(articles))`
- `logger.debug("Duplicate skipped: %s", data.get("source_id"))`
- `logger.exception("Error saving article %s for %s", data.get("source_id"), self.source)`

## Comments

**When to Comment:**
- Complex business logic (e.g., signal score calculation, event clustering window)
- Non-obvious dedup logic or data transformations
- Workarounds or temporary code (prefixed with `# TODO:` or `# HACK:`)
- API contract changes (docstrings on pydantic models)

**JSDoc/TSDoc:**
- Python docstrings on public functions and classes (e.g., `BaseCollector.collect()` with return type)
- TypeScript: Inline JSDoc rarely used; types in interfaces provide documentation
- Function-level comments explain intent, not what the code does

**Example (Python):**
```python
def save(self, articles: list[dict[str, Any]]) -> int:
    """Save articles to DB with dedup. Returns count of new articles saved."""
```

## Function Design

**Size:** 
- Target <50 lines per function
- Helper functions extracted for clarity (e.g., `_make_article()` factory in tests)
- Collectors limit per-source logic to a single `collect()` method

**Parameters:**
- Type annotations on all parameters (Python/TypeScript)
- Avoid >4 parameters; use dataclass/interface for complex arguments
- Optional parameters use defaults or `| None` in Python, `?` in TypeScript

**Return Values:**
- Explicit return type annotations (e.g., `-> int`, `-> list[dict]`)
- Python functions return counts or query results; no bare `None` on success paths
- TypeScript components return JSX; API methods return typed Promises

**Example:**
```python
def _make_article(
    session: Session,
    source: str,
    narrative_tags: list[str],
    relevance: int = 3,
    hours_ago: float = 1.0,
) -> Article:
```

## Module Design

**Exports:**
- Python: Collectors inherit `BaseCollector` with abstract `collect()` method
- TypeScript: Named exports for all components and utilities (e.g., `export function FeedCard()`)
- API client: Single default export `api` object with method properties

**Barrel Files:**
- Python: Not used; direct imports from modules
- TypeScript: No barrel files; direct path imports (e.g., `import { FeedCard } from "../components/FeedCard"`)

**File Cohesion:**
- Each collector in `collectors/` is self-contained (e.g., `rss.py`, `reddit.py`)
- Models grouped in `db/models.py` and `events/models.py`
- API routes grouped by domain (`routes.py`, `ui_routes.py`, `event_routes.py`)
- React pages in `pages/`, components in `components/`, types in `types/`

---

*Convention analysis: 2026-03-31*
