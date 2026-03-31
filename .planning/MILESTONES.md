# Milestones

## v1.0 Reliability & Open-Source (Shipped: 2026-03-31)

**Phases completed:** 3 phases, 6 plans, 13 tasks

**Key accomplishments:**

- ErrorCategory 4-way enum, categorize_error/is_retryable functions, CollectorResult dataclass, and CollectorRun persistent model with idempotent migration
- Tenacity retry on collect_from_source with 3-attempt exponential backoff, CollectorRun DB persistence for every collection attempt, and weekly 30-day cleanup job
- Per-source health endpoints with freshness policy, volume anomaly detection, scheduler heartbeat, and disabled source reasoning
- Color-coded /health page with source cards showing freshness, volume anomaly flags, disabled instructions, health banner, and 60-second auto-refresh via TanStack Query
- launchd LaunchAgent with KeepAlive auto-restart, CORS hardened to localhost defaults, and conditional dev reload
- Documented env template (.env.example), verified zero-config core sources, added graceful degradation for optional collectors, and rewrote README for open-source audience

---
