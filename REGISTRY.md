# Runtime Registry

## 2026-08-31 · DeepSeek → Codex CLI fallback restored scheduled newsletters

- DeepSeek returned HTTP 402 from 2026-08-26 through 2026-08-31. Finance
  Daily previously stopped before delivery, and Finance Weekly stopped because
  its required Daily archive coverage fell to 2/7.
- Issue #25 / PR #27 introduced the fallback; Issue #26 narrows its trigger
  to explicit DeepSeek quota exhaustion (`http_402`). The same frozen prompt
  is passed to an isolated, read-only, ephemeral Codex CLI process; no tools,
  browser, apps, unified execution or live search are enabled. Other DeepSeek
  failures remain fail-closed.
- Real acceptance on 2026-08-31: DeepSeek `http_402` → Codex CLI success;
  Finance Daily Brief #275 passed the existing quality gate, was archived to
  `/Users/wendy/park-io/007_finance daily newsletter/2026-08-31-finance-daily-newsletter.md`,
  and was sent to Feishu (`feishu_sent=True`).
- Finance Weekly remains fail-closed until its Daily archive window reaches
  the existing 7/7 coverage contract; it was not fabricated from the 2/7
  window. The next complete weekly window will use the same quota-only
  fallback seam for synthesis and repair.

## 现在在哪里

- Automated article scoring, event narratives, and narrative-signal briefs use the DeepSeek Chat Completions API.
- The Daily Finance Newsletter archive and delivery contract is available on `main`.
- Weekly retrospective, calendar verification, Obsidian/Feishu publication, delivery manifests, same-week no-op, and explicit force-resend are available on `main`.
- Finance Daily, Finance Weekly, and the upstream Park Intel service now run from the clean production checkout `/Users/wendy/work/trading-co/park-intel-production`, created from `origin/main`.
- Daily runs at 08:00 Asia/Shanghai; Weekly runs Sunday 08:30 with Monday catch-up; the upstream service is KeepAlive-managed.
- The cutover evidence, local-state boundaries, and rollback files are recorded in `docs/finance-newsletter-production-runtime-2026-08-24.md`.
- Runtime credentials are read from `/Users/wendy/park-hands/_secrets/deepseek-key`; Codex CLI fallback uses local subscription authentication and no API key is written to logs or content.
- The relevant macOS services are `com.park-intel.agent`, `com.wendy.park-intel-finance-newsletter`, and `com.wendy.park-intel-weekly-finance-newsletter`. Website refresh jobs remain owned by the separate `zinan92/park-ai-intel` repository.

## 下一步

- Keep interactive Claude Desktop and operator-started Claude Code sessions separate from background service accounting.
- Monitor source-health states and the first post-cutover scheduled Daily/Weekly cycles; detailed cutover evidence is recorded in `docs/finance-newsletter-production-runtime-2026-08-24.md`.
