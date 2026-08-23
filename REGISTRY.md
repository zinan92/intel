# Runtime Registry

## 现在在哪里

- Automated article scoring, event narratives, and narrative-signal briefs use the DeepSeek Chat Completions API.
- The Daily Finance Newsletter archive and delivery contract is now available on `main`; Weekly Finance production is staged behind issues #12-#16.
- The Weekly retrospective dry-run is now available on `main`; calendar discovery, verification, and publication remain staged behind issues #13-#16.
- Weekly calendar/earnings discovery snapshots and BEA/Federal Reserve verification are now available on `main`; publication remains staged behind issues #14-#16.
- Weekly Obsidian/Feishu publication, delivery manifests, same-week no-op, and explicit force-resend are now available on `main`; scheduling and website consumption remain staged behind issues #15-#16 and park-ai-intel#59.
- Runtime credentials are read from `/Users/wendy/park-hands/_secrets/deepseek-key`; no Claude Code CLI subprocess is used by park-intel.
- The macOS services are managed by `com.park-intel.agent`, `com.park-intel.api`, and `com.wendy.park-intel-finance-newsletter`.

## 下一步

- Keep interactive Claude Desktop and operator-started Claude Code sessions separate from background service accounting.
- Implement #15 next: schedule Sunday publication with a Monday catch-up, then complete park-ai-intel#59 in parallel.
