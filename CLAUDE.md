# qualitative-data-pipeline (park-intel)

## Project Overview
Qualitative signal pipeline and feed-first workbench for collecting frontier-tech, macro, and market content into a structured API and local reading UI.

## Tech Stack
- **Backend**: FastAPI, SQLAlchemy 2.0, Python 3.11+
- **Database**: SQLite at `data/park_intel.db`
- **Frontend**: React 18, TypeScript, Vite, Tailwind, TanStack Query, React Router
- **Dependencies**: feedparser, requests, apscheduler, anthropic, python-dotenv, httpx

## Architecture (V2)
```
Source Registry (DB) → Adapters → Collectors (fetch) → BaseCollector.save → SQLite
                                                                              ↓
                                  LLM Tagger → relevance_score + narrative_tags → SQLite
                                                                              ↓
                                           FastAPI APIs (/api/* + /api/ui/*) → React frontend
```

### Source Architecture V2
- **Source Registry**: `source_registry` table is the single source of truth for active sources
- **Adapters**: `sources/adapters.py` bridges registry records to collectors
- **Seeding**: `sources/seed.py` populates registry from `config.py` on first run (insert-only)
- **Resolver**: `sources/resolver.py` classifies URLs into source types (internal tool)
- **Naming**: V2 uses domain-oriented names (`social_kol`, `github_trending`, `website_monitor`)
- **Naming is canonical**: `Article.source` stores V2 names directly; no legacy translation layer

### Event Aggregation
- `events/models.py` — Event + EventArticle models
- `events/aggregator.py` — Clusters articles by narrative_tag in 48h windows, runs hourly
- `api/event_routes.py` — /api/events/active, /api/events/{id}
- Signal score = source_count × avg_relevance

### User Personalization
- `users/models.py` — UserProfile with topic_weights (JSON)
- `users/service.py` — CRUD + weight validation (0.0-3.0, 13 valid topics)
- `api/user_routes.py` — /api/users CRUD
- Feed personalization via ?user= param on /api/ui/feed

### Quant Bridge
- `tagging/tickers.py` — Ticker extraction (cashtag + alias + source)
- `bridge/quant.py` — Async price snapshot from quant-data-pipeline (port 8000)
- Event detail includes price_impacts when tickers available

### Source Types (10)
`rss`, `reddit`, `hackernews`, `github_release`, `github_trending`, `website_monitor`, `social_kol`, `xueqiu`, `yahoo_finance`, `google_news`

## Key Files
- `main.py` — FastAPI app entry (port 8001)
- `config.py` — seed data for source registry, collector-specific config, env loading
- `db/models.py` — Article + SourceRegistry models
- `db/migrations.py` — Idempotent schema migrations
- `db/database.py` — Engine, session, init_db (creates tables + seeds registry)
- `sources/registry.py` — Source registry CRUD service
- `sources/adapters.py` — Source-type adapter dispatch (registry record → collector)
- `sources/seed.py` — Seed registry from bootstrap config (insert-only, runs at init)
- `sources/resolver.py` — URL → source_type classifier (internal)
- `api/routes.py` — core read APIs: health, latest, search, digest, signals, sources
- `api/ui_routes.py` — frontend read-model APIs: feed, item detail, topics, sources, search
- `scheduler.py` — Registry-driven APScheduler (one job per source_type)
- `collectors/base.py` — BaseCollector abstract class (with auto keyword tagging)
- `collectors/` — Per-type collectors (hackernews, rss, reddit, social_kol, etc.)
- `tagging/keywords.py` — Regex-based keyword tagger (13 tag categories)
- `tagging/llm.py` — Claude Sonnet LLM tagger for relevance + narratives
- `tagging/tickers.py` — Ticker extraction (cashtag, company alias, source-provided)
- `events/aggregator.py` — Event aggregation (48h narrative_tag clustering)
- `events/models.py` — Event + EventArticle models
- `users/models.py` — UserProfile model
- `users/service.py` — User CRUD + weight validation
- `bridge/quant.py` — Async price snapshot from quant-data-pipeline
- `api/event_routes.py` — Event API endpoints
- `api/user_routes.py` — User API endpoints
- `scripts/run_collectors.py` — Run all collectors
- `scripts/run_llm_tagger.py` — Run LLM tagger on unscored articles
- `scripts/backfill_tickers.py` — Backfill tickers for existing articles
- `frontend/` — feed-first React app

