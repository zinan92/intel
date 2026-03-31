# Phase 3: Persistent Run & Open-Source - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Make park-intel run persistently via launchd (auto-restart on crash), and package for open-source release: .env.example, zero-config core sources, graceful degradation for optional sources, CORS hardening, hardcoded path audit, and README rewrite.

</domain>

<decisions>
## Implementation Decisions

### launchd service
- **D-01:** User-level LaunchAgent plist (~/Library/LaunchAgents/), not system-level LaunchDaemon
- **D-02:** KeepAlive = true for auto-restart on crash
- **D-03:** Wrapper script (scripts/park-intel-service.sh) activates .venv and runs uvicorn without --reload
- **D-04:** StandardOutPath and StandardErrorPath point to logs/ directory
- **D-05:** WorkingDirectory set to project root (absolute path resolved at install time)
- **D-06:** Management scripts: scripts/install-service.sh, scripts/uninstall-service.sh, scripts/service-status.sh

### Production server config
- **D-07:** Remove `reload=True` from main.py uvicorn.run() — use env var PARK_INTEL_DEV=1 to enable reload in dev
- **D-08:** CORS restricted to localhost origins by default, configurable via CORS_ORIGINS env var

### Open-source packaging
- **D-09:** Create .env.example with all env vars documented (ANTHROPIC_API_KEY, XUEQIU_COOKIE, GITHUB_TOKEN — all marked optional)
- **D-10:** Core sources (RSS, HackerNews, Reddit) verified to work without any tokens — no code changes needed, already functional
- **D-11:** Optional sources (Xueqiu, GitHub releases, social_kol) skip gracefully with clear log — verify existing behavior, add missing log messages if needed
- **D-12:** Audit codebase for hardcoded absolute paths — grep found none in Python files, verify frontend too
- **D-13:** Keep requirements.txt (not pyproject.toml — deferred to v2 per Codex review)

### README
- **D-14:** Rewrite for open-source audience: quick start (3 commands), architecture overview, source configuration guide, contributing section
- **D-15:** Include the /health dashboard screenshot
- **D-16:** Document launchd setup as optional "Run as background service" section

### Claude's Discretion
- Exact plist XML structure
- Wrapper script error handling
- README structure and wording
- How to test install/uninstall scripts

</decisions>

<specifics>
## Specific Ideas

- Pitfalls research warned: launchd silently fails without absolute paths, test with `launchctl kickstart` not `load`
- Pitfalls research warned: clone-to-run failure is #1 open-source adoption killer
- Current state: main.py has `reload=True` hardcoded and CORS `allow_origins=["*"]`
- Current state: .env has only ANTHROPIC_API_KEY and XUEQIU_COOKIE (no GITHUB_TOKEN documented)
- No hardcoded /Users/ paths found in Python code — good baseline

</specifics>

<canonical_refs>
## Canonical References

### Research
- `.planning/research/PITFALLS.md` — launchd permission issues, clone-to-run failures, hardcoded paths
- `.planning/research/STACK.md` — launchd LaunchAgent pattern, wrapper script approach

### Existing code
- `main.py` line 65 — CORS `allow_origins=["*"]` to fix
- `main.py` line 78 — `reload=True` to make conditional
- `requirements.txt` — Current dependency file (keep as-is)
- `README.md` — Current README to rewrite
- `.env` — Current env file (basis for .env.example)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/run_collectors.py` — Existing script pattern for management scripts
- `config.py` — Environment variable loading pattern (python-dotenv)

### Established Patterns
- All config loaded via python-dotenv from .env
- Scripts in scripts/ directory
- Logs in logs/ directory with rotation

### Integration Points
- `main.py` — uvicorn.run() config and CORS middleware
- `~/Library/LaunchAgents/` — launchd plist destination
- `.gitignore` — ensure .env excluded, .env.example included

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-persistent-run-open-source*
*Context gathered: 2026-03-31*
