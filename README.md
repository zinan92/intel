# park-intel

Qualitative signal workbench for collecting, scoring, and reading high-value market and frontier-tech content.

It includes:
- a FastAPI backend with source-layer health semantics and UI read-model endpoints
- a feed-first frontend workbench in `frontend/`
- active collectors for RSS, Hacker News, Xueqiu, GitHub trending, Yahoo Finance, Google News, ClawFeed, Reddit, GitHub releases, and webpage monitoring

## Quick Start

```bash
pip install -r requirements.txt

# Run collectors
python scripts/run_collectors.py
python scripts/run_collectors.py --source hackernews

# Start API server
python main.py
# -> http://127.0.0.1:8001/docs
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# -> http://localhost:5173
```

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/health` | Active-source healthcheck |
| `GET /api/articles/latest?limit=20&source=rss` | Latest articles |
| `GET /api/articles/search?q=bitcoin&days=7` | Search by keyword |
| `GET /api/articles/sources` | Historical source summary with counts |
| `GET /api/ui/feed` | Feed-first UI read model |
| `GET /api/ui/items/{id}` | Item detail with related items |
| `GET /api/ui/topics` | Topic list |
| `GET /api/ui/topics/{slug}` | Topic drill-down |
| `GET /api/ui/sources` | Active source list for UI |
| `GET /api/ui/sources/{name}` | Source drill-down |
| `GET /api/ui/search?q=openai` | UI search |

## Collectors

- **Hacker News** — Algolia API, score >= 50
- **RSS** — config-driven feed list in `config.RSS_FEEDS`
- **Xueqiu** — Chinese finance/KOL collector
- **GitHub Trending** — trending repos with keyword filtering
- **Yahoo Finance** — ticker/news collector
- **Google News** — query-driven RSS collector
- **ClawFeed** — curated KOL export via `clawfeed` CLI
- **Reddit** — top daily subreddit RSS feeds
- **GitHub Release** — pinned repo release monitoring
- **Webpage Monitor** — blog scrape + docs commit monitoring

## Data

SQLite DB lives under `data/park_intel.db` and is gitignored. Runtime state such as webpage monitor state also lives under `data/`.
