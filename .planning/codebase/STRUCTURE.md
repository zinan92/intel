# Codebase Structure

**Analysis Date:** 2026-03-31

## Directory Layout

```
park-intel/
├── main.py                  # FastAPI app entry point (port 8001)
├── config.py                # Global config: source bootstrap, env vars, paths
├── scheduler.py             # APScheduler-based collector orchestration
├── api/                     # REST API endpoints
│   ├── routes.py           # Core read APIs (health, articles, signals, digest)
│   ├── ui_routes.py        # Feed workbench read-models (feed, items, topics, sources)
│   ├── event_routes.py     # Event APIs (active, detail, history, scorecard)
│   └── user_routes.py      # User profile CRUD
├── db/                      # Data layer
│   ├── models.py           # SQLAlchemy ORM: Article, SourceRegistry, Brief, Event, EventArticle, UserProfile
│   ├── database.py         # Engine, session, init_db (creates tables + seed + migration)
│   └── migrations.py       # Schema migrations (insert-only, idempotent)
├── sources/                 # Source registry & adapter layer
│   ├── registry.py         # Source registry CRUD service
│   ├── adapters.py         # Per-type adapters (registry record → collector method)
│   ├── seed.py             # Populate registry from config.SOURCE_BOOTSTRAP (insert-only)
│   └── resolver.py         # URL → source_type classifier (internal utility)
├── collectors/              # Data source collectors
│   ├── base.py             # BaseCollector: abstract class with save() + dedup/tagging
│   ├── rss.py              # RSS feed collector (multi-feed config)
│   ├── reddit.py           # Reddit subreddit collector
│   ├── hackernews.py       # Hacker News top stories
│   ├── github_release.py   # GitHub releases by repo
│   ├── github_trending.py  # GitHub trending repos
│   ├── google_news.py      # Google News
│   ├── yahoo_finance.py    # Yahoo Finance news
│   ├── xueqiu.py           # Xueqiu stock discussion
│   ├── social_kol.py       # Curated KOL Twitter via clawfeed CLI
│   └── webpage_monitor.py  # Website blog scraping + GitHub commit monitoring
├── tagging/                 # Article enrichment (keywords, LLM, tickers)
│   ├── keywords.py         # Regex-based keyword tagger (13 categories: ai, crypto, macro, etc.)
│   ├── llm.py              # Claude LLM relevance scorer + narrative generator
│   ├── tickers.py          # Ticker extraction (cashtag, company alias, source)
│   └── __init__.py         # Exports tag_article(), extract_tickers()
├── events/                  # Event aggregation (narrative clustering)
│   ├── models.py           # Event, EventArticle ORM models
│   ├── aggregator.py       # Cluster articles by narrative_tag, compute signal scores
│   └── narrator.py         # Generate cross-source narrative summaries via LLM
├── users/                   # User personalization
│   ├── models.py           # UserProfile: username, topic_weights (JSON)
│   ├── service.py          # CRUD + topic_weights validation (0.0-3.0)
│   └── __init__.py
├── bridge/                  # External integrations
│   ├── quant.py            # Async price snapshot from quant-data-pipeline (port 8000)
│   └── __init__.py
├── briefs/                  # Morning briefing generation
│   ├── models.py           # Brief ORM model
│   └── __init__.py
├── scripts/                 # CLI scripts (not scheduled)
│   ├── run_collectors.py   # Run all collectors or filter by source type
│   ├── run_llm_tagger.py   # Score unscored articles: --limit, --prefiltered, --backfill modes
│   ├── backfill_tickers.py # Backfill tickers for existing articles
│   └── generate_narrative_signal.py  # Generate narrative signal brief
├── frontend/                # React TypeScript frontend
│   ├── src/
│   │   ├── main.tsx        # App entry (React.createRoot)
│   │   ├── App.tsx         # Router setup, layout
│   │   ├── api/
│   │   │   └── client.ts   # Typed API client (get/put, buildQuery helpers)
│   │   ├── types/
│   │   │   └── api.ts      # TypeScript types for all API responses
│   │   ├── components/     # Reusable UI components
│   │   │   ├── FeedCard.tsx        # Article card for feed
│   │   │   ├── EventCard.tsx       # Event card (cross-source cluster)
│   │   │   ├── ItemDrawer.tsx      # Full article detail + related items
│   │   │   ├── ContextRail.tsx     # Right panel: related articles + event context
│   │   │   ├── Sidebar.tsx         # Left navigation (topics, sources, events)
│   │   │   ├── TopBar.tsx          # Search, filters, user selector
│   │   │   ├── MorningBrief.tsx    # Daily narrative brief display
│   │   │   ├── NarrativeSignal.tsx # Signal heat visualization
│   │   └── pages/          # Page-level components
│   │       ├── FeedPage.tsx        # Main feed with cursor pagination
│   │       ├── EventPage.tsx       # Event detail (articles + price impacts)
│   │       ├── SearchPage.tsx      # Keyword search results
│   │       ├── TopicPage.tsx       # Topic drill-down (all items with tag)
│   │       ├── SourcePage.tsx      # Source drill-down (all items from source)
│   │       ├── EventHistoryPage.tsx # Past events, scorecard
│   │       ├── ConstellationPage.tsx # Event constellation visualization (D3.js)
│   │       └── SettingsPage.tsx    # User topic weights
│   ├── index.css           # Tailwind styles
│   ├── vite-env.d.ts       # Vite environment type definitions
│   ├── vite.config.ts      # Vite build config (React, TypeScript)
│   ├── package.json        # Dependencies: react, react-router, tanstack-query, tailwind, d3
│   ├── tsconfig.json       # TypeScript compiler options
│   └── dist/               # Built frontend (generated)
├── tests/                   # pytest test suite
│   ├── conftest.py         # pytest fixtures, test DB setup
│   ├── test_event_aggregation.py
│   ├── test_event_api.py
│   ├── test_event_models.py
│   ├── test_health_active_sources.py
│   ├── test_keywords.py
│   ├── test_migration.py
│   ├── test_personalized_feed.py
│   ├── test_reddit.py
│   ├── test_rss_collector.py
│   ├── test_scorecard.py
│   ├── test_signals.py
│   ├── test_source_canonicalization.py
│   ├── test_source_registry_parity.py
│   ├── test_source_registry_seed.py
│   ├── test_ui_regressions.py
│   ├── test_ui_source_hidden_semantics.py
│   ├── test_webpage_monitor.py
│   └── test_xueqiu.py
├── data/                    # Data directory (generated at runtime)
│   ├── park_intel.db       # SQLite database
│   └── website_monitor_state.json  # Webpage monitor state (hash tracking)
├── logs/                    # Log files (generated at runtime)
│   └── park-intel.log      # Rotating log file
├── docs/                    # Documentation
│   ├── plans/              # Planning/design docs
│   └── superpowers/        # Skill documentation
├── plans/                   # Project planning
├── .planning/
│   └── codebase/           # This analysis
├── .env                     # Environment variables (secrets: ANTHROPIC_API_KEY, etc.)
├── .gitignore              # Ignores logs, .venv, __pycache__, *.db
├── CLAUDE.md               # Project README (architecture, API endpoints, commands)
└── .venv/                  # Python virtual environment
```

