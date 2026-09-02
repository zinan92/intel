# Runtime Registry

## 2026-09-02 · Unknown moved outside the decision buckets

- Issue #73 keeps Unknown as an explicit operational truth state but removes
  it from the visually weighted High Impact / Watch / Noise decision surface.
- `/api/ui/realtime.operational` reports full-window completed Unknown count,
  rate and a `>=10%` alert, plus pending and failed counts separately.
- A shared cross-source event matcher drives both display deduplication and a
  five-minute Unknown revisit. Later related evidence requeues an Unknown once,
  supplies bounded supplemental context to AI, and cannot create retry loops.

## 2026-09-02 · Watch decisions require explicit asset exposure

- Issue #81 requires every Watch result to name at least one affected asset or
  asset class. If no defensible exposure exists, the result must be repaired,
  isolated as Unknown/failed, or classified Noise rather than accepted empty.
- Unclear Watch assets use `impact=unclear` plus concrete watch conditions;
  directional Watch assets require per-asset up/down impact.

## 2026-09-02 · Scheduled High Impact keeps magnitude separate from direction

- Issue #79 permits `unclear` only for explicit pre-release/scheduled High
  Impact catalysts, and only when affected assets plus concrete watch
  conditions are present. Scheduled assets use `impact=unclear` honestly.
- Released/observed High Impact events still require bullish/bearish direction
  and per-asset up/down impact. `mixed` remains forbidden everywhere.

## 2026-09-02 · High Impact floor narrowed to actual policy events

- Issue #77 keeps FOMC, rate decisions, emergency hikes/cuts, CPI/PCE/NFP and
  equivalent Chinese releases on the deterministic High Impact floor.
- Generic central-bank names, official meetings and non-directional comments
  are no longer force-upgraded. This prevents the validator from demanding a
  fabricated bullish/bearish call for news that contains no policy action.

## 2026-09-02 · Realtime decision buckets collapse duplicate source reports

- Issue #72 keeps `/api/ui/realtime.items` as the immutable raw Article stream
  while grouping cross-source near-duplicate headlines into one bucket card
  inside a 45-minute evidence window.
- Each displayed event retains source, Article ID, link, timestamp, primary
  Article and deterministic read-model IDs. Same-source updates, distinct
  headlines and matching headlines outside the window remain separate.
- Bucket counts now represent displayed events; raw-returned count and collapsed
  duplicate count remain explicit. No source evidence is deleted or rewritten.

## 2026-09-02 · Realtime AI decision contract hardened

- Issue #71 removes the two-sided bull/bear scenario fields from the active
  model and API contract. Historical database columns remain only for
  non-destructive compatibility; new triage explicitly clears them.
- `mixed` is no longer accepted. High Impact requires a bullish/bearish call,
  non-empty affected assets, and per-asset up/down impact; unclear Watch items
  require concrete confirmation conditions.
- Source-extracted tickers are supplied to the model. Invalid output receives
  one bounded repair attempt, then only that Article becomes failed/Unknown for
  retry instead of poisoning the whole batch or being mislabeled Noise.

## 2026-09-02 · Core APIs exclude realtime backfill from current activity

- Issue #70 fixes the remaining read-path leak in `api/routes.py`: imported
  historical SEC filings no longer inflate health, latest, search, source
  freshness, or 24-hour activity.
- `/api/articles/sources` still preserves the full historical total and now
  reports `backfill_count` explicitly; no filing is deleted or re-dated.
- The regression fixture reproduces the production shape exactly: 3 current
  filings plus 2,935 same-day-collected backfill rows report current activity
  as 3 while retaining an archive total of 2,938.

## 2026-09-02 · BlockBeats official Pro API integration, live gate open

- Issue #64 adds the official BlockBeats `/v1/newsflash` source at a 300-second
  free-tier baseline cadence. It preserves the BlockBeats permalink and any distinct
  upstream URL/attribution, strips provider HTML, and accepts both documented
  date-time strings and legacy Unix timestamps.
- Missing/invalid credentials, rate limits, malformed payloads and provider
  status failures remain visible; they are never converted into an empty
  success. Replay is deduplicated through provider ID/GUID or a stable hash.
- BlockBeats is treated as secondary evidence: items enter `needs_review`, are
  unconfirmed, and cannot independently qualify for pinning. AI impact remains
  a separate classification, so a genuinely major event may still be High
  Impact while awaiting primary-source confirmation.
- The free account was created with 10,000 monthly calls and its key is stored
  outside the repository. A sanitized live receipt returned 50 valid rows,
  persisted and AI-triaged a 10-item sample, exposed 10 UI items with healthy
  source status, then proved replay deduplication (`saved=0`, `duplicates=10`).
  The production deployment uses the 300-second baseline after merge.

## 2026-09-02 · Telegram ingestion permanently retired

- Issue #63 removes the Telegram MTProto collector, adapter, bootstrap entry,
  activation path, live-smoke path, dependency, and credential instructions.
