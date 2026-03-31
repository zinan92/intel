# Codebase Concerns

**Analysis Date:** 2026-03-31

## Tech Debt

**Collector-specific configuration coupled to global config.py:**
- Issue: All collector parameters (HN keywords, Xueqiu KOL IDs, RSS feeds, etc.) hardcoded in `config.py`, limiting runtime flexibility and making it difficult to add/remove sources without code changes
- Files: `config.py` (lines 19-95, 98-200+), `collectors/*.py`
- Impact: Adding new RSS feeds or tweaking collector keywords requires editing config.py and restarting. Source registry was introduced as fix but config.py bootstrap data still maintained as duplicate source of truth
- Fix approach: Complete migration to registry-only configuration; remove collector-specific constants from config.py once all sources verified working via registry. Keep config.py for non-source settings only (API ports, db paths, API keys).

**LLM tagger subprocess invocation without proper shell escaping:**
- Issue: `subprocess.run()` with `claude` CLI in `tagging/llm.py:107-113` passes user message directly via `-p` flag. While not vulnerable to injection (args passed as list), no explicit input sanitization
- Files: `tagging/llm.py` (lines 107-113), dependency: `scripts/run_llm_tagger.py`
- Impact: Malformed article content could cause claude CLI to fail or hang. Rate limiting via sleep is weak protection against resource exhaustion if many articles trigger CLI errors simultaneously
- Fix approach: Add explicit content truncation/sanitization before passing to claude; implement exponential backoff on subprocess failures; add per-batch timeout with graceful failure handling.

**SQLite database connection not properly isolated per request:**
- Issue: `db/database.py:38-43` creates new sessions but doesn't implement proper context manager pattern. Sessions are manually closed with try/finally, but pattern is repeated across 20+ endpoints in `api/` routes
- Files: `db/database.py`, `api/routes.py`, `api/ui_routes.py`, `api/event_routes.py`, `api/user_routes.py`
- Impact: If an exception occurs between `get_session()` and `session.close()`, connection leaks. Under load (multiple concurrent collectors), connection pool could exhaust
- Fix approach: Implement FastAPI `Depends()` with context manager or use SQLAlchemy's `Session` as dependency injection. Create decorator `@with_session` to wrap route functions automatically.

**Scheduler state stored in module-level dict:**
- Issue: `scheduler.py:47-53` uses `_last_results` module-level dict to cache collector run results. No locking for concurrent access from scheduler threads
- Files: `scheduler.py` (lines 47-53, 108-116)
- Impact: Under high scheduler load (many collector jobs running in parallel), dict writes could be corrupted or reads return incomplete data. Health endpoint could report stale/inconsistent state
- Fix approach: Use `threading.Lock()` to protect `_last_results` dict access, or migrate to thread-safe queue.

## Known Bugs

**Xueqiu KOL collection fails silently with WAF 400 errors:**
- Symptoms: Some KOL feeds return `{"error": 400}` without articles. No retry logic; articles for that KOL are skipped entirely
- Files: `collectors/xueqiu.py` (lines 180-206, 205-206 shows error log)
- Trigger: Certain KOLs (e.g., "仓又加错-刘成岗") trigger Alibaba Cloud WAF blocks. Playwright stealth mode doesn't always succeed
- Workaround: Manually test KOL access; update XUEQIU_KOL_IDS in config to remove consistently blocked KOLs. Ensure XUEQIU_COOKIE is current
- Fix approach: Implement retry logic with exponential backoff; add circuit breaker per KOL ID; log detailed error context for debugging.

**Google News RSS parsing may drop articles due to HTML entity decoding:**
- Symptoms: Some feed items have incomplete title/content if they contain unescaped HTML
- Files: `collectors/google_news.py` (lines 31-35 show bozo exception handling, but silent pass)
- Trigger: Feed entries with malformed XML or broken CDATA sections
- Workaround: None; articles are silently dropped. Monitor logs for "bozo_exception" entries
- Fix approach: Implement fallback HTML parser; log bozo exceptions with full entry data; consider using `html.parser` with graceful degradation.

**Database WAL file growth not monitored:**
- Symptoms: `/data/park_intel.db-wal` grows to several MB (current: 4.0M). No automated cleanup or checkpoint strategy
- Files: `db/database.py` (lines 17-21 enables WAL but no checkpoint config)
- Trigger: High write frequency from scheduler jobs + inactive readers (WAL checkpoint waits for all readers to finish)
- Impact: Disk usage grows over time; WAL file not cleaned up on graceful shutdown
- Fix approach: Configure `PRAGMA wal_autocheckpoint=1000` (checkpoint every 1000 pages) in `_set_sqlite_pragma`; add shutdown hook to force final checkpoint.