## Directory Purposes

**`api/`:**
- Purpose: REST endpoint handlers for all API routes
- Contains: FastAPI routers for core data, UI read-models, events, users
- Key files: `routes.py` (health/articles/signals), `ui_routes.py` (feed workbench), `event_routes.py` (events)

**`db/`:**
- Purpose: Data layer (models, connection, initialization, migrations)
- Contains: SQLAlchemy ORM definitions, engine factory, schema setup
- Key files: `models.py` (Article, SourceRegistry, Event, UserProfile), `database.py` (init_db, get_session), `migrations.py` (idempotent schema updates)

**`sources/`:**
- Purpose: Source registry management and adapter dispatch
- Contains: Registry CRUD, source-type to collector routing, bootstrap seeding
- Key files: `registry.py` (list_active_sources, CRUD), `adapters.py` (per-type adapters), `seed.py` (populate registry from config)

**`collectors/`:**
- Purpose: Fetch articles from external sources
- Contains: Base class, per-source implementations (10 types)
- Pattern: Each collector.source defines source type; collect() returns article dicts; save() is inherited with dedup/tagging

**`tagging/`:**
- Purpose: Extract and enrich article metadata (keywords, relevance, narratives, tickers)
- Contains: Regex tagger, LLM scorer, ticker extractor
- Key exports: `tag_article(title, content) → list[str]`, `extract_tickers(title, content, source_tickers) → list[str]`

