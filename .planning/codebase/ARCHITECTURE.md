# Architecture

**Analysis Date:** 2026-03-31

## Pattern Overview

**Overall:** Layered pipeline with registry-driven scheduling and adapter-based collection

**Key Characteristics:**
- Event-driven data collection triggered by registry-based scheduler
- Registry is the single source of truth for active data sources (not config files)
- Adapter pattern decouples source-type logic from per-instance configuration
- Feed workbench with priority scoring, personalization, and event aggregation
- Clean separation between data layer (SQLite), business logic (API), and presentation (React frontend)

## Layers

**Data Collection Layer:**
- Purpose: Fetch articles from external sources (RSS, Reddit, HackerNews, GitHub, etc.)
- Location: `collectors/` directory with per-source implementations
- Contains: BaseCollector abstract class, 10+ source-specific collectors
- Depends on: Database models, config.py, tagging services
- Used by: APScheduler-driven jobs via adapter layer

**Source Registry & Orchestration:**
- Purpose: Manage active data sources as database records; route collection jobs
- Location: `sources/registry.py`, `sources/adapters.py`, `sources/seed.py`
- Contains: Source registry CRUD, adapter dispatch, registry seeding
- Depends on: Database, collectors
- Used by: Scheduler, API endpoints, collectors

**Tagging & Enrichment Layer:**
- Purpose: Extract keywords, LLM-based relevance/narrative scoring, ticker extraction
- Location: `tagging/keywords.py`, `tagging/llm.py`, `tagging/tickers.py`
- Contains: Regex keyword tagger, Claude LLM scorer, cashtag/ticker extractor
- Depends on: Database, anthropic CLI or API
- Used by: BaseCollector.save(), standalone LLM tagger script

**Event Aggregation Layer:**
- Purpose: Cluster articles by narrative_tag within 48-hour windows; compute signal scores
- Location: `events/aggregator.py`, `events/narrator.py`, `events/models.py`
- Contains: Event/EventArticle models, aggregation logic, narrative generation
- Depends on: Database, tagging, bridge.quant
- Used by: Scheduler (hourly), event API endpoints

**Quant Bridge Layer:**
- Purpose: Async price snapshot fetching from quant-data-pipeline (port 8000)
- Location: `bridge/quant.py`
- Contains: Price impact calculator, ticker-to-price mapping
- Depends on: External quant-data-pipeline service
- Used by: Event aggregator on event closure

**API Layer:**
- Purpose: Expose collected, tagged, and aggregated data as REST endpoints
- Location: `api/routes.py`, `api/ui_routes.py`, `api/event_routes.py`, `api/user_routes.py`
- Contains: Read endpoints (health, articles, signals, events), UI read-models, user profiles
- Depends on: Database, business logic services
- Used by: Frontend, external consumers

**User Personalization Layer:**
- Purpose: Per-user topic weight preferences and personalized feed ranking
- Location: `users/models.py`, `users/service.py`
- Contains: UserProfile model (topic_weights JSON), CRUD service
- Depends on: Database
- Used by: UI feed endpoint for priority re-scoring

**Frontend Layer:**
- Purpose: Feed-first workbench for browsing, searching, and analyzing articles
- Location: `frontend/src/`
- Contains: React components, TypeScript types, API client
- Depends on: FastAPI backend endpoints
- Used by: End users

**Database Layer:**
- Purpose: Persistent storage of articles, sources, users, events
- Location: `db/models.py`, `db/database.py`, `db/migrations.py`
- Contains: SQLAlchemy ORM models, schema migrations, initialization
- Depends on: SQLite, sqlalchemy
- Used by: All other layers

## Data Flow

**Collection & Enrichment Pipeline:**

1. FastAPI startup triggers `CollectorScheduler.start()`
2. Scheduler loads active sources from `source_registry` table (grouped by `source_type`)
3. For each source type, scheduler dispatches `_run_source_type(source_type)` at configured intervals
4. `_run_source_type()` queries registry for all instances of that type
5. For each instance, `sources/adapters.py:collect_from_source(record)` calls the type-specific adapter
6. Adapter invokes collector-specific method (e.g., `RSSCollector._fetch_feed()`) with instance config
7. Collector returns list of raw article dicts
8. `BaseCollector.save()` processes each article:
   - Merges collector tags with regex keyword tags
   - Extracts tickers via cashtag/alias/source patterns
   - Creates `Article` row (dedup via unique `source_id`)
   - On IntegrityError: logs debug message and continues

9. Separately, scheduled `_run_llm_tagger()` scores unscored articles (limit=50, every 4 hours)
10. LLM tagger updates `Article.relevance_score` (1-5) and `Article.narrative_tags` (JSON array)
11. Scheduled `_run_event_aggregation()` (every 1 hour) clusters recent articles by `narrative_tags`:
    - Groups articles within 48-hour window by narrative_tag
    - Creates/updates `Event` rows with signal_score = source_count × avg_relevance
    - On event window expiration, snapshots ticker prices from quant-data-pipeline
    - Generates cross-source narratives via LLM

**Request Flow (API → Frontend):**

1. User requests `/api/ui/feed?user=alice` from frontend
2. Endpoint queries recent articles, calculates priority_score per article
3. Priority scoring: event_membership (4.0 boost) > freshness (decay) > source_weight (0.1-0.5)
4. If `?user=alice` specified, re-scores using user's topic_weights
5. Returns paginated FeedResponse with cursor-based pagination
6. Frontend fetches `/api/ui/items/{id}` to populate ItemDrawer (full article + related articles + event context)
7. Frontend fetches `/api/events/{id}` for event detail (articles in event, signal score, price impacts)