**Article title/content truncation at 1000 chars in LLM tagger:**
- Symptoms: Long articles get cut off mid-sentence before LLM scoring, reducing relevance accuracy
- Files: `tagging/llm.py` (line 97: `[:1000]`)
- Impact: Relevance scores inaccurate for detailed articles; narrative tags miss context
- Fix approach: Increase truncation to 2000-3000 chars or implement smart truncation (sentence-aware); measure token count instead of char count for Claude API.

## Security Considerations

**CORS middleware allows all origins:**
- Risk: Any cross-origin client can access `/api/*` endpoints. If sensitive personal data or user weights added, unauthorized access possible
- Files: `main.py` (lines 62-68)
- Current mitigation: `/api/ui/feed` supports `?user=` param for personalization but doesn't validate request origin
- Recommendations: Restrict `allow_origins` to known frontend domains (e.g., localhost:5173 for dev, vercel domain for prod); implement request signing or API key for cross-origin calls.

**HTTP source feeds in RSS config:**
- Risk: Some hardcoded RSS URLs use plain `http://` (e.g., Paul Graham essays at line 157 of config.py), vulnerable to MITM attacks on insecure networks
- Files: `config.py` (lines 157, 158: antirez RSS over http)
- Current mitigation: None
- Recommendations: Migrate all RSS feeds to `https://` or implement certificate pinning; audit config.py for all insecure URLs; add lint rule to prevent http:// in source URLs.

**LLM tagger subprocess clears CLAUDECODE env var:**
- Risk: Clearing env vars assumes subprocess has different auth context. If Claude CLI relies on inherited env for MFA or custom config, subprocess call could fail or be intercepted
- Files: `tagging/llm.py` (line 106)
- Current mitigation: Env var cleared only for nested CLI calls
- Recommendations: Document why CLAUDECODE is cleared; add explicit env var allowlist instead of blacklist; validate claude CLI version compatibility.

**No input validation on config URLs:**
- Risk: Webhook URLs, monitor URLs, and RSS feed URLs in config.py not validated. Attacker could inject `file://` or `gopher://` URLs to cause SSRF
- Files: `config.py`, `collectors/webpage_monitor.py`, `collectors/rss.py`
- Current mitigation: `requests` library doesn't follow file:// by default, but no explicit check
- Recommendations: Validate all URLs are http/https at boot time; use URL validator schema (e.g., Pydantic URL type); test with malicious URLs in unit tests.

## Performance Bottlenecks

**Database query in health endpoint not indexed for concurrent load:**
- Problem: `/api/health` runs `session.query(Article).filter(Article.source.in_(...))` with `group_by` and `max()` aggregation. Without index on (source, collected_at), query scans all 80M DB file
- Files: `api/routes.py` (lines 48-57)
- Cause: One index on `idx_source` (line 61 of db/models.py) but aggregation query not optimized for it
- Current capacity: Runs ~500ms on 80M DB with 10 active sources; under 100 concurrent requests would timeout or lock DB
- Improvement path: Add composite index `(source, collected_at DESC)`; cache health result for 5 minutes; move aggregation to scheduled job instead of on-demand.

**Event aggregation scans all articles in 48h window:**
- Problem: `events/aggregator.py` clusters articles by narrative_tag in 48h windows. No index on `(narrative_tags, collected_at)`
- Files: `events/aggregator.py`, `db/models.py` (index defined at line 63)
- Cause: narrative_tags stored as JSON string; SQLite doesn't optimize JSON contains queries
- Current capacity: ~100ms per run; scales linearly with article count. At 10k articles/day, aggregation takes 1-2 seconds
- Improvement path: Denormalize narrative_tags into separate `article_tags` table with (article_id, tag) pairs + index; OR use SQLite JSON1 extension with proper indexes; OR pre-aggregate in materialized view.

**LLM tagger batches limited to 10 articles due to token constraints:**
- Problem: `tagging/llm.py:75` sets batch_size=10 to avoid token limit overruns. Each batch takes 2+ seconds (rate limit) + API call, so tagging 1000 articles takes 200+ seconds
- Files: `tagging/llm.py` (lines 75, 101, 68)
- Cause: No token counting; conservative batch size to avoid "too many tokens" errors from Claude
- Impact: LLM tagger job runs every 4 hours (scheduler.py:43), can only process ~50 articles per run (scheduled mode limit)
- Improvement path: Implement token counting using Anthropic token counter; increase batch size to 25-50 articles; OR implement streaming results to process articles as they're tagged.

**Database file growth: 80MB with no pruning strategy:**
- Problem: Articles never deleted; articles table grows indefinitely. No archival or retention policy
- Files: `db/models.py` (Article table design)
- Current capacity: 80M file with ~5-10 years data at current collection rate; no monitoring
- Improvement path: Implement 90-day retention policy; archive old articles to S3/cloud storage; add `deleted_at` soft delete field; implement scheduled purge job.

