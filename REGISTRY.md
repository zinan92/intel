# Runtime Registry

## 2026-09-02 · SEC historical filings retained as reversible backfill

- Issue #61 adds `is_backfill` plus a traceable reason. SEC filings outside
  the configured 72-hour realtime window remain stored for retrospective
  research but are excluded from scheduled realtime AI triage.
- `/api/ui/realtime` hides backfill by default and exposes it only when
  `include_backfill=true` is explicitly requested. No SEC Article is deleted.
- The one-time marker command is dry-run by default and can undo only rows
  carrying the exact supplied reason, preserving completed historical triage.

## 2026-09-02 · Telegram MTProto source implemented, human gate open

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
- The SEC EDGAR watchlist source is implemented behind the same realtime opt-in
  but is not live-verified on this host while the official endpoints return 403.
- The Telegram MTProto source is implemented but inactive until its explicit
  human credential/session/channel-ID gate is completed.
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

- Obtain a successful official SEC live receipt without bypassing fair-access
  controls, then close issue #53.
- Complete Telegram API/session authorization and approve the exact seven
  numeric channel IDs, then capture the #54 live receipt.
- Complete an uninterrupted clean observation window for realtime unique
  article throughput, then decide whether the lane is ready for broader source
  coverage or canonical-lane convergence.
- Keep interactive Claude Desktop and operator-started Claude Code sessions separate from background service accounting.
- Monitor source-health states and the first post-cutover scheduled Daily/Weekly cycles; detailed cutover evidence is recorded in `docs/finance-newsletter-production-runtime-2026-08-24.md`.
