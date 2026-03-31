# External Integrations

**Analysis Date:** 2026-03-31

## APIs & External Services

**News & Content:**
- Hacker News (Algolia API) - Top stories and keyword search
  - SDK/Client: `requests` library
  - Config: `HN_API_BASE = "https://hn.algolia.com/api/v1"` in `config.py`
  - Implementation: `collectors/hackernews.py`
  - Auth: None (public API)

- RSS/Atom Feeds - Generic feed parsing
  - SDK/Client: `feedparser` library
  - Implementation: `collectors/rss.py`, `collectors/reddit.py`, `collectors/google_news.py`
  - Auth: None (public feeds)

- Google News - News articles search
  - SDK/Client: `feedparser` library
  - Config: `GOOGLE_NEWS_QUERIES` list in `config.py` with search parameters
  - Implementation: `collectors/google_news.py`
  - Auth: None (public RSS feed)

**Market Data:**
- Yahoo Finance - Stock/commodity quotes and news
  - SDK/Client: `yfinance` library
  - Config: `YAHOO_TICKERS` list and `YAHOO_SEARCH_KEYWORDS` in `config.py`
  - Implementation: `collectors/yahoo_finance.py`
  - Auth: None (public API)

- Xueqiu (雪球) - Chinese investment platform
  - SDK/Client: `requests` library with custom headers/cookies
  - Config: `XUEQIU_KOL_IDS` list (20 KOL profiles) in `config.py`
  - Implementation: `collectors/xueqiu.py`
  - Auth: Optional `XUEQIU_COOKIE` environment variable for authenticated access

**Developer Platforms:**
- GitHub - Trending repos and release monitoring
  - SDK/Client: `requests` library
  - Config: `SOCIAL_KOL_HANDLES` and collectors configuration
  - Implementation: `collectors/github_trending.py`, `collectors/github_release.py`
  - Auth: Optional `GITHUB_TOKEN` environment variable for higher rate limits

- Social KOL (Twitter/X equivalent) - Monitoring handles
  - SDK/Client: `requests` library
  - Config: `SOCIAL_KOL_HANDLES` list in `config.py` (30+ handles)
  - Implementation: `collectors/social_kol.py`
  - Auth: Not documented (likely requires bearer token or session)

**Internal Integration:**
- Quant Data Pipeline (sibling project) - Price snapshot data
  - SDK/Client: `httpx` async HTTP client
  - Endpoint: `QUANT_API_BASE_URL` (default: `http://localhost:8000`)
  - API: `GET /api/price/{ticker}?date=YYYY-MM-DD`
  - Implementation: `bridge/quant.py`
  - Timeout: 3.0 seconds with graceful fallback to None on failure
  - Used by: Event detail enrichment for ticker price impacts

## Data Storage

**Databases:**
- SQLite (local)
  - Path: `data/park_intel.db`
  - ORM: SQLAlchemy 2.0+ with declarative models
  - Client: `sqlalchemy` with `sqlalchemy.orm.Session`
  - Journal Mode: WAL (Write-Ahead Logging) enabled for concurrent writes
  - Connection Pool: Single-threaded with 30-second timeout
  - Tables: `articles`, `source_registry`, `events`, `event_articles`, `user_profiles`, `briefs`

**File Storage:**
- Local filesystem only
- Logs: `logs/park-intel.log` (rotating file handler, 10 MB per file, 5 backups)
- Data: SQLite database file at `data/park_intel.db`

**Caching:**
- None detected - All data served fresh from SQLite

## Authentication & Identity

**Auth Provider:**
- Custom/None - No centralized authentication system
- Implementation: User profiles are created via API POST `/api/users`
- Model: Simple `UserProfile` with `username` and topic weights (JSON)
- Session: Stateless HTTP (no cookies or JWT observed)

## Monitoring & Observability

**Error Tracking:**
- None detected (no Sentry, Rollbar, etc.)
- Errors logged via Python `logging` module

**Logs:**
- Python `logging` with rotating file handler
- Location: `logs/park-intel.log`
- Format: `%(asctime)s %(levelname)s [%(name)s] %(message)s`
- Rotation: 10 MB per file, 5 backup files retained
- Level: INFO

## CI/CD & Deployment

**Hosting:**
- Not specified (local development evident)
- Likely Vercel or similar for frontend (Vite build supports static deployment)
- Backend: FastAPI deployable to any ASGI host

**CI Pipeline:**
- None detected in codebase
- Git repo present at `.git/`

## Environment Configuration

**Required env vars:**
- `ANTHROPIC_API_KEY` - Claude API key for LLM tagging (optional if using CLI)
- `XUEQIU_COOKIE` - Xueqiu session cookie for authenticated KOL access (optional)
- `GITHUB_TOKEN` - GitHub PAT for rate limit increase (optional)
- `QUANT_API_BASE_URL` - URL to quant-data-pipeline (default: `http://localhost:8000`)

**Optional env vars:**
- `QUANT_API_BASE_URL` - Defaults to `http://localhost:8000` if not set

**Secrets location:**
- `.env` file at project root (not committed to git)
- Loaded via `python-dotenv` in `config.py`

## Webhooks & Callbacks

**Incoming:**
- None detected

**Outgoing:**
- None detected

## Collector-Specific Configuration

**Hacker News:**
- `HN_MIN_SCORE` - Minimum score threshold for stories (default: 20)
- `HN_HITS_PER_PAGE` - Results per API call (default: 50)
- `HN_SEARCH_KEYWORDS` - List of 13 keywords for targeted searches (crypto, AI, trading, etc.)

**Xueqiu:**
- `XUEQIU_KOL_IDS` - 20 investment KOL profiles with name, ID, and tag category
- Tags: macro, value, tech, trading, us-stock

**Yahoo Finance:**
- `YAHOO_TICKERS` - 5 commodity/ETF tickers (gold futures, miners)
- `YAHOO_SEARCH_KEYWORDS` - 6 search phrases (gold price, XAUUSD, etc.)

**Google News:**
- `GOOGLE_NEWS_QUERIES` - 7 queries in English and Chinese with locale/language settings

**Social KOL:**
- `SOCIAL_KOL_HANDLES` - 30+ Twitter/X handles across categories (llm, fintech, crypto, etc.)

## Scheduler Configuration

**APScheduler:**
- Background scheduler with registry-driven intervals
- Per-source interval: Loaded from `source_registry.schedule_hours` (default: 1 hour)
- LLM tagger job: Runs every 4 hours (configurable in `SchedulerConfig`)
- Timezone: Asia/Shanghai (configurable)
- Last run results cached in memory and served by health endpoint

---

*Integration audit: 2026-03-31*