## Fragile Areas

**Xueqiu collector brittle to WAF changes:**
- Files: `collectors/xueqiu.py` (full file, especially Playwright integration lines 180-206)
- Why fragile: Relies on Playwright stealth mode + cookies to bypass Alibaba Cloud WAF. Any WAF rule update breaks silently; no monitoring for KOL fetch success rate
- Safe modification: Add comprehensive logging of each KOL fetch attempt with request/response metadata; implement health check endpoint for KOL accessibility; add circuit breaker per KOL
- Test coverage: No tests for actual Xueqiu API (skipped in CI); only mocked tests exist. Add integration test suite against staging credentials if available.

**LLM tagger assumes claude CLI availability:**
- Files: `tagging/llm.py` (lines 104-117, especially subprocess.run call), `scripts/run_llm_tagger.py`
- Why fragile: If claude CLI not in PATH or not authenticated, tagger silently returns empty results with only ERROR log. No validation at startup
- Safe modification: Check `which claude` at app startup; implement fallback scoring function (keyword-based rules); add tagger health check endpoint
- Test coverage: Unit tests mock claude CLI; no tests for missing/broken CLI scenario. Add mock test for returncode != 0 case.

**Webpage monitor state file corruption on concurrent writes:**
- Files: `collectors/webpage_monitor.py` (lines 18, 22-36 show read/write)
- Why fragile: State loaded, articles collected, state saved — all happen in same `collect()` call without locking. Two concurrent calls can overwrite state
- Safe modification: Use file-based locking (fcntl.flock on Unix); or move state to database; or use atomic file writes (write to temp file, rename)
- Test coverage: No test for concurrent collector invocations. Add test that simulates parallel calls to webpage monitor.

**Source registry migration incomplete; config.py still canonical for defaults:**
- Files: `config.py` (SOURCE_BOOTSTRAP lines 84-95), `sources/seed.py` (idempotent insert), `scheduler.py` (reads registry)
- Why fragile: If registry DB gets corrupted or deleted, seed will repopulate from config.py, but if config.py has stale/wrong source types, silent mismatch occurs
- Safe modification: Add validation that source_type in config.py matches actual collector class name; add startup verification that all registry entries are in scheduler
- Test coverage: No test validates registry consistency. Add integration test that verifies all config.py sources map to valid collectors.

## Scaling Limits

**SQLite write concurrency bottleneck:**
- Current capacity: ~5-10 concurrent writes before SQLITE_BUSY timeouts; WAL mode helps but doesn't solve fundamental SQLite single-writer limitation
- Limit: At 10 sources × 1-hour intervals + LLM tagger + event aggregation + API reads, all writes serialize through single WAL lock
- Scaling path: (1) Scale up to 100 articles/min → migrate to PostgreSQL with connection pooling; (2) Keep SQLite but implement write queue (collect articles to memory, batch write every 10s); (3) Split databases by source type.

**Memory usage: 300MB+ venv + process overhead:**
- Current capacity: Each collector loads full article list in memory before save. No streaming
- Limit: At 100k articles/day, single collector might allocate 500MB just for article list
- Scaling path: (1) Implement generator-based collection (fetch → save immediately); (2) Batch collector calls to process 100 articles at a time; (3) Use streaming SQLAlchemy bulk_insert_mappings.

**LLM API rate limits not enforced:**
- Current capacity: 4-hour tagger interval with 50 articles per run = ~300 articles/day. At 10 requests/sec rate limit from Anthropic, sustainable up to ~50k articles/day
- Limit: If collection rate increases to 500 articles/min and batch size goes to 50 articles, would hit API rate limits → LLM tagger fails, articles unscored
- Scaling path: Implement token bucket rate limiter; queue unscored articles and backoff on 429 errors; measure actual token usage per article to estimate sustainable batch size.

**Async bridge to quant-data-pipeline has no timeout per ticker:**
- Current capacity: `asyncio.gather()` waits for all tickers; if quant API slow for one ticker, all price lookups stall
- Limit: Event detail page could hang for 3+ seconds if quant API returns 500 error for one ticker
- Scaling path: Set timeout per individual ticker (currently only global timeout); implement fallback to cache or None if quant API unavailable.

## Dependencies at Risk