- Existing source-registry rows and collected Articles are preserved for audit
  and retrospective research, but startup migration marks the legacy source
  inactive and retired so it cannot be scheduled accidentally.
- This supersedes the earlier Issue #54 implementation. Under Telegram's
  current [API Terms](https://core.telegram.org/api/terms) and
  [Content Licensing Terms](https://telegram.org/tos/content-licensing), the
  proposed third-party-channel AI triage path is not eligible without explicit
  channel-owner permission. Credential acquisition is therefore not a blocker
  to retry; the source is disqualified from the product path. The dated
  decision record is
  [`docs/telegram-ai-terms-decision-2026-09-02.md`](docs/telegram-ai-terms-decision-2026-09-02.md).

## 2026-09-02 · SEC historical filings retained as reversible backfill

- Issue #61 adds `is_backfill` plus a traceable reason. SEC filings outside
  the configured 72-hour realtime window remain stored for retrospective
  research but are excluded from scheduled realtime AI triage.
- `/api/ui/realtime` hides backfill by default and exposes it only when
  `include_backfill=true` is explicitly requested. No SEC Article is deleted.
- The one-time marker command is dry-run by default and can undo only rows
  carrying the exact supplied reason, preserving completed historical triage.

## 2026-09-02 · Telegram MTProto source implemented, human gate open (superseded)

- Issue #54 adds an MTProto user-session source for exactly seven approved
  Telegram channels. Setup enumerates joined channels by display-name hints,
  requires each hint to resolve exactly once, and persists only the approved
  immutable numeric IDs after an explicit `--approve` step.
- The source reads bounded text-message windows for reconnect/gap recovery,
  records original and edited message versions idempotently, never downloads
  media, and keeps session/API credentials outside the repository.
- Telegram-only evidence always requires independent confirmation before
  pinning. Global News Monitor, Intel Slava, and Solid Intel are forced to
  Watch/needs-review even if the AI model proposes High Impact.
- The source remains inactive until the operator supplies Telegram API
  credentials, completes phone/OTP/2FA authorization, and approves the seven
  numeric channel IDs. Issue #54 remains open until a real approved-channel
  provider-to-persistence-to-API receipt succeeds.
- The statements above record the historical implementation state only and are
  superseded by the permanent-retirement decision at the top of this file.

## 2026-09-02 · SEC EDGAR realtime watchlist code integrated, live gate open

- Issue #53 adds the official SEC EDGAR adapter for the approved 20-company
  watchlist and five filing forms, with an explicit SEC User-Agent gate,
  sub-10-request/second throttling, official ticker-to-CIK verification,
  pinned CIK drift detection, accession-id deduplication, and metadata-only
  smoke receipts.
- Source authority, corroboration state, and pin eligibility are persisted and
  exposed independently from AI impact classification. An official filing can
  satisfy trusted-source evidence but does not force High Impact or pinning.
- Issue #57 adds the idempotent upgrade path for SEC rows created before CIK
  pinning: it fills only a missing map and preserves operator ticker, form,
  activation, schedule, and any existing non-empty pin edits.
- Issue #59 makes the realtime UI health read model fall back to the latest
  persisted collector run, so a provider failure remains visible after restart
  or an out-of-process smoke run instead of regressing to `no_data`.
- The code and full local suite pass, but this host currently receives HTTP 403
  from the official SEC JSON and archive hosts. The adapter reports that as a
  provider block rather than empty success. Issue #53 remains open until a real
  provider-to-persistence-to-API receipt succeeds.

## 2026-09-01 · Realtime polling cursor fixed

- PR #49 fixes CLS Telegraph and Eastmoney realtime polling: each poll reads
  the provider's latest window and relies on local source-id deduplication;
  backwards-pagination cursors are no longer persisted by the scheduler.
- Live smoke after restart reached current provider timestamps and saved new
  rows from both sources. A clean throughput measurement window is running;
  its eventual overnight total must not be recorded until the window ends.

## 2026-09-01 · Realtime News Lane implemented and reviewed

- PRs #37, #38, and #39 add CLS Telegraph, Eastmoney 7x24, lane provenance,
  second-level scheduling, and a sanitized dual-run receipt; #40–#42 close
  the Sonnet review, two-axis review, and final scheduler delivery gaps.
- The post-review fix keeps the trial explicit: `REALTIME_LANE_ENABLED=1` is
  required, provider blocks pause only that source type, and realtime items do
  not enter the existing hourly digest, LLM tagging, event aggregation, or
  trading-signal inputs before convergence.
- `python scripts/measure_dual_run.py --hours 1 --live-smoke` reports persisted
  lane metrics plus read-only provider smoke status. It never enables
  `canonical_realtime`; the current convergence state remains `not_ready`.
- On an existing database, the explicit activation path is
  `REALTIME_LANE_ENABLED=1 python scripts/activate_realtime_lane.py`; the
  normal service stays disabled until that operator action is taken.

## 2026-09-01 · Realtime AI triage connected to the prototype

- PR #46 adds persisted AI triage for realtime News Items and
  `/api/ui/realtime`; the local News Triage Desk now reads real CLS/Eastmoney
  items and renders High Impact, Watch, Noise, and explicit Unknown states.
- DeepSeek remains the first provider. When it returns quota/transport failure,
  the existing isolated Codex CLI fallback is used; if both fail, the item is
  retained as `unknown` with an error state.
- The live page is served locally at
  `http://127.0.0.1:8777/research-newsliquid/prototype-news-triage-v1-simple.html`.
  K-line, broker, order execution, and canonical-lane convergence remain out
  of scope.

## 2026-08-31 · DeepSeek → Codex CLI fallback restored scheduled newsletters

- DeepSeek returned HTTP 402 from 2026-08-26 through 2026-08-31. Finance
  Daily previously stopped before delivery, and Finance Weekly stopped because
  its required Daily archive coverage fell to 2/7.
- Issue #25 / PR #27 introduced the fallback. Issue #31 supersedes the
  quota-only restriction from #26: every DeepSeek synthesis failure now passes
  the same frozen prompt to an isolated, read-only, ephemeral Codex CLI
  process. No tools, browser, apps, unified execution, or live search are
  enabled; only a subsequent Codex failure remains fail-closed.
- Real acceptance on 2026-08-31: DeepSeek `http_402` → Codex CLI success;
  Finance Daily Brief #275 passed the existing quality gate, was archived to
  `/Users/wendy/park-io/007_finance daily newsletter/2026-08-31-finance-daily-newsletter.md`,
  and was sent to Feishu (`feishu_sent=True`).
- Issue #29 recovered the five missing Daily archives for 2026-08-26 through
  2026-08-30 from their frozen historical windows. Each is an `archived`
  Codex-generated record, was written to Obsidian, and was not sent to Feishu;
  the current Daily Brief remained published.
- The recovered 2026-08-30 Weekly Finance Newsletter passed its 7/7 coverage
  gate, was archived, and was sent once to Feishu with `provider=codex-cli`.
  A post-publication scheduled no-op returned successfully, proving the
  manifest prevents a duplicate send.

## 现在在哪里

- Automated article scoring, event narratives, and narrative-signal briefs use the DeepSeek Chat Completions API.
- The realtime lane polls CLS Telegraph and Eastmoney 7x24 from the latest
  provider windows every 60 seconds, persists unique News Items, and exposes
  them through the local News Triage Desk; its throughput measurement remains
  provisional until a clean observation window completes.
- The BlockBeats official Pro API source is implemented at 300-second baseline
  cadence; temporary 60-second event windows are isolated in issue #68.
- The SEC EDGAR watchlist source is implemented behind the same realtime opt-in
  but is not live-verified on this host while the official endpoints return 403.
- Telegram ingestion is permanently retired; historical registry rows and
  Articles remain stored, while no collector or scheduler path can activate it.
- The Daily Finance Newsletter archive and delivery contract is available on `main`.
- Weekly retrospective, calendar verification, Obsidian/Feishu publication, delivery manifests, same-week no-op, and explicit force-resend are available on `main`.
- Finance Daily, Finance Weekly, and the upstream Park Intel service now run from the clean production checkout `/Users/wendy/work/trading-co/park-intel-production`, created from `origin/main`.
- Daily runs at 08:00 Asia/Shanghai; Weekly runs Sunday 08:30 with Monday catch-up; the upstream service is KeepAlive-managed.
- The cutover evidence, local-state boundaries, and rollback files are recorded in `docs/finance-newsletter-production-runtime-2026-08-24.md`.
- Runtime credentials are read from `/Users/wendy/park-hands/_secrets/deepseek-key`; Codex CLI fallback uses local subscription authentication and no API key is written to logs or content.
- The relevant macOS services are `com.park-intel.agent`, `com.wendy.park-intel-finance-newsletter`, and `com.wendy.park-intel-weekly-finance-newsletter`. Website refresh jobs remain owned by the separate `zinan92/park-ai-intel` repository.
- Weekly publication sends to Feishu by default. A failed or incomplete Weekly
  run does not send, and a previously published week returns no-op rather than
  sending a duplicate.

## 下一步

- Decide the long-term Unknown presentation under issue #73 and measure the
  24-hour BlockBeats increment/overlap under issue #65.
- Measure BlockBeats versus CLS/Eastmoney/SEC over a clean 24-hour window under
  issue #65, then decide which incremental event categories justify retention.
- Add quota-aware temporary 60-second BlockBeats event windows under issue #68
  without changing the 300-second free-tier baseline.
- Complete an uninterrupted clean observation window for realtime unique
  article throughput, then decide whether the lane is ready for broader source
  coverage or canonical-lane convergence.
- Keep interactive Claude Desktop and operator-started Claude Code sessions separate from background service accounting.
- Monitor source-health states and the first post-cutover scheduled Daily/Weekly cycles; detailed cutover evidence is recorded in `docs/finance-newsletter-production-runtime-2026-08-24.md`.