**`events/`:**
- Purpose: Cluster articles by narrative_tag, compute event signals
- Contains: Event/EventArticle models, aggregation logic, narrative generation
- Entry point: `aggregator.run_aggregation(session)` called hourly by scheduler

**`users/`:**
- Purpose: User profiles with topic-based personalization
- Contains: UserProfile model, CRUD service with validation
- Service: `users.service.UserService` validates topic_weights (0.0-3.0, 13 keys)

**`bridge/`:**
- Purpose: Integration with external systems (quant-data-pipeline)
- Contains: Async price fetcher, price impact calculator
- Used by: Event aggregator on event closure to snapshot ticker prices

**`scripts/`:**
- Purpose: One-off CLI scripts (not scheduled)
- Contains: Collector runner, LLM tagger, ticker backfiller, narrative brief generator
- Usage: `python scripts/run_collectors.py [--source TYPE]`, etc.

**`frontend/`:**
- Purpose: React TypeScript UI for feed workbench
- Contains: Page components, API client, TypeScript types
- Key pages: FeedPage (main), EventPage, SearchPage, TopicPage, SourcePage
- Build: Vite dev server on localhost:5173, production build to dist/

**`tests/`:**
- Purpose: pytest test suite (283+ tests, ~80% coverage)
- Pattern: Tests co-located by feature (test_event_api.py, test_source_registry_seed.py)
- Fixtures: conftest.py provides test DB, session, sample data

**`data/`:**
- Purpose: Runtime-generated data files
- Contents: SQLite database (park_intel.db), webpage monitor state
- Gitignored: Database files are not committed

**`logs/`:**
- Purpose: Application logs
- Contents: RotatingFileHandler output from main.py
- Gitignored: Log files are not committed

## Key File Locations

**Entry Points:**
- `main.py`: FastAPI app startup (port 8001)
- `frontend/src/main.tsx`: React app entry
- `scheduler.py`: APScheduler initialization and job registration

**Configuration:**
- `config.py`: Source bootstrap, env var loading, paths (BASE_DIR, DB_PATH, DATA_DIR)
- `.env`: Environment secrets (ANTHROPIC_API_KEY, XUEQIU_COOKIE, GITHUB_TOKEN)
- `frontend/tsconfig.json`: TypeScript compiler options

**Core Logic:**
- `db/models.py`: ORM definitions for Article, SourceRegistry, Event, UserProfile
- `collectors/base.py`: BaseCollector with save(), dedup, auto-tagging
- `sources/adapters.py`: Registry record → collector method dispatch
- `events/aggregator.py`: Event clustering, signal scoring
- `api/ui_routes.py`: Feed workbench read-models with priority scoring

**Testing:**
- `tests/conftest.py`: pytest fixtures (test DB, session factory, sample data)
- `tests/test_event_aggregation.py`: Event clustering tests
- `tests/test_personalized_feed.py`: User weight personalization tests
- `tests/test_source_registry_seed.py`: Registry seeding tests

## Naming Conventions