## API Endpoints
- `GET /api/health` — registry-driven active-source healthcheck
- `GET /api/articles/latest?limit=20&source=rss&min_relevance=4` — recent articles
- `GET /api/articles/search?q=keyword` — keyword search
- `GET /api/articles/digest` — grouped by source with top tags
- `GET /api/articles/signals?hours=24&compare_hours=24` — topic heat, narrative momentum, relevance distribution
- `GET /api/articles/sources` — historical source summary with counts
- `GET /api/ui/feed` — priority-scored feed with context rail data
- `GET /api/ui/items/{id}` — item detail with related items
- `GET /api/ui/topics` — topic list
- `GET /api/ui/sources` — active source list (registry-driven)
- `GET /api/ui/search?q=...` — UI search
- `GET /api/events/active` — active events by signal score
- `GET /api/events/{id}` — event detail with articles and price impacts
- `POST /api/users` — create user profile
- `GET /api/users` — list users
- `GET /api/users/{username}` — get user profile
- `PUT /api/users/{username}/weights` — update topic weights

## Commands
```bash
# Run API server
python main.py  # port 8001

# Run all collectors
python scripts/run_collectors.py

# Run specific collector
python scripts/run_collectors.py --source reddit

# Run LLM tagger
python scripts/run_llm_tagger.py --limit 10
python scripts/run_llm_tagger.py --prefiltered
python scripts/run_llm_tagger.py --backfill

# Frontend
cd frontend && npm install
cd frontend && npm run dev
cd frontend && npm run build

# Run tests
pytest tests/

# Backfill tickers for existing articles
python scripts/backfill_tickers.py
```

## Environment Variables (.env)
- `ANTHROPIC_API_KEY` — optional if running via API; nested CLI tagging uses `claude`
- `XUEQIU_COOKIE` — optional, for authenticated Xueqiu access
- `GITHUB_TOKEN` — optional, for GitHub release / commit monitor rate limits

## Conventions
- All collectors inherit from `BaseCollector`
- Dedup via unique `source_id` per source
- Tags stored as JSON array in SQLite
- Keyword tags + tickers auto-extracted on ingest via `BaseCollector.save()`
- `/api/health` is driven by the source registry, not config lists
- `/api/articles/sources` remains historical DB-driven
- Frontend-facing read models live under `/api/ui/*`
- `config.py` SOURCE_BOOTSTRAP is seed-only bootstrap data, not runtime truth
- Source registry is insert-only at seed time; DB edits survive restarts

## Tag Categories (13)
ai, crypto, macro, geopolitics, china-market, us-market, sector/tech, sector/finance, sector/energy, trading, regulation, earnings, commodities

## Current State
- Source architecture V2.1 complete (canonical source names throughout)
- Registry-driven scheduler, health, adapters — no legacy translation layer
- `Article.source` stores canonical V2 names; migration rewrites legacy values at startup
- Feed-first frontend v1 complete with user personalization
- Event aggregation: cross-source clustering by narrative_tag with signal scoring
- User profiles: per-user topic weights (0.0-3.0) for personalized feed ranking
- Quant bridge: ticker extraction + async price impact from quant-data-pipeline
- Full suite passes in local verification (283 tests)

## Related Project
- **quant-data-pipeline** (ashare) runs on port 8000, provides quantitative data
- Repo: https://github.com/zinan92/quant-data-pipeline

<!-- GSD:project-start source:PROJECT.md -->
## Project

**Park-Intel**

An open-source qualitative signal pipeline that collects frontier-tech, macro, and market content from 10+ source types (RSS, HackerNews, Reddit, GitHub, etc.), enriches articles with keyword tags and LLM-based relevance scoring, clusters them into narrative events, and serves them through a REST API with a feed-first frontend workbench. Currently a personal tool being prepared for public open-source release.

**Core Value:** Anyone can clone, configure, and run a self-hosted market intelligence pipeline with zero-config core sources and a health dashboard that makes data freshness visible at a glance.

### Constraints

