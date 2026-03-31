# Feature Landscape: Pipeline Health Monitoring & Open-Source Reliability

**Domain:** Self-hosted data pipeline health monitoring, collector reliability, developer onboarding
**Researched:** 2026-03-31
**Context:** park-intel already has a basic `/api/health` endpoint (per-source status, freshness age_hours, article count, last_run error). This research covers what the next milestone needs to add.

## Table Stakes

Features users expect from any data pipeline with a health dashboard. Missing = the tool feels unreliable or unobservable.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Per-source status indicator** (ok/stale/degraded/no_data) | Airflow, Dagster, Prefect all show per-task/asset status with color coding. Users need instant visual triage. | Low | Already exists in `/api/health` API. Frontend needs visual representation (color-coded cards or rows). |
| **Data freshness per source** | Dagster treats freshness as a first-class concept with freshness policies. Users expect to see "last collected 2h ago" at a glance. | Low | Already exists as `age_hours` in API. Frontend needs human-readable display ("2h ago", "3 days ago") with color thresholds. |
| **Collection volume (article counts)** | Every pipeline dashboard shows row/record counts. Monte Carlo's 5 pillars include Volume as core metric. Users need to see if a source suddenly returns 0 articles. | Low | Already exists as `count` in API. Frontend needs to display it. Consider adding 24h/7d counts for trend context. |
| **Last run error visibility** | Airflow shows task logs and error messages inline. Silent failures are the #1 complaint in data pipelines. Errors must be surfaced, not swallowed. | Low | `last_run_error` exists in API. Frontend needs to show error messages with expandable detail. |
| **Run history (last N runs per source)** | Airflow's Grid View shows a matrix of past runs per task. Dagster shows materialization history. Without history, you can only see "right now" not "pattern over time". | Medium | Currently only stores last run in memory (`_last_results` dict). Needs: persistent `collector_runs` table with timestamp, articles_fetched, articles_saved, duration, error. API to query last N runs per source. |
| **Retry logic for transient failures** | Prefect and Airflow both have built-in retry with configurable attempts and backoff. External APIs fail transiently (rate limits, timeouts). Without retry, a single HTTP 429 marks a source as failed until next scheduled run. | Medium | Does not exist. Add to `BaseCollector` with configurable max_retries (default 3) and exponential backoff. Log each retry attempt. |
| **Collector error categorization** | Users need to distinguish "API key expired" (needs human action) from "timeout" (will self-heal). Airflow differentiates task failure reasons. | Low | Currently errors are raw strings. Categorize into: `transient` (timeout, rate limit, connection), `auth` (401/403, expired token), `parse` (unexpected response format), `config` (missing env var). |
| **Scheduler liveness indicator** | If the APScheduler thread crashes silently, the entire pipeline stops collecting but the API still serves stale data. Users expect a "scheduler running" heartbeat like Airflow's scheduler health. | Low | Add a heartbeat timestamp updated each scheduler tick. Health endpoint reports scheduler as alive/dead based on recency. |
| **Startup health validation** | On `python main.py`, report which sources are configured, which are missing tokens and will be skipped, and confirm scheduler started. Airflow and Dagster both validate configuration at startup. | Low | Currently no startup summary. Add a boot log that lists: N active sources, M skipped (missing tokens), scheduler started at HH:MM. |
| **Frontend health dashboard page** | Airflow has a dedicated DAG monitoring view. Dagster has the asset catalog. A JSON API alone is not a dashboard -- users expect a visual page. | Medium | New React page at `/health` or `/dashboard`. Renders per-source cards with status, freshness, volume, last error. No external charting library needed for v1 -- use colored divs and text. |

## Differentiators