**Files:**
- Collectors: `collectors/{source_type}.py` (e.g., `collectors/hackernews.py`)
- Tests: `tests/test_{feature}.py` (e.g., `tests/test_event_aggregation.py`)
- API routers: `api/{entity}_routes.py` (e.g., `api/event_routes.py`)
- Models: `{entity}/models.py` (e.g., `events/models.py`)

**Directories:**
- Feature domains: lowercase, plural preferred (`collectors/`, `tagging/`, `events/`)
- Components: CamelCase files (e.g., `FeedCard.tsx`, `ItemDrawer.tsx`)

**Functions/Classes:**
- Python: snake_case functions, PascalCase classes (e.g., `BaseCollector`, `_run_source_type()`)
- TypeScript: PascalCase components, camelCase utilities (e.g., `FeedCard`, `buildQuery()`)

**Database:**
- Tables: lowercase plural (`articles`, `source_registry`, `events`)
- Columns: snake_case (e.g., `source_id`, `published_at`, `narrative_tags`)

**API:**
- Routes: kebab-case with slash-prefix (e.g., `/api/ui/feed`, `/api/events/active`)
- Query params: snake_case (e.g., `?limit=20&min_relevance=4`)

## Where to Add New Code

**New Collector (new source type):**
- Implementation: `collectors/{source_type}.py`
- Inherit from `BaseCollector`, set `source = "source_type"`, implement `collect()` or helper methods
- Add adapter in `sources/adapters.py`: `_adapt_{source_type}(record) → list[dict]`
- Register adapter in `_ADAPTERS` dict in adapters.py
- Add seeding config in `config.py:SOURCE_BOOTSTRAP` (source_key, source_type, config_json)
- Tests: `tests/test_{source_type}.py`

**New API Endpoint:**
- Implementation: `api/{entity}_routes.py` (create if needed)
- Create FastAPI router with prefix (e.g., `router = APIRouter(prefix="/api/...")`)
- Use `@router.get()` decorator
- Import and register in `main.py:app.include_router()`
- Query params: use `Query()` for validation
- Return typed response (define type in `frontend/src/types/api.ts`)

**New Database Model:**
- Implementation: `{entity}/models.py` (create if needed)
- Inherit from `Base`, define SQLAlchemy columns
- Auto-registered in `db/database.py` via `import {entity}.models`
- Add schema migration in `db/migrations.py` if adding new columns/tables after initial setup

**New React Page:**
- Implementation: `frontend/src/pages/{EntityPage}.tsx`
- Use React Router for routing in `App.tsx`
- Fetch data via `api.{entity}()` client methods
- Add route in `App.tsx` router definition

**Shared Utilities:**
- Python: `tagging/` for article enrichment, generic utils in module-specific helpers
- TypeScript: `frontend/src/api/client.ts` for API methods, `frontend/src/types/api.ts` for types

**Tests:**
- Unit: `tests/test_{component}.py`
- Pattern: conftest.py provides fixtures; tests use `session` fixture for DB access
- Markers: `@pytest.mark.unit`, `@pytest.mark.integration`

## Special Directories

**`.planning/`:**
- Purpose: This codebase analysis and project planning
- Generated: Yes (by GSD mapping agents)
- Committed: Yes

**`data/`:**
- Purpose: SQLite database and state files
- Generated: Yes (by init_db, collectors)
- Committed: No (in .gitignore)

**`logs/`:**
- Purpose: Application log files
- Generated: Yes (by RotatingFileHandler)
- Committed: No (in .gitignore)

**`.venv/`:**
- Purpose: Python virtual environment
- Generated: Yes (by `python -m venv`)
- Committed: No (in .gitignore)

**`frontend/node_modules/`:**
- Purpose: npm dependencies
- Generated: Yes (by `npm install`)
- Committed: No (in .gitignore)

**`frontend/dist/`:**
- Purpose: Production build output
- Generated: Yes (by `npm run build`)
- Committed: No (in .gitignore)

---

*Structure analysis: 2026-03-31*
