# Runtime Registry

## 2026-09-01 · Realtime News Lane implemented and reviewed

- PRs #37, #38, and #39 add CLS Telegraph, Eastmoney 7x24, lane provenance,
  second-level scheduling, and a sanitized dual-run receipt.
- The post-review fix keeps the trial explicit: `REALTIME_LANE_ENABLED=1` is
  required, provider blocks pause only that source type, and realtime items do
  not enter the existing hourly digest, LLM tagging, event aggregation, or
  trading-signal inputs before convergence.
- `python scripts/measure_dual_run.py --hours 1 --live-smoke` reports persisted
  lane metrics plus read-only provider smoke status. It never enables
  `canonical_realtime`; the current convergence state remains `not_ready`.

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

- Keep interactive Claude Desktop and operator-started Claude Code sessions separate from background service accounting.
- Monitor source-health states and the first post-cutover scheduled Daily/Weekly cycles; detailed cutover evidence is recorded in `docs/finance-newsletter-production-runtime-2026-08-24.md`.
