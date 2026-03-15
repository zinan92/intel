# qualitative-data-pipeline (park-intel)

## Project Overview
Qualitative signal pipeline and feed-first workbench for collecting frontier-tech, macro, and market content into a structured API and local reading UI.

## Tech Stack
- **Backend**: FastAPI, SQLAlchemy 2.0, Python 3.11+
- **Database**: SQLite at `data/park_intel.db`
- **Frontend**: React 18, TypeScript, Vite, Tailwind, TanStack Query, React Router
- **Dependencies**: feedparser, requests, apscheduler, anthropic, python-dotenv

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
- `scripts/run_collectors.py` — Run all collectors
- `scripts/run_llm_tagger.py` — Run LLM tagger on unscored articles
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
```

## Environment Variables (.env)
- `ANTHROPIC_API_KEY` — optional if running via API; nested CLI tagging uses `claude`
- `XUEQIU_COOKIE` — optional, for authenticated Xueqiu access
- `GITHUB_TOKEN` — optional, for GitHub release / commit monitor rate limits

## Conventions
- All collectors inherit from `BaseCollector`
- Dedup via unique `source_id` per source
- Tags stored as JSON array in SQLite
- Keyword tags auto-applied on ingest via `BaseCollector.save()`
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
- Feed-first frontend v1 complete
- Full suite passes in local verification

## Related Project
- **quant-data-pipeline** (ashare) runs on port 8000, provides quantitative data
- Repo: https://github.com/zinan92/quant-data-pipeline