Features that set the project apart from "just another data scraper." Not expected, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Volume trend sparklines** | Show 7-day article volume trend per source as a tiny inline chart. Lets users spot degradation ("RSS used to fetch 50/day, now fetching 5"). Dagster+ shows this for asset materialization frequency. | Medium | Requires storing daily collection counts (can aggregate from `collector_runs` table). Use a simple SVG sparkline (no charting library). |
| **Freshness policy per source** | Different sources have different expected cadences. HackerNews should refresh hourly, GitHub releases daily. A single 24h stale threshold is too coarse. Dagster's freshness policies are exactly this concept. | Low | Add `expected_freshness_hours` column to `source_registry` table. Health endpoint compares actual age against per-source threshold instead of hardcoded 24h. Seed with sensible defaults. |
| **Anomaly detection (simple)** | Flag when a source's volume drops below 50% of its 7-day rolling average. Monte Carlo and Elementary both offer this. For a self-hosted tool, a simple statistical check beats no check. | Medium | Compute rolling 7-day average from `collector_runs` history. Compare today's count. Flag as `anomaly` status if below 50% threshold. No ML needed -- just arithmetic. |
| **Auto-recovery with dead-letter logging** | When retry logic exhausts attempts, log the failure to a `dead_letters` table with full context (URL, error, timestamp, attempt count). Enables manual investigation without losing the failed work. | Low | Add `collector_dead_letters` table. After max retries exhausted, insert a record. Dashboard shows dead letter count per source. |
| **Source dependency health** | Show whether external dependencies (quant-data-pipeline on port 8000, Claude API for LLM tagging) are reachable. Pipeline tools like Prefect show upstream dependency status. | Low | Ping quant bridge endpoint and Claude API on health check. Report as separate "dependencies" section in health response. |
| **Historical freshness timeline** | Show a 30-day timeline of when each source was fresh vs stale. Helps answer "was this source reliable last month?" Dagster+ offers this in their asset health view. | High | Requires storing periodic snapshots or computing from `collector_runs`. Needs a timeline visualization component. Defer to later phase. |
| **One-command setup validation** | `python scripts/check_setup.py` that validates: Python version, dependencies installed, .env exists, required vs optional tokens present, database writable, ports available. Critical for open-source onboarding. | Low | Script that runs checks and prints a clear pass/fail report. No external dependencies. |
| **Graceful degradation reporting** | When optional sources are skipped (missing tokens), show them in the dashboard as "disabled (missing GITHUB_TOKEN)" rather than hiding them entirely. Users should see what they could enable. | Low | Already have source registry with active/retired. Add a `disabled_reason` field or compute from missing env vars at startup. Show in dashboard with "enable" instructions. |

## Anti-Features

Features to explicitly NOT build. These add complexity without proportional value for a self-hosted single-user tool.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Complex alerting system (email/Slack/PagerDuty)** | Enterprise feature. Single user checks their own dashboard. Adding notification integrations means maintaining OAuth flows, webhook configs, and delivery reliability for a tool that one person uses. PROJECT.md explicitly puts Telegram/Slack notifications out of scope. | Color-coded dashboard with clear status. If the user wants alerts, they can curl the health API from a cron job. |
| **Multi-user RBAC / team dashboards** | Out of scope per PROJECT.md. Self-hosted single-user tool. Adding auth adds database tables, session management, middleware, and UI for something nobody needs. | Single-user dashboard. No login required. |
| **ML-based anomaly detection** | Requires training data, model management, and tuning. The simple "50% below rolling average" check catches 90% of issues. Soda Core and Elementary use ML but they're dedicated observability platforms. | Simple statistical thresholds (percentage drop from rolling average). |
| **Data lineage visualization** | Dagster's lineage graph tracks asset dependencies across a complex DAG. Park-intel has a linear pipeline (collect -> tag -> aggregate). No DAG to visualize. | Show the pipeline stages as a simple flow diagram in docs, not a dynamic lineage graph. |
| **SLA monitoring with breach notifications** | Enterprise pattern for teams with on-call rotations. A solo trader checking their own dashboard doesn't need SLA breach escalation. | Freshness policies with visual status (green/yellow/red) are sufficient. |
| **Custom metric exporters (Prometheus/StatsD)** | Adds operational complexity (need to run Prometheus, configure Grafana). The built-in dashboard is sufficient for single-user. | Built-in health dashboard. If users want Prometheus, the health API JSON is easy to scrape externally. |
| **Log aggregation UI** | Building a log viewer is reinventing Kibana. Python's logging module writes to stdout/files. | Structured logging to file. Users `tail -f` or use their preferred log tool. Surface only errors in the dashboard. |
| **Database migration to support monitoring** | Do NOT migrate from SQLite to Postgres just for monitoring features. SQLite handles the write volume of a single-user collector pipeline fine. | Add monitoring tables to existing SQLite database. Use WAL mode if not already enabled. |

