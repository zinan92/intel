# qualitative-data-pipeline (park-intel)

## Project Overview
Qualitative signal pipeline and feed-first workbench for collecting frontier-tech, macro, and market content into a structured API and local reading UI.

## Tech Stack
- **Backend**: FastAPI, SQLAlchemy 2.0, Python 3.11+
- **Database**: SQLite at `data/park_intel.db`
- **Frontend**: React 18, TypeScript, Vite, Tailwind, TanStack Query, React Router
- **Dependencies**: feedparser, requests, apscheduler, anthropic, python-dotenv

## Architecture
```
Collectors (fetch) → BaseCollector.save (dedup + keyword tagging) → SQLite
                                                                      ↓
LLM Tagger → relevance_score + narrative_tags → SQLite
                                                                      ↓
                         FastAPI APIs (/api/* + /api/ui/*) → React frontend
```

## Key Files
- `main.py` — FastAPI app entry (port 8001)
- `config.py` — source registry, feed lists, collector config, env loading
- `db/models.py` — Article model (source, title, content, url, tags, score, relevance_score, narrative_tags)
- `db/migrations.py` — Idempotent schema migrations
- `api/routes.py` — core read APIs: health, latest, search, digest, signals, sources
- `api/ui_routes.py` — frontend read-model APIs: feed, item detail, topics, sources, search
- `scheduler.py` — APScheduler registration for active collectors + LLM tagger
- `collectors/base.py` — BaseCollector abstract class (with auto keyword tagging)
- `collectors/hackernews.py` — HN Algolia API collector
- `collectors/rss.py` — config-driven RSS collector
- `collectors/xueqiu.py` — Xueqiu collector (Chinese source)
- `collectors/clawfeed.py` — ClawFeed CLI collector
- `collectors/reddit.py` — Reddit RSS collector
- `collectors/github_release.py` — GitHub release monitor
- `collectors/webpage_monitor.py` — scrape + docs commit monitor
- `tagging/keywords.py` — Regex-based keyword tagger (13 tag categories)
- `tagging/llm.py` — Claude Sonnet LLM tagger for relevance + narratives
- `scripts/run_collectors.py` — Run all collectors
- `scripts/run_llm_tagger.py` — Run LLM tagger on unscored articles
- `frontend/` — feed-first React app

## API Endpoints
- `GET /api/health` — active-source healthcheck
- `GET /api/articles/latest?limit=20&source=rss&min_relevance=4` — recent articles
- `GET /api/articles/search?q=keyword` — keyword search
- `GET /api/articles/digest` — grouped by source with top tags
- `GET /api/articles/signals?hours=24&compare_hours=24` — topic heat, narrative momentum, relevance distribution
- `GET /api/articles/sources` — historical source summary with counts
- `GET /api/ui/feed` — priority-scored feed with context rail data
- `GET /api/ui/items/{id}` — item detail with related items
- `GET /api/ui/topics` — topic list
- `GET /api/ui/sources` — active source list
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
- `/api/health` is driven by `config.ACTIVE_SOURCES`, not by DB history
- `/api/articles/sources` remains historical DB-driven
- frontend-facing read models live under `/api/ui/*`

## Tag Categories (13)
ai, crypto, macro, geopolitics, china-market, us-market, sector/tech, sector/finance, sector/energy, trading, regulation, earnings, commodities

## Current State
- source-layer redesign complete
- feed-first frontend v1 complete
- full suite currently passes in local verification
- remaining cleanup is mostly documentation and warning reduction (`datetime.utcnow()` deprecations)

## Related Project
- **quant-data-pipeline** (ashare) runs on port 8000, provides quantitative data
- Repo: https://github.com/zinan92/quant-data-pipeline