- **Tech stack**: Keep existing FastAPI + React stack — no framework migration
- **Database**: Stay on SQLite — simplest for self-hosted deployment
- **LLM dependency**: Claude API is optional (LLM tagging degrades gracefully without it)
- **Zero-config core**: RSS, HackerNews, Reddit must work without any API keys or tokens
- **Backward compatibility**: Existing data in park_intel.db must not be lost during upgrades
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.13.7 - Backend API, data collectors, scheduling, LLM integration
- TypeScript 5.6.3 - Frontend application with strict type checking
- JavaScript (ES2020) - Frontend runtime with modern module resolution
- SQL - SQLite database queries via SQLAlchemy ORM
- HTML/CSS - Via React JSX and Tailwind CSS
## Runtime
- Python 3.13.7 (via `.venv` virtual environment)
- Node.js (for frontend build and dev tooling)
- pip - Python dependencies managed via `requirements.txt`
- npm - JavaScript/TypeScript dependencies managed via `frontend/package.json`
## Frameworks
- FastAPI 0.100.0+ - REST API framework, CORS middleware, async endpoints
- SQLAlchemy 2.0+ - ORM for SQLite database with declarative models
- APScheduler 3.10.0+ - Background job scheduler for periodic data collection
- Uvicorn 0.23.0+ - ASGI server (runs on port 8001)
- React 18.3.1 - UI component library
- React Router 6.28.0 - Client-side routing
- Vite 5.4.10 - Build tool and dev server (port 5174 with proxy to 8001)
- TypeScript compiler - Type checking during build
- Tailwind CSS 3.4.15 - Utility-first CSS framework
- PostCSS 8.4.49 - CSS processing with autoprefixer
## Key Dependencies
- feedparser 6.0+ - RSS/Atom feed parsing for news sources
- requests 2.31+ - HTTP client for collector integrations (HN, GitHub, Xueqiu, RSS)
- httpx 0.27+ - Async HTTP client for quant bridge API calls
- yfinance 0.2.36+ - Yahoo Finance data fetching for market news
- anthropic 0.40.0+ - Claude API client for LLM tagging
- python-dotenv 1.0+ - Environment variable loading from `.env`
- @radix-ui/react-dialog 1.1.2 - Modal dialog component
- @radix-ui/react-scroll-area 1.2.0 - Scrollable area component
- @radix-ui/react-separator 1.1.0 - Visual separator component
- @radix-ui/react-toast 1.2.2 - Toast notification system
- @tanstack/react-query 5.60.5 - Server state management
- @tanstack/react-query-devtools 5.60.5 - React Query development tools
- d3 7.9.0 - Data-driven visualization library for charts and diagrams
- @types/d3 7.4.3 - TypeScript types for D3
- @vitejs/plugin-react 4.3.3 - React Fast Refresh plugin for Vite
- @types/react 18.3.12 - TypeScript types for React
- @types/react-dom 18.3.1 - TypeScript types for React DOM
## Configuration
- Loaded via `python-dotenv` from `.env` file at project root
- Flask-style config module at `config.py` aggregates all settings
- Backend: FastAPI with uvicorn ASGI server
- Frontend: Vite with TypeScript compilation (`tsc && vite build`)
- Database: SQLite with WAL mode enabled for concurrent writes
- Backend: Runs on 127.0.0.1:8001
- Frontend: Runs on localhost:5174 with API proxy to http://localhost:8001
## Platform Requirements
- Python 3.13+
- Node.js (version not explicitly pinned in lockfile, but modern ESM support required)
- SQLite 3.x (included with Python)
- Python 3.13+ with FastAPI/Uvicorn
- Static frontend build artifacts deployable to CDN or Node.js
- SQLite database file persistence (or compatible SQL database if migrated)
- Network access to external APIs: Anthropic, Hacker News Algolia, Xueqiu, GitHub, Yahoo Finance, etc.
- SQLite stored at `data/park_intel.db`
- WAL journal mode enabled for performance
- Timeout: 30 seconds per connection
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Python modules: `snake_case` (e.g., `base.py`, `conftest.py`, `test_event_aggregation.py`)
- TypeScript components: `PascalCase` (e.g., `FeedCard.tsx`, `ItemDrawer.tsx`)
- TypeScript utilities: `camelCase` (e.g., `client.ts`, `api.ts`)
- Python functions: `snake_case` (e.g., `tag_article()`, `run_aggregation()`, `_configure_logging()`)
- Private functions: Leading underscore (e.g., `_no_scheduler()`, `_make_article()`)
- React components: `PascalCase` and exported as function (e.g., `export function FeedPage()`)
- React hooks in API client: `camelCase` (e.g., `feedParams`, `buildQuery`)
- Python: `snake_case` throughout (e.g., `saved_count`, `db_session`, `source_id`)
- TypeScript: `camelCase` for variables and properties (e.g., `activeUser`, `hasNextPage`, `staleTime`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `HN_MIN_SCORE`, `API_HOST`, `WINDOW_OPTIONS`)
- Type unions: `snake_case_label` for status strings (e.g., `"fading"`, `"no_data"`, `"ok"`)
- TypeScript interfaces: `PascalCase` (e.g., `FeedItem`, `ItemDetail`, `FeedParams`)
- Python dataclass/model names: `PascalCase` (e.g., `Article`, `SourceRegistry`, `Event`)
- Database table names: `snake_case` (e.g., `articles`, `source_registry`, `events`)
## Code Style
- TypeScript: Vite project with Tailwind CSS and component co-location
- Python: PEP 8 compliant, no explicit formatter configured (rely on linter)
- HTML/JSX: Four-space indentation in components
- TypeScript: `tsc --noEmit` type checking, `"strict": true` in tsconfig
- Python: No explicit linter configured; reliance on runtime and test execution
- Type checking: `tsconfig.json` enforces strict mode with `noUnusedLocals` and `noUnusedParameters`
- TypeScript: Import type utilities from API at top (e.g., `import type { FeedItem } from "../types/api"`)
- Python: Grouped by standard library, third-party, local; no explicit isort configuration
- Python functions: Direct function imports where needed (e.g., `from tagging import tag_article, extract_tickers`)
## Import Organization
- TypeScript: `@/*` maps to `src/` (configured in `tsconfig.json` baseUrl/paths)
- Python: Absolute imports from project root (e.g., `from db.models import Article`)
- TypeScript: `type` imports for interface-only imports (e.g., `import type { FeedItem }`)
- Python: Type annotations on all function signatures (e.g., `def collect(self) -> list[dict[str, Any]]`)
## Error Handling
- Try-catch blocks at critical save points with `IntegrityError` for dedup (`BaseCollector.save()`)
- Rollback on any exception, log with context (see `collectors/base.py` lines 71-76)
- Functions that may fail log exceptions with `logger.exception()` for full traceback
- Network/parsing errors caught gracefully in collectors (e.g., `test_rss_broken_feed_skipped_gracefully`)
- API client wraps fetch in try-catch with error message including status code (see `api/client.ts` lines 18-24)
- Async/await pattern used throughout; throw on HTTP non-200 response
- React components show loading and error states (see `FeedPage.tsx` lines 77-80)
- Python: Context-aware messages with source name (e.g., `"[%s] Saved %d new articles"` with source and count)
- TypeScript: Include HTTP status in error (e.g., `"API error 404: /api/ui/items/123"`)
## Logging
- Module-level logger: `logger = logging.getLogger(__name__)` at top of each module
- Log levels used: `INFO` (general flow), `DEBUG` (dedup skipped), `exception()` (errors with traceback)
- Rotating file handler: 10MB max per file, 5 backups, UTF-8 encoding (see `main.py` lines 28-35)
- No console logging in main app; all goes to `logs/park-intel.log`
- `logger.info("[%s] Saved %d new articles (of %d fetched)", self.source, saved, len(articles))`
- `logger.debug("Duplicate skipped: %s", data.get("source_id"))`
- `logger.exception("Error saving article %s for %s", data.get("source_id"), self.source)`
## Comments
- Complex business logic (e.g., signal score calculation, event clustering window)
- Non-obvious dedup logic or data transformations
- Workarounds or temporary code (prefixed with `# TODO:` or `# HACK:`)
- API contract changes (docstrings on pydantic models)
- Python docstrings on public functions and classes (e.g., `BaseCollector.collect()` with return type)
- TypeScript: Inline JSDoc rarely used; types in interfaces provide documentation
- Function-level comments explain intent, not what the code does
## Function Design
- Target <50 lines per function
- Helper functions extracted for clarity (e.g., `_make_article()` factory in tests)
- Collectors limit per-source logic to a single `collect()` method
- Type annotations on all parameters (Python/TypeScript)
- Avoid >4 parameters; use dataclass/interface for complex arguments
- Optional parameters use defaults or `| None` in Python, `?` in TypeScript
- Explicit return type annotations (e.g., `-> int`, `-> list[dict]`)
- Python functions return counts or query results; no bare `None` on success paths
- TypeScript components return JSX; API methods return typed Promises
## Module Design
- Python: Collectors inherit `BaseCollector` with abstract `collect()` method
- TypeScript: Named exports for all components and utilities (e.g., `export function FeedCard()`)
- API client: Single default export `api` object with method properties
- Python: Not used; direct imports from modules
- TypeScript: No barrel files; direct path imports (e.g., `import { FeedCard } from "../components/FeedCard"`)
- Each collector in `collectors/` is self-contained (e.g., `rss.py`, `reddit.py`)
- Models grouped in `db/models.py` and `events/models.py`
- API routes grouped by domain (`routes.py`, `ui_routes.py`, `event_routes.py`)
- React pages in `pages/`, components in `components/`, types in `types/`
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- Event-driven data collection triggered by registry-based scheduler
- Registry is the single source of truth for active data sources (not config files)
- Adapter pattern decouples source-type logic from per-instance configuration
- Feed workbench with priority scoring, personalization, and event aggregation
- Clean separation between data layer (SQLite), business logic (API), and presentation (React frontend)
## Layers
- Purpose: Fetch articles from external sources (RSS, Reddit, HackerNews, GitHub, etc.)
- Location: `collectors/` directory with per-source implementations
- Contains: BaseCollector abstract class, 10+ source-specific collectors
- Depends on: Database models, config.py, tagging services
- Used by: APScheduler-driven jobs via adapter layer
- Purpose: Manage active data sources as database records; route collection jobs
- Location: `sources/registry.py`, `sources/adapters.py`, `sources/seed.py`
- Contains: Source registry CRUD, adapter dispatch, registry seeding
- Depends on: Database, collectors
- Used by: Scheduler, API endpoints, collectors
- Purpose: Extract keywords, LLM-based relevance/narrative scoring, ticker extraction
- Location: `tagging/keywords.py`, `tagging/llm.py`, `tagging/tickers.py`
- Contains: Regex keyword tagger, Claude LLM scorer, cashtag/ticker extractor
- Depends on: Database, anthropic CLI or API
- Used by: BaseCollector.save(), standalone LLM tagger script
- Purpose: Cluster articles by narrative_tag within 48-hour windows; compute signal scores
- Location: `events/aggregator.py`, `events/narrator.py`, `events/models.py`
- Contains: Event/EventArticle models, aggregation logic, narrative generation
- Depends on: Database, tagging, bridge.quant
- Used by: Scheduler (hourly), event API endpoints
- Purpose: Async price snapshot fetching from quant-data-pipeline (port 8000)
- Location: `bridge/quant.py`
- Contains: Price impact calculator, ticker-to-price mapping
- Depends on: External quant-data-pipeline service
- Used by: Event aggregator on event closure
- Purpose: Expose collected, tagged, and aggregated data as REST endpoints
- Location: `api/routes.py`, `api/ui_routes.py`, `api/event_routes.py`, `api/user_routes.py`
- Contains: Read endpoints (health, articles, signals, events), UI read-models, user profiles
- Depends on: Database, business logic services
- Used by: Frontend, external consumers
- Purpose: Per-user topic weight preferences and personalized feed ranking
- Location: `users/models.py`, `users/service.py`
- Contains: UserProfile model (topic_weights JSON), CRUD service
- Depends on: Database
- Used by: UI feed endpoint for priority re-scoring
- Purpose: Feed-first workbench for browsing, searching, and analyzing articles
- Location: `frontend/src/`
- Contains: React components, TypeScript types, API client
- Depends on: FastAPI backend endpoints
- Used by: End users
- Purpose: Persistent storage of articles, sources, users, events
- Location: `db/models.py`, `db/database.py`, `db/migrations.py`
- Contains: SQLAlchemy ORM models, schema migrations, initialization
- Depends on: SQLite, sqlalchemy
- Used by: All other layers
## Data Flow
- Database is single source of truth
- Scheduler caches last run results in module-level `_last_results` dict (read by health endpoint)
- Frontend uses TanStack Query for client-side caching and re-fetching
- No in-memory state shared between requests; each API call queries fresh DB state
## Key Abstractions
- Purpose: Define common dedup/save pattern; auto-tag all articles
- Examples: `collectors/rss.py`, `collectors/reddit.py`, `collectors/hackernews.py`
- Pattern: Subclasses implement `collect()` to return raw article dicts; inherit `save()` with dedup/tagging
- Purpose: Map source registry records to collector-specific fetch methods
- Examples: `_adapt_rss()`, `_adapt_reddit()`, `_adapt_social_kol()`
- Pattern: Thin wrapper functions that parse config_json, invoke collector method, return normalized article list
- Purpose: Store source metadata (source_key, source_type, config, schedule)
- Fields: source_type (rss, reddit, github_release, etc.), display_name, config_json, schedule_hours, is_active
- Contract: All active sources have a registry row; no read-time translation layer
- Purpose: Represent collected article with metadata, tags, relevance, narratives, tickers
- Fields: source (V2 canonical name), source_id (dedup key), title, content, tags (JSON), relevance_score (1-5), narrative_tags (JSON), tickers (JSON)
- Contract: source_id is unique within source type; all articles get keyword tags on ingest
- Purpose: Cluster articles by narrative_tag within 48-hour window
- Fields: narrative_tag, window_start/end, status (active/closed), signal_score, source_count, avg_relevance, outcome_data (JSON)
- Contract: One active event per narrative_tag; events auto-close after 48 hours
- Purpose: Store user-specific topic weights for personalized feed ranking
- Fields: username, topic_weights (JSON map of topic → float 0.0-3.0)
- Contract: 13 valid topic keys; invalid weights rejected by service.py
## Entry Points
- Location: `main.py`
- Triggers: `python main.py` or uvicorn
- Responsibilities: Initialize FastAPI app, register routers, setup lifespan (DB init, scheduler start/stop)
- Location: `scheduler.py:CollectorScheduler`
- Triggers: FastAPI lifespan startup
- Responsibilities: Register APScheduler jobs per source_type, orchestrate collection runs, track results
- Location: `scripts/run_llm_tagger.py`
- Triggers: Scheduled by `_run_llm_tagger()`, manual CLI invocation
- Responsibilities: Score unscored articles using Claude LLM, store relevance_score + narrative_tags
- Location: `events/aggregator.py:run_aggregation()`
- Triggers: Scheduled by `_run_event_aggregation()`, manual invocation
- Responsibilities: Cluster articles by narrative_tag, compute signal scores, snapshot prices
- Location: `frontend/src/main.tsx:App`
- Triggers: Browser load
- Responsibilities: Route to pages (FeedPage, EventPage, SearchPage, etc.), fetch from API, display workbench
## Error Handling
- **Dedup errors (IntegrityError):** Log at debug level, skip to next article (expected behavior)
- **Parsing errors (JSON, HTML):** Log at debug/warning level, use fallback value or empty default
- **External API failures:** Log exception, return empty list or partial results, scheduler continues
- **Database errors:** Rollback transaction, log exception, continue with next batch
- **LLM tagger failures:** Catch exception in scheduler, record error in result, next run retries
- **Event aggregation failures:** Log exception, continue with remaining events
- `IntegrityError`: Duplicate article (source_id constraint violation)
- `json.JSONDecodeError`: Malformed JSON in tags/narrative_tags/tickers fields
- `ValueError`: Invalid type conversions or format issues
- `HTTPError`: External API (HN, Reddit, RSS) request failures
- `asyncio.TimeoutError`: Quant bridge timeout on price fetching
## Cross-Cutting Concerns
- Framework: Python logging module
- Location: Root logger configured in `main.py:_configure_logging()`
- Format: `%(asctime)s %(levelname)s [%(name)s] %(message)s`
- Rotation: RotatingFileHandler with 10MB max, 5 backups at `logs/park-intel.log`
- Pattern: All modules use `logger = logging.getLogger(__name__)` and log at appropriate levels (debug for dedup, info for success, exception for failures)
- Source registry: `sources/seed.py` validates source_type, config structure on seed
- User profiles: `users/service.py` validates topic_weights (0.0-3.0 per key, 13 valid keys)
- API inputs: `api/routes.py` parses query params with defaults, no schema validation library used
- No global request body validation (mostly read-only APIs)
- Not implemented; frontend and API have CORS enabled for all origins
- No user authentication; ?user= param is a reference key, not auth
- Suitable for internal workbench use
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
