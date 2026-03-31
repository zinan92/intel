# Domain Pitfalls

**Domain:** Open-source Python data pipeline (monitoring, retry, packaging)
**Project:** Park-Intel (qualitative signal pipeline)
**Researched:** 2026-03-31

## Critical Pitfalls

Mistakes that cause rewrites, data loss, or abandoned open-source adoption.

### Pitfall 1: Retry Storms on Transient Failures

**What goes wrong:** Adding retry logic to all 10 collectors without jitter or circuit breakers causes a "thundering herd" effect. When an upstream service (e.g., Reddit API, HackerNews) has a brief outage, all retry attempts fire simultaneously after the backoff window, overloading the service again and triggering rate limits or IP bans.

**Why it happens:** Naive retry implementations use fixed exponential backoff without randomization. With APScheduler running collectors on the same interval, retries synchronize across source types.

**Consequences:** IP gets rate-limited or banned by upstream APIs. SQLite gets hammered with concurrent write attempts from retrying collectors. Xueqiu WAF (already fragile) permanently blocks the IP. Collectors that were working fine get starved of database write access.

**Prevention:**
- Use exponential backoff with **full jitter**: `delay = random(0, min(cap, base * 2^attempt))`
- Implement per-source-type circuit breakers: after N consecutive failures, stop retrying for a cooldown period (e.g., 30 minutes). Track circuit state in the source registry table.
- Set a **max retry count of 3** per collection cycle. If all retries fail, mark the source as degraded and move on.
- Never retry on 4xx errors (client error, won't fix itself). Only retry on 5xx, timeouts, and connection errors.

**Detection:** Monitor retry count per source per hour. If retries exceed 2x normal collection attempts, circuit breaker is not working.

**Phase:** Retry logic implementation (early milestone work).

**Confidence:** HIGH -- retry storms are well-documented in distributed systems literature and Google SRE guidance.

---

### Pitfall 2: SQLite Write Contention from Monitoring + Collection

**What goes wrong:** Adding a health monitoring system that writes run history, collector status, and metrics to the same SQLite database used for article storage creates write contention. SQLite allows only one writer at a time (even in WAL mode). Monitoring writes compete with collector writes, causing `SQLITE_BUSY` errors and `database is locked` timeouts.

**Why it happens:** The existing codebase already has concurrent collector writes (10 source types on APScheduler threads). Adding monitoring writes (job start/end timestamps, health check results, anomaly flags) doubles the write pressure. The current WAL file is already 4MB with no checkpoint strategy (per CONCERNS.md).

**Consequences:** Collectors silently drop articles when they can't acquire a write lock. Health dashboard shows stale data because its own writes fail. WAL file grows unbounded because checkpoint can't complete while readers are active (checkpoint starvation).

**Prevention:**
- **Batch monitoring writes**: Buffer health metrics in memory, flush to DB on a fixed interval (every 30-60 seconds), not on every event.
- **Use a separate SQLite database for monitoring data** (`data/health.db`). This eliminates write contention between monitoring and article collection entirely. Health dashboard reads from health.db; article collection writes to park_intel.db.
- **Configure `PRAGMA busy_timeout = 5000`** (5 seconds) on all connections so writers wait instead of failing immediately.
- **Add `PRAGMA wal_autocheckpoint = 1000`** as identified in CONCERNS.md.
- **One connection per thread**: Never share SQLAlchemy sessions across APScheduler threads. The existing session isolation issue (CONCERNS.md) must be fixed before adding monitoring writes.

**Detection:** Log all `SQLITE_BUSY` errors with source context. If any appear after adding monitoring, write contention is the cause. Monitor WAL file size -- growth beyond 10MB indicates checkpoint starvation.

**Phase:** Health dashboard implementation. Must fix session isolation (CONCERNS.md tech debt) first.

**Confidence:** HIGH -- SQLite concurrent write limitations are well-documented. The project already shows symptoms (4MB WAL file).

---

### Pitfall 3: Breaking Existing Collectors During Error Surfacing Refactor

**What goes wrong:** Refactoring collectors to surface errors (replacing silent `return []` with exceptions or error reporting) inadvertently breaks the scheduler's error handling assumptions. The scheduler expects collectors to always return a list. If a collector now raises an exception, the scheduler thread crashes, killing all subsequent scheduled jobs for that source type.

**Why it happens:** The current contract between `BaseCollector.collect()` and `scheduler.py` is implicit: collectors return `[]` on failure, scheduler logs it as "0 articles collected." Changing this contract without updating all call sites causes cascading failures.

**Consequences:** A single collector exception kills the APScheduler thread for that source type. Because APScheduler BackgroundScheduler runs jobs in a thread pool, one unhandled exception doesn't crash the whole scheduler, but that specific job never runs again until restart. With no persistent job state (CONCERNS.md), the operator doesn't know until they check manually.

**Prevention:**
- **Keep the return-list contract**. Don't change `collect()` to raise exceptions. Instead, return a result object: `CollectorResult(articles=[], errors=[], warnings=[])`.
- **Add error reporting alongside the existing flow**, not replacing it. Collectors still return articles; errors are captured as metadata.
- **Wrap every collector invocation in scheduler.py** with try/except that logs the exception and records it in health state, but never lets it propagate to APScheduler.
- **Refactor one collector at a time** with its tests, not all 10 at once. Verify the scheduler still runs correctly after each change.
- **Add an integration test**: run the scheduler with a deliberately failing collector, verify other collectors continue running.

**Detection:** After each collector refactor, run `pytest tests/` and manually trigger the scheduler for that source type. If test count drops or scheduler logs show "Job ... raised an exception," the contract was broken.

**Phase:** Error surfacing (first phase of milestone work). This is the highest-risk refactor because it touches every collector.

**Confidence:** HIGH -- this exact pattern is described in the CONCERNS.md (collectors return [] on error, scheduler has no persistent state).

---

### Pitfall 4: launchd Permission and Environment Failures on macOS

**What goes wrong:** The launchd plist works in testing but fails silently in production. Python can't find modules because PATH is minimal. The .env file can't be read because launchd runs from `/` not the project directory. The virtual environment isn't activated. Logs go to /dev/null because StandardOutPath wasn't set.

**Why it happens:** launchd runs in a stripped-down environment with almost no environment variables (no PATH beyond `/usr/bin:/bin:/usr/sbin:/sbin`, no VIRTUAL_ENV, no working directory context). Developers test by running `launchctl load` from their terminal where these variables exist, masking the problem.

**Consequences:** Service appears to start (launchctl shows it running) but the Python process crashes immediately or runs with wrong dependencies. No articles collected, no errors visible. The operator thinks the service is running fine.

**Prevention:**
- **Use absolute paths for everything** in the plist: Python binary (`/Users/wendy/work/trading-co/park-intel/.venv/bin/python`), script path, working directory.
- **Set WorkingDirectory** in the plist so relative paths in config.py (e.g., `data/park_intel.db`) resolve correctly.
- **Set EnvironmentVariables** in the plist for any needed env vars, or use a wrapper shell script that sources `.env` before running Python.
- **Set StandardOutPath and StandardErrorPath** to log files (e.g., `~/Library/Logs/park-intel-stdout.log`).
- **Test with `launchctl kickstart`** not `launchctl load` from a terminal -- kickstart more closely mimics the real launch environment.
- **Add a startup health check**: the first thing main.py does is write a timestamp to a known file (e.g., `data/.last_startup`). If this file is stale, the service isn't running.
- **File permissions**: plist must be owned by the user and have `644` permissions, or launchd will refuse to load it with "Dubious permissions" error.

**Detection:** Check `launchctl list | grep park-intel` -- if PID is `-` (dash), the service crashed. Check StandardErrorPath log for import errors or path failures.

**Phase:** Persistent deployment phase. Test this before documenting it for open-source users.

**Confidence:** HIGH -- launchd permission/environment issues are the #1 complaint in Apple Community forums for Python services.

---

### Pitfall 5: Open-Source Onboarding Fails at Clone-to-Run

**What goes wrong:** New users clone the repo, run `pip install`, and the app crashes because: (1) no `.env.example` to know what variables are needed, (2) `data/` directory doesn't exist, (3) SQLite database path is hardcoded to a developer-specific location, (4) Playwright/Chrome not installed for Xueqiu collector, (5) `claude` CLI not in PATH for LLM tagger. Users open issues, get no response, and abandon the project.

**Why it happens:** The developer's machine has all dependencies, env vars, and directories pre-configured. The "works on my machine" problem. No one tests the fresh-clone experience because the developer never does a fresh clone.

**Consequences:** Zero adoption. Open-source release fails at the first hurdle. Every issue filed is a variant of "can't install" or "crashes on startup."

**Prevention:**
- **`.env.example`** with every variable, commented with required/optional status and where to get the value. Never include real tokens.
- **`data/` directory auto-creation**: `os.makedirs("data", exist_ok=True)` at startup, not in README instructions.
- **Graceful degradation for optional deps**: If Playwright not installed, skip Xueqiu collector with a clear startup log message: "Xueqiu collector disabled: playwright not installed. Run `pip install playwright && playwright install chromium` to enable."
- **CLI validation at startup**: Check for `claude` CLI presence. If missing, disable LLM tagger with clear message, not a crash.
- **Test the fresh-clone experience**: Create a GitHub Action that does `git clone`, `pip install`, `python main.py` and verifies the app starts with zero config.
- **Separate `requirements.txt` from `requirements-dev.txt`**: Core deps only in the main file. Playwright, pytest, etc. in dev.
- **Makefile or setup script**: `make setup` that creates venv, installs deps, copies `.env.example` to `.env`, creates data directory, runs migrations.

**Detection:** If you can't `git clone && pip install -r requirements.txt && python main.py` on a clean machine and see the health dashboard, onboarding is broken.

**Phase:** Open-source packaging (final phase of milestone). But start `.env.example` and auto-directory-creation early -- they cost nothing.

**Confidence:** HIGH -- this is the most common failure mode for open-source Python projects. Every popular project (FastAPI, Streamlit, etc.) has solved this with excellent first-run experience.

## Moderate Pitfalls

### Pitfall 6: Over-Engineering the Health Dashboard

**What goes wrong:** Building a full monitoring system (Prometheus metrics, Grafana dashboards, alert rules) when the project needs a simple "are my collectors running?" page. Scope creeps from "show source freshness" to "real-time WebSocket updates, anomaly detection ML, historical trend analysis."

**Prevention:**
- **MVP dashboard is one page**: A table of sources, last collection time, article count in last 24h, status (green/yellow/red). No WebSocket, no real-time, no ML.
- **Freshness thresholds are simple**: Green = collected in last 2x scheduled interval. Yellow = 3x interval. Red = beyond 3x or error on last run.
- **Store health data in memory + periodic DB flush**, not a full time-series database.
- **No Prometheus/Grafana**: This is a single-user self-hosted tool, not a production SaaS. A JSON endpoint + React table is sufficient.
- Timebox dashboard work to 1-2 days. If it takes longer, scope is too big.

**Detection:** If you're writing WebSocket handlers or discussing "real-time anomaly detection," you've over-scoped.

**Phase:** Health dashboard implementation. Define the MVP table before writing any code.

---

### Pitfall 7: Monitoring Writes Corrupt Health State on Unclean Shutdown

**What goes wrong:** Health monitoring state stored in a module-level dict (`_last_results` in scheduler.py, per CONCERNS.md) is lost on crash. If health state is partially written to DB during a crash, the dashboard shows inconsistent data (some sources show "running," others show "unknown").

**Prevention:**
- **Atomic health state writes**: Write all source statuses in a single transaction, not one-by-one.
- **Add a `last_heartbeat` timestamp** to the health state. Dashboard treats any source with heartbeat older than 2x its interval as "unknown" rather than trusting the stored status.
- **On startup, mark all sources as "starting"** before the first collection cycle completes. Don't inherit stale state from the DB.
- Fix the threading.Lock issue identified in CONCERNS.md (scheduler.py:47-53) before adding any monitoring writes.

**Detection:** Kill the process with `kill -9` mid-collection, restart, check if dashboard shows accurate state. If any source shows "success" from before the crash, state recovery is broken.

**Phase:** Health monitoring implementation. Depends on fixing the `_last_results` threading issue first.

---

### Pitfall 8: Hardcoded Developer Paths Leak into Open-Source Release

**What goes wrong:** Paths like `/Users/wendy/work/trading-co/park-intel/data/park_intel.db`, Xueqiu cookies, specific KOL IDs, and personal RSS feeds make it into the released code. Users fork the project and inherit configuration that only works on the developer's machine.

**Prevention:**
- **Audit config.py before release**: The CONCERNS.md identifies hardcoded KOL IDs (lines 19-95), RSS feeds (lines 98-200+). These must be moved to `.env` or a user-configurable file.
- **Use relative paths everywhere**: `data/park_intel.db` not absolute paths. Resolve relative to `__file__` or working directory.
- **Separate "example" sources from "personal" sources**: Ship with a default `sources.json` containing 5-10 public RSS feeds, HackerNews, Reddit. User adds their own sources via registry API or config file.
- **Pre-commit hook**: Add a check that rejects commits containing `/Users/` paths or known personal tokens.
- **`.gitignore` audit**: Ensure `data/*.db`, `.env`, `*.cookie`, `*.token` are all ignored.

**Detection:** `grep -r "/Users/" --include="*.py"` in the repo. If any hits, paths are hardcoded.

**Phase:** Open-source packaging. Do the audit before creating the public release tag.

---

### Pitfall 9: Retry Logic Masks Permanent Failures

**What goes wrong:** Retry logic treats all errors the same. A collector that fails because the API changed its response format retries forever, consuming resources and filling logs with identical errors. The operator doesn't realize the collector is permanently broken because the health dashboard shows "retrying" not "broken."

**Prevention:**
- **Classify errors**: Transient (timeout, 503, connection reset) vs. permanent (404, 403, parse error, schema change). Only retry transient errors.
- **Circuit breaker with escalation**: After circuit opens (too many failures), change source status from "retrying" to "broken" and require manual intervention.
- **Log the first error with full context** (URL, status code, response body snippet). Log subsequent retries at DEBUG level to avoid log flooding.
- **Health dashboard must distinguish** "healthy," "degraded" (intermittent failures), and "broken" (circuit open) states.

**Detection:** If a source has been retrying for more than 1 hour without success, it's probably a permanent failure masquerading as transient.

**Phase:** Retry logic implementation. Define error classification before writing retry code.

---

### Pitfall 10: Database Migration Breaks Existing User Data

**What goes wrong:** Adding health monitoring tables, modifying the source registry schema, or adding indexes requires schema changes. Without a proper migration strategy, existing users lose their `park_intel.db` data on upgrade, or the app crashes because the old schema doesn't have new columns.

**Prevention:**
- **The existing `db/migrations.py` uses idempotent migrations** -- preserve this pattern. Every new column/table addition must be idempotent (IF NOT EXISTS, try/except for ALTER TABLE).
- **Never drop or rename columns** in a migration. Add new columns with defaults; deprecate old ones.
- **Test migrations on a copy of the real 80MB database**, not just an empty test DB.
- **Document upgrade path**: "If upgrading from v0.x, run `python -m db.migrations` before starting the app."
- **Back up before migrate**: Add a `--backup` flag to the migration script that copies the DB file before modifying it.

**Detection:** Run migrations on a fresh DB and on the existing 80MB DB. If either fails, the migration is broken.

**Phase:** Any phase that adds database tables (health monitoring, enhanced source registry). Plan migrations before writing feature code.

## Minor Pitfalls

### Pitfall 11: APScheduler Event Listeners Not Wired for Crash Detection

**What goes wrong:** APScheduler's BackgroundScheduler runs jobs in daemon threads. If a job raises an unhandled exception, APScheduler logs it but the job is rescheduled normally. However, if the scheduler thread itself dies (memory error, interpreter crash), there's no detection -- the main FastAPI process stays up but no collections happen.

**Prevention:**
- Wire APScheduler event listeners (`EVENT_JOB_ERROR`, `EVENT_JOB_MISSED`) to the health monitoring system.
- Add a **scheduler heartbeat**: a lightweight job that runs every 5 minutes and writes a timestamp. If the timestamp is stale, the scheduler is dead.
- In the launchd plist, set `KeepAlive: true` so macOS restarts the entire process if it exits.

**Detection:** Health dashboard shows "scheduler last heartbeat: 47 minutes ago" -- scheduler thread is dead.

**Phase:** Scheduler health monitoring.

---

### Pitfall 12: README-Driven Development for Open-Source

**What goes wrong:** Writing an elaborate README with features that don't exist yet, or documenting the ideal setup process before actually testing it. Users follow the README, hit undocumented edge cases, and lose trust.

**Prevention:**
- **Write README last**, after the fresh-clone CI test passes.
- **Test every README command** on a clean environment before publishing.
- **Keep README short**: Quick start (5 steps), configuration reference, architecture diagram. Link to docs/ for details.
- **Add a "Known Limitations" section** so users know what doesn't work yet.

**Detection:** If README mentions features not in the codebase, it's aspirational documentation.

**Phase:** Final packaging phase, after all functional work is done.

---

### Pitfall 13: CORS and Security Hardening Forgotten in Open-Source Release

**What goes wrong:** The current CORS configuration allows all origins (per CONCERNS.md). For a personal tool this is fine, but once open-sourced, users might expose their instance to the network. Without rate limiting or CORS restrictions, the API is vulnerable to abuse.

**Prevention:**
- **Default CORS to localhost only** (`http://localhost:5174`, `http://127.0.0.1:5174`). Document how to add custom origins.
- **Add basic rate limiting** via `slowapi` or middleware -- 100 req/min per IP is sufficient.
- **Don't add authentication** (out of scope per PROJECT.md) but document that the API should not be exposed to the public internet without a reverse proxy.

**Detection:** `grep "allow_origins" main.py` -- if it shows `["*"]`, CORS is still wide open.

**Phase:** Open-source packaging. Quick fix, low effort.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Error surfacing | Breaking collector contract (#3) | Return result objects, don't raise exceptions |
| Retry logic | Retry storms (#1), masking permanent failures (#9) | Jitter + circuit breakers + error classification |
| Health dashboard | Over-engineering (#6), SQLite contention (#2) | MVP table only, separate health.db |
| Scheduler monitoring | APScheduler crash undetected (#11), stale state (#7) | Heartbeat job + event listeners |
| Persistent deployment | launchd env/path failures (#4) | Absolute paths, wrapper script, log files |
| Database changes | Migration breaks data (#10) | Idempotent migrations, test on real DB |
| Open-source packaging | Clone-to-run failure (#5), hardcoded paths (#8), CORS (#13) | Fresh-clone CI test, path audit, localhost CORS |

## Dependency Between Pitfalls

```
Fix session isolation (CONCERNS.md)
  --> then add monitoring writes (avoids #2)
  --> then add health dashboard (avoids #6, #7)

Fix _last_results threading (CONCERNS.md)
  --> then add scheduler heartbeat (avoids #11)
  --> then wire event listeners

Error surfacing (#3) must be done before retry logic (#1)
  -- need to know what errors look like before deciding retry policy

Retry logic (#1) + error classification (#9) should be designed together
  -- same abstraction layer

Open-source packaging (#5, #8, #12, #13) is the final phase
  -- depends on all functional work being stable
```

## Sources

- [Google SRE - Managing Data Processing Pipelines](https://sre.google/sre-book/data-processing-pipelines/) -- retry storms, pipeline reliability patterns
- [Handling Thundering Herd Problems in Python](https://johal.in/handling-thundering-herd-problems-in-python-caching-layers-with-jittered-backoff-3/) -- jittered backoff implementation
- [SQLite Concurrent Writes and "database is locked" Errors](https://tenthousandmeters.com/blog/sqlite-concurrent-writes-and-database-is-locked-errors/) -- WAL mode limitations, busy_timeout
- [SQLite WAL Documentation](https://www.sqlite.org/wal.html) -- checkpoint starvation, single-writer constraint
- [Python SQLite Database Locked Despite Large Timeouts](https://www.py4u.org/blog/python-sqlite-database-locked-despite-large-timeouts/) -- unclosed connections, connection-per-thread
- [launchd Tutorial](https://www.launchd.info/) -- plist permissions, environment variables, absolute paths
- [How to Run Python Script at macOS Startup](https://www.tutorialpedia.org/blog/run-python-script-at-os-x-startup/) -- PATH issues, permission errors
- [APScheduler User Guide](https://apscheduler.readthedocs.io/en/3.x/userguide.html) -- event listeners, BackgroundScheduler daemon threads
- [Python APScheduler Monitoring](https://cronradar.com/blog/python-scheduler-monitoring) -- crash detection, job state persistence
- [Common Mistakes with .env Files](https://medium.com/byte-of-knowledge/common-mistakes-developers-make-with-env-files-1dbd72272eba) -- .env.example, secret exposure
- [Python Packaging User Guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/) -- src layout, dependency management
- Park-Intel CONCERNS.md -- project-specific tech debt and known bugs
