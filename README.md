<div align="center">

# park-intel

**Self-hosted market intelligence pipeline -- collect, enrich, and surface trading signals from 10+ sources**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](#)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](#)
[![React 18](https://img.shields.io/badge/React_18-61DAFB?style=flat-square&logo=react&logoColor=black)](#)
[![Tests](https://img.shields.io/badge/tests-290%2B_passing-brightgreen?style=flat-square)](#)

</div>

---

## What It Does

park-intel is a self-hosted market intelligence pipeline. It collects articles from 10+ source types (RSS, Hacker News, Reddit, GitHub, and more), enriches them with keyword tagging and optional LLM-based relevance scoring, clusters related articles into narrative events, and serves everything through a REST API with a feed-first frontend.

Core sources work out of the box with zero API keys. Optional sources (Xueqiu, LLM tagging) activate when you add their credentials.

## Quick Start

```bash
git clone https://github.com/zinan92/intel.git park-intel
cd park-intel

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # edit .env to add optional API keys

# Build frontend (one-time)
cd frontend && npm install && npm run build && cd ..

# Start server (API + frontend served together)
python main.py                # open http://localhost:8001
```

The built-in scheduler starts collecting automatically. Visit `http://localhost:8001/health` to see source status.

**Run as background service (macOS):**

```bash
bash scripts/install-service.sh    # auto-starts on boot, restarts on crash
bash scripts/service-status.sh     # check if running
bash scripts/uninstall-service.sh  # stop and remove
```

## Core vs Optional Sources

| Source | Key Required | Env Var | Notes |
|--------|-------------|---------|-------|
| RSS Feeds (50+) | No | -- | Blogs, newsletters, tech and crypto media |
| Hacker News | No | -- | Algolia API, score >= 20 filter |
| Reddit | No | -- | 13 subreddits via RSS |
| GitHub Trending | No | -- | Keyword-filtered trending repos |
| Yahoo Finance | No | -- | Ticker news via yfinance |
| Google News | No | -- | Query-driven news aggregation |
| GitHub Releases | Optional | `GITHUB_TOKEN` | Increases API rate limit |
| Xueqiu (Chinese market) | Yes | `XUEQIU_COOKIE` | Chinese market KOL commentary |
| Social KOL | Optional | -- | Requires `clawfeed` CLI installed |
| LLM Tagging | Optional | `ANTHROPIC_API_KEY` | AI relevance scoring + narrative tags |

Without `ANTHROPIC_API_KEY`, articles still collect and get keyword tags -- they just won't have LLM-based relevance scores or narrative tags.

## Architecture

```
Source Registry (DB)
       |
       v
   Adapters  -->  Collectors (fetch + dedup)  -->  SQLite
                                                      |
                        Keyword Tagger (13 categories) |
                        Ticker Extractor ($NVDA, etc.) |
                                                      v
                                              LLM Tagger (optional)
                                              relevance_score 1-5
                                              narrative_tags
                                                      |
                                                      v
                                          Event Aggregator (48h window)
                                          cross-source clustering
                                          signal scoring
                                                      |
                                                      v
                                              FastAPI REST API
                                             /api/* + /api/ui/*
                                                      |
                              +-----------+-----------+-----------+
                              |           |           |           |
                           React UI   Quant Bridge  User        Health
                           Feed +     price impact  profiles    Dashboard
                           Events     from ext.     topic       /health
                                      service       weights
```

**Data flow:** Sources are registered in a database table (not config files). The scheduler runs one job per source type. Collectors fetch, deduplicate, and auto-tag articles on ingest. An optional LLM tagger scores relevance and generates narrative labels. The event aggregator clusters articles sharing the same narrative tag within 48-hour windows, computing a signal score (source count x avg relevance).

## Health Dashboard

The `/health` endpoint shows per-source status including last collection time, article counts, error rates, and volume anomalies. When running the frontend, navigate to the health page to see a visual overview.

![Health Dashboard](docs/health-dashboard.png)

## Run as Background Service (macOS)

Optional: run park-intel as a persistent background service using launchd. The service auto-restarts on crash.

```bash
./scripts/install-service.sh    # installs LaunchAgent and starts the service
./scripts/service-status.sh     # check if the service is running
./scripts/uninstall-service.sh  # stop and remove the service
```

Logs go to the `logs/` directory with automatic rotation.

## API Endpoints

### Core Data

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Per-source health status (registry-driven) |
| `GET /api/articles/latest` | Recent articles `?limit=20&source=rss&min_relevance=4` |
| `GET /api/articles/search` | Keyword search `?q=bitcoin&days=7` |
| `GET /api/articles/digest` | Articles grouped by source with top tags |
| `GET /api/articles/signals` | Topic heat + narrative momentum `?hours=24` |
| `GET /api/articles/sources` | Historical source statistics |

### Frontend Read Model

| Endpoint | Description |
|----------|-------------|
| `GET /api/ui/feed` | Priority-scored feed `?user=myname&window=24h` |
| `GET /api/ui/items/{id}` | Article detail with related items |
| `GET /api/ui/topics` | Topic list |
| `GET /api/ui/sources` | Active source list |
| `GET /api/ui/search` | Frontend search `?q=openai` |

### Events

| Endpoint | Description |
|----------|-------------|
| `GET /api/events/active` | Active events ranked by signal score |
| `GET /api/events/{id}` | Event detail with article timeline + price impacts |
| `GET /api/events/history` | Closed events archive `?tag=btc&days=30` |

### Users

| Endpoint | Description |
|----------|-------------|
| `POST /api/users` | Create user profile |
| `GET /api/users/{username}` | Get user profile and topic weights |
| `PUT /api/users/{username}/weights` | Update topic weights (0.0-3.0 per topic) |

## Development

```bash
# Run tests
pytest tests/

# Run in development mode (auto-reload on file changes)
PARK_INTEL_DEV=1 python main.py

# Run collectors manually
python scripts/run_collectors.py                # all sources
python scripts/run_collectors.py --source reddit # single source

# Run LLM tagger
python scripts/run_llm_tagger.py --limit 10     # score 10 unscored articles
python scripts/run_llm_tagger.py --backfill     # backfill historical articles

# Backfill ticker extraction
python scripts/backfill_tickers.py
```

## Project Structure

```
main.py                  # FastAPI entry point (port 8001)
config.py                # Source seed data, collector config, env loading
scheduler.py             # Registry-driven APScheduler
sources/                 # Source registry, adapters, seeding
collectors/              # 10 source-type collectors (BaseCollector pattern)
events/                  # Event aggregation (48h clustering, narratives)
tagging/                 # Keyword tagger, LLM tagger, ticker extractor
users/                   # User profiles and topic weights
bridge/                  # Quant bridge (price impact from external service)
api/                     # REST API routes
db/                      # SQLAlchemy models, migrations, database init
frontend/                # React + TypeScript + Vite frontend
scripts/                 # Management and utility scripts
tests/                   # 290+ pytest tests
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes and add tests
4. Run the test suite (`pytest tests/`)
5. Commit and push (`git push origin feature/my-feature`)
6. Open a Pull Request

## License

MIT
