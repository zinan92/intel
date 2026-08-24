# Runtime Registry

## 现在在哪里

- Automated article scoring, event narratives, and narrative-signal briefs use the DeepSeek Chat Completions API.
- The Daily Finance Newsletter archive and delivery contract is available on `main`.
- Weekly retrospective, calendar verification, Obsidian/Feishu publication, delivery manifests, same-week no-op, and explicit force-resend are available on `main`.
- Finance Daily, Finance Weekly, and the upstream Park Intel service now run from the clean production checkout `/Users/wendy/work/trading-co/park-intel-production`, created from `origin/main`.
- Daily runs at 08:00 Asia/Shanghai; Weekly runs Sunday 08:30 with Monday catch-up; the upstream service is KeepAlive-managed.
- The cutover evidence, local-state boundaries, and rollback files are recorded in `docs/finance-newsletter-production-runtime-2026-08-24.md`.
- Runtime credentials are read from `/Users/wendy/park-hands/_secrets/deepseek-key`; no Claude Code CLI subprocess is used by park-intel.
- The relevant macOS services are `com.park-intel.agent`, `com.wendy.park-intel-finance-newsletter`, and `com.wendy.park-intel-weekly-finance-newsletter`. Website refresh jobs remain owned by the separate `zinan92/park-ai-intel` repository.

## 下一步

- Keep interactive Claude Desktop and operator-started Claude Code sessions separate from background service accounting.
- Monitor source-health states and the first post-cutover scheduled Daily/Weekly cycles; detailed cutover evidence is recorded in `docs/finance-newsletter-production-runtime-2026-08-24.md`.