## Feature Dependencies

```
Scheduler Heartbeat ──────────────────────────────> Frontend Health Dashboard
                                                          ^
Per-source Freshness Policy ──> Health Status Logic ──────┘
                                      ^
Retry Logic ──> Error Categorization ─┘
                      |
                      v
              Dead Letter Logging

Run History Table ──> Volume Trend Sparklines
       |                     |
       v                     v
  Anomaly Detection    Frontend Health Dashboard

Startup Validation ──> Graceful Degradation Reporting
       |
       v
  One-Command Setup Check (scripts/check_setup.py)
```

**Critical path:** Run History Table is the foundation for volume trends, anomaly detection, and meaningful history display. Build it first.

## MVP Recommendation

### Phase 1: Foundation (must ship together)

Prioritize these -- they form the minimum viable health dashboard:

1. **Run History Table** -- persistent `collector_runs` storage replaces in-memory `_last_results`. Everything else depends on this.
2. **Retry Logic** -- stops transient failures from marking sources as degraded. Direct user pain point.
3. **Error Categorization** -- makes errors actionable ("auth expired" vs "will retry").
4. **Scheduler Heartbeat** -- detects the silent-death failure mode.
5. **Per-source Freshness Policy** -- replaces hardcoded 24h threshold with per-source expectations.
6. **Frontend Health Dashboard** -- visual page that renders all the above. Without this, the API improvements are invisible.
7. **Startup Health Validation** -- boot log showing what's active, what's skipped.

### Phase 2: Polish & Open-Source Readiness

8. **Volume Trend Sparklines** -- requires run history data to accumulate.
9. **Simple Anomaly Detection** -- requires 7+ days of run history.
10. **Dead Letter Logging** -- nice-to-have after retry logic is solid.
11. **One-Command Setup Validation** -- critical for open-source onboarding.
12. **Graceful Degradation Reporting** -- shows disabled sources with enable instructions.
13. **Source Dependency Health** -- pings external services.

### Defer

- **Historical Freshness Timeline** -- high complexity, low urgency. Requires timeline visualization component and weeks of data.

## Sources

- [Dagster Asset Health Monitoring Docs](https://docs.dagster.io/examples/best-practices/asset-health-monitoring) -- freshness policies, health status concepts
- [Dagster Freshness Policies Docs](https://docs.dagster.io/guides/observe/asset-freshness-policies) -- time-window and cron-based freshness
- [Dagster Data Observability Guide](https://dagster.io/guides/data-observability-in-2025-pillars-pros-cons-best-practices) -- 5 pillars of data observability
- [Airflow UI Documentation](https://airflow.apache.org/docs/apache-airflow/stable/ui.html) -- Grid View, Gantt chart, task status
- [Monte Carlo Data Pipeline Monitoring](https://www.montecarlodata.com/blog-data-pipeline-monitoring/) -- 5 pillars: freshness, quality, volume, schema, lineage
- [ZenML Orchestration Comparison](https://www.zenml.io/blog/orchestration-showdown-dagster-vs-prefect-vs-airflow) -- feature comparison across orchestrators
- [RudderStack Pipeline Monitoring Best Practices](https://www.rudderstack.com/blog/data-pipeline-monitoring/) -- core metrics and monitoring strategies
- [Integrate.io Pipeline Monitoring Tools](https://www.integrate.io/blog/data-pipeline-monitoring-tools/) -- dashboard features overview
- [Dagster+ New UI Announcement](https://dagster.io/blog/introducing-the-new-dagster-plus-ui) -- dashboard, metrics, freshness pass rate
