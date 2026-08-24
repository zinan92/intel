# Finance Newsletter Production Runtime

Date: 2026-08-24
Issue: #23
Repository: `zinan92/intel`

## Canonical Runtime

The production checkout for Finance Daily, Finance Weekly, and the upstream
Park Intel service is:

`/Users/wendy/work/trading-co/park-intel-production`

At cutover, the checkout was created from `origin/main` at:

`957df54441d7da62e57b189341876c266e71c939`

The tracked tree matched `origin/main`. Local-only runtime files are kept
outside Git history:

- `.env`: copied locally with mode `0600`; never committed.
- `.venv`: local symlink to the validated existing Python environment.
- `data/park_intel.db`: SQLite backup of the active database; never committed.
- `logs/`: local launchd logs; never committed.

The existing development checkout at
`/Users/wendy/work/trading-co/park-intel` was preserved unchanged. Its local
modifications were not committed or deleted.

## Launchd Ownership

| Label | Schedule | Production entrypoint |
| --- | --- | --- |
| `com.park-intel.agent` | KeepAlive | `scripts/park-intel-service.sh` |
| `com.wendy.park-intel-finance-newsletter` | Daily 08:00 Asia/Shanghai | `scripts/publish_finance_daily_newsletter.py` |
| `com.wendy.park-intel-weekly-finance-newsletter` | Sunday/Monday 08:30 Asia/Shanghai | `scripts/run_scheduled_weekly_finance_newsletter.py` |

The installed LaunchAgents point all three labels at the canonical runtime.
The website refresh jobs remain in the separate `zinan92/park-ai-intel`
repository and are not part of the Intel generation runtime.

## Verification Evidence

- `com.park-intel.agent`: running from the canonical runtime; `/api/health`
  returned HTTP 200 with `scheduler=running`.
- Finance Daily controlled delivery: read brief `#273`, wrote
  `/Users/wendy/park-io/007_finance daily newsletter/2026-08-24-finance-daily-newsletter.md`,
  and skipped Feishu with `PARK_INTEL_SKIP_FEISHU=1`.
- Finance Weekly controlled dry-run: returned `weekly_delivery: dry_run`,
  wrote no archive/manifest publication, and sent no Feishu message.
- The normal Weekly dry-run refused a changed published content hash unless
  `--force-resend` was explicit; this confirms the idempotency guard remained
  active.
- Focused publisher tests: `10 passed`.

## Rollback

Pre-cutover LaunchAgent files were preserved as
`*.plist.bak-20260824-production-cutover` in
`/Users/wendy/Library/LaunchAgents/`. The old development checkout and its
database were left in place.
