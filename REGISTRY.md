# Runtime Registry

## 现在在哪里

- Automated article scoring, event narratives, and narrative-signal briefs use the DeepSeek Chat Completions API.
- The Daily Finance Newsletter archive and delivery contract is now available on `main`; Weekly Finance production is staged behind issues #12-#16.
- Runtime credentials are read from `/Users/wendy/park-hands/_secrets/deepseek-key`; no Claude Code CLI subprocess is used by park-intel.
- The macOS services are managed by `com.park-intel.agent`, `com.park-intel.api`, and `com.wendy.park-intel-finance-newsletter`.

## 下一步

- Keep interactive Claude Desktop and operator-started Claude Code sessions separate from background service accounting.
- Implement #12 next: generate the Weekly retrospective dry-run from seven Daily archives before adding live calendar sources.