**APScheduler background scheduler with no persistent job state:**
- Risk: Jobs stored only in memory. If app crashes, scheduled jobs are lost (e.g., LLM tagger doesn't run until app restarts)
- Impact: If app goes down, data collection stops immediately; users don't know until health check fails
- Migration plan: (1) Switch to APScheduler with SQLAlchemy job store (jobs persist to DB); (2) Or implement separate systemd timer for critical jobs; (3) Add Kubernetes CronJob wrapper for cloud deployments.

**Playwright dependency optional but not gracefully handled:**
- Risk: If Playwright not installed, Xueqiu KOL collection silently disabled with warning log only
- Impact: Users don't know why Xueqiu data is missing; no metrics to track disabled collectors
- Migration plan: Implement explicit "disabled" status in source registry; add feature flag for optional collectors; warn on startup if required collectors are disabled.

**yfinance may break with Yahoo API changes:**
- Risk: yfinance is community-maintained wrapper around Yahoo Finance. No SLA; has been known to break during Yahoo updates
- Impact: Yahoo collector fails silently; users miss financial data alerts
- Migration plan: (1) Implement fallback to AlphaVantage or another financial data provider; (2) Add health check that validates yfinance works at startup; (3) Monitor yfinance GitHub for breaking changes.

**Claude CLI subprocess dependency (no fallback):**
- Risk: If claude CLI removed or authentication revoked, LLM tagger becomes completely non-functional
- Impact: Articles stop being scored; downstream event aggregation has no narrative_tags; user feed loses quality
- Migration plan: (1) Add fallback keyword-based tagger as baseline; (2) Implement API-based Claude scoring with explicit error handling; (3) Cache LLM responses to reduce API dependency.

## Missing Critical Features

**No data export or backup:**
- Problem: 80M SQLite DB file accumulates data but no backup strategy; if DB corrupts, no recovery
- Blocks: Can't migrate to PostgreSQL easily; can't restore from disasters
- Implementation: Add automated daily export to S3/cloud storage; implement `POST /api/export` endpoint for user data export; add restore-from-backup CLI tool.

**No API rate limiting or authentication:**
- Problem: `/api/*` endpoints have no rate limiting; anyone can spam requests or scrape entire database
- Blocks: Can't expose API publicly without DDoS risk; no user attribution for API usage
- Implementation: Add API key requirement; implement per-key rate limiting (e.g., 100 req/min); add request logging with user/key attribution.

**No audit log for config/registry changes:**
- Problem: If source registry row is modified or deleted, no record of who changed it or when
- Blocks: Can't debug "why did Yahoo collector stop?" if registry was silently modified
- Implementation: Add `audit_log` table with (timestamp, action, source_key, old_value, new_value, user); wrap all registry updates with audit logging.

**No admin UI for source registry management:**
- Problem: Adding/removing/disabling sources requires SQL or code change
- Blocks: Non-technical users can't manage data sources
- Implementation: Create admin dashboard at `/admin/sources`; CRUD endpoints for source registry; source health visualization.

## Test Coverage Gaps

**Untested: Concurrent collector executions:**
- What's not tested: Multiple collectors running in parallel (e.g., `_run_source_type` called simultaneously for different source types)
- Files: `scheduler.py` (lines 56-127), integration test coverage
- Risk: Module-level `_last_results` dict could be corrupted; session leaks could accumulate
- Priority: HIGH - scheduler runs jobs concurrently by design

**Untested: Database connection exhaustion:**
- What's not tested: Behavior when connection pool exhausted (e.g., 100 concurrent requests to `/api/health`)
- Files: `db/database.py`, `api/routes.py`
- Risk: App hangs or crashes without clear error message
- Priority: HIGH - app is intended to run behind load balancer

**Untested: LLM tagger with invalid JSON responses:**
- What's not tested: Edge case where claude CLI returns valid JSON but without required fields (e.g., missing `id` or `relevance_score`)
- Files: `tagging/llm.py` (lines 129-141 validates structure)
- Risk: Validation passes but downstream code expects fields and crashes
- Priority: MEDIUM - low probability but high impact

**Untested: Event aggregation with no articles:**
- What's not tested: Behavior when event aggregator runs but no articles in window
- Files: `events/aggregator.py`, `api/event_routes.py`
- Risk: Endpoint returns empty list or crashes (untested)
- Priority: LOW - edge case

**Untested: Quant bridge timeout with partial results:**
- What's not tested: When `asyncio.gather()` has timeout, what happens to partially completed ticker requests?
- Files: `bridge/quant.py` (lines 38-50)
- Risk: Some tickers return data, others missing; no clear signal to user about partial data
- Priority: MEDIUM - affects event detail page reliability

**Untested: Frontend API error handling:**
- What's not tested: Frontend behavior when API returns 5xx or network timeout
- Files: `frontend/src/api/client.ts` (lines 18-24 throw generic "API error")
- Risk: No user-friendly error display; users see blank pages or stale data
- Priority: MEDIUM - user experience degradation

---

*Concerns audit: 2026-03-31*