**State Management:**

- Database is single source of truth
- Scheduler caches last run results in module-level `_last_results` dict (read by health endpoint)
- Frontend uses TanStack Query for client-side caching and re-fetching
- No in-memory state shared between requests; each API call queries fresh DB state

## Key Abstractions

**BaseCollector:**
- Purpose: Define common dedup/save pattern; auto-tag all articles
- Examples: `collectors/rss.py`, `collectors/reddit.py`, `collectors/hackernews.py`
- Pattern: Subclasses implement `collect()` to return raw article dicts; inherit `save()` with dedup/tagging

**Adapter Functions:**
- Purpose: Map source registry records to collector-specific fetch methods
- Examples: `_adapt_rss()`, `_adapt_reddit()`, `_adapt_social_kol()`
- Pattern: Thin wrapper functions that parse config_json, invoke collector method, return normalized article list

**SourceRegistry Model:**
- Purpose: Store source metadata (source_key, source_type, config, schedule)
- Fields: source_type (rss, reddit, github_release, etc.), display_name, config_json, schedule_hours, is_active
- Contract: All active sources have a registry row; no read-time translation layer

**Article Model:**
- Purpose: Represent collected article with metadata, tags, relevance, narratives, tickers
- Fields: source (V2 canonical name), source_id (dedup key), title, content, tags (JSON), relevance_score (1-5), narrative_tags (JSON), tickers (JSON)
- Contract: source_id is unique within source type; all articles get keyword tags on ingest

**Event Model:**
- Purpose: Cluster articles by narrative_tag within 48-hour window
- Fields: narrative_tag, window_start/end, status (active/closed), signal_score, source_count, avg_relevance, outcome_data (JSON)
- Contract: One active event per narrative_tag; events auto-close after 48 hours

**UserProfile Model:**
- Purpose: Store user-specific topic weights for personalized feed ranking
- Fields: username, topic_weights (JSON map of topic → float 0.0-3.0)
- Contract: 13 valid topic keys; invalid weights rejected by service.py

## Entry Points

**API Server:**
- Location: `main.py`
- Triggers: `python main.py` or uvicorn
- Responsibilities: Initialize FastAPI app, register routers, setup lifespan (DB init, scheduler start/stop)

**Collector Scheduler:**
- Location: `scheduler.py:CollectorScheduler`
- Triggers: FastAPI lifespan startup
- Responsibilities: Register APScheduler jobs per source_type, orchestrate collection runs, track results

**LLM Tagger Script:**
- Location: `scripts/run_llm_tagger.py`
- Triggers: Scheduled by `_run_llm_tagger()`, manual CLI invocation
- Responsibilities: Score unscored articles using Claude LLM, store relevance_score + narrative_tags

**Event Aggregation:**
- Location: `events/aggregator.py:run_aggregation()`
- Triggers: Scheduled by `_run_event_aggregation()`, manual invocation
- Responsibilities: Cluster articles by narrative_tag, compute signal scores, snapshot prices

**Frontend:**
- Location: `frontend/src/main.tsx:App`
- Triggers: Browser load
- Responsibilities: Route to pages (FeedPage, EventPage, SearchPage, etc.), fetch from API, display workbench

## Error Handling

**Strategy:** Fail gracefully with logging; continue processing other items

**Patterns:**

- **Dedup errors (IntegrityError):** Log at debug level, skip to next article (expected behavior)
- **Parsing errors (JSON, HTML):** Log at debug/warning level, use fallback value or empty default
- **External API failures:** Log exception, return empty list or partial results, scheduler continues
- **Database errors:** Rollback transaction, log exception, continue with next batch
- **LLM tagger failures:** Catch exception in scheduler, record error in result, next run retries
- **Event aggregation failures:** Log exception, continue with remaining events

**Error Types Handled:**

- `IntegrityError`: Duplicate article (source_id constraint violation)
- `json.JSONDecodeError`: Malformed JSON in tags/narrative_tags/tickers fields
- `ValueError`: Invalid type conversions or format issues
- `HTTPError`: External API (HN, Reddit, RSS) request failures
- `asyncio.TimeoutError`: Quant bridge timeout on price fetching

## Cross-Cutting Concerns

**Logging:** 
- Framework: Python logging module
- Location: Root logger configured in `main.py:_configure_logging()`
- Format: `%(asctime)s %(levelname)s [%(name)s] %(message)s`
- Rotation: RotatingFileHandler with 10MB max, 5 backups at `logs/park-intel.log`
- Pattern: All modules use `logger = logging.getLogger(__name__)` and log at appropriate levels (debug for dedup, info for success, exception for failures)

**Validation:**
- Source registry: `sources/seed.py` validates source_type, config structure on seed
- User profiles: `users/service.py` validates topic_weights (0.0-3.0 per key, 13 valid keys)
- API inputs: `api/routes.py` parses query params with defaults, no schema validation library used
- No global request body validation (mostly read-only APIs)

**Authentication:**
- Not implemented; frontend and API have CORS enabled for all origins
- No user authentication; ?user= param is a reference key, not auth
- Suitable for internal workbench use

---

*Architecture analysis: 2026-03-31*
