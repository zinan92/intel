# Weekly Finance Production Verification

Date: 2026-08-23

## Verified

- Runtime checkout: `/Users/wendy/work/trading-co/park-intel-runtime`, pinned from the merged `main` line.
- LaunchAgent: `com.wendy.park-intel-weekly-finance-newsletter`.
- Schedule: Sunday and Monday catch-up at 08:30 Asia/Shanghai.
- Published week: `2026-08-23`.
- Obsidian artifact: `/Users/wendy/park-io/008_finance weekly newsletter/2026-08-23-finance-weekly-newsletter.md`.
- Delivery manifest: `/Users/wendy/park-io/008_finance weekly newsletter/.delivery-manifests/2026-08-23.json`.
- Feishu: `feishu_sent=true`.
- Public latest route: https://park-ai-intel.com/finance-weekly-newsletter (HTTP 200).
- Public archive route: https://park-ai-intel.com/finance-weekly-newsletter/archive.html (HTTP 200).
- Re-running the same week returned `weekly_delivery: noop`; manifest remained at one published revision and no second Feishu send occurred.

## Source State at Publication

- `nasdaq:earnings=ok`
- `nasdaq:macro=error`
- `official:bea=ok`
- `official:federal_reserve=no_data`

The report disclosed these states in its Source Status. It did not treat the failed Nasdaq macro source or unavailable Federal Reserve page as successful coverage.

## Validation

- Full test suite: 422 passed, 402 warnings.
- Gitleaks: passed.
- Plist lint: passed.
- Scheduler tests: passed.
- Website latest and archive route checks: passed.
