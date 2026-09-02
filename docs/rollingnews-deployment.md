# Rolling News deployment

Issue: [#84](https://github.com/zinan92/intel/issues/84)

## Architecture

The production page is the tracked file at `rollingnews/index.html`. A
KeepAlive launchd job serves that directory on `127.0.0.1:8787` using
`scripts/rollingnews-static-service.sh`. The existing `com.park-intel.agent`
job remains the sole owner of the realtime FastAPI/SQLite service on port
8001.

The public hostname is `news.park-ai-intel.com`. Its dedicated Cloudflare
tunnel has two ingress rules:

```yaml
ingress:
  - hostname: news.park-ai-intel.com
    path: ^/api/ui/realtime$
    service: http://127.0.0.1:8001
  - hostname: news.park-ai-intel.com
    service: http://127.0.0.1:8787
  - service: http_status:404
```

Only the realtime read-model route is proxied to the API. Mutating API routes,
admin routes, raw database files, logs, and environment files are not routed
through the public tunnel. Existing `desk`, `goldbot`, `research`, and other
tunnels are independent and remain unchanged.

## Install or repair the local page service

```bash
./scripts/install-rollingnews-static-service.sh
curl -fsS http://127.0.0.1:8787/ | grep -F 'NEWS TRIAGE DESK — ROLLING NEWS'
```

The launchd template is tracked as
`com.park-intel.rollingnews-static.plist`; the installed copy lives in
`~/Library/LaunchAgents` and contains the absolute checkout path.

## Tunnel configuration

Keep the tunnel credential and config outside Git, for example in
`~/.cloudflared/rollingnews.yml`. Substitute the created tunnel UUID in the
template below:

```yaml
tunnel: <ROLLINGNEWS_TUNNEL_UUID>
credentials-file: /Users/wendy/.cloudflared/<ROLLINGNEWS_TUNNEL_UUID>.json
ingress:
  - hostname: news.park-ai-intel.com
    path: ^/api/ui/realtime$
    service: http://127.0.0.1:8001
  - hostname: news.park-ai-intel.com
    service: http://127.0.0.1:8787
  - service: http_status:404
```

Run the tunnel under the tracked KeepAlive launchd label
`com.park-intel.rollingnews-tunnel`:

```bash
./scripts/install-rollingnews-tunnel-service.sh
```

Verify both loopback services before reloading it. The Mac must be online for
the self-hosted public surface to be available.

## Verification

```bash
curl -fsS https://news.park-ai-intel.com/ | grep -F 'NEWS TRIAGE DESK — ROLLING NEWS'
curl -fsS 'https://news.park-ai-intel.com/api/ui/realtime?window=24h&limit=3'
```

The JSON response must contain real `items`, `source_health`, `operational`,
and `stats` fields. A page that renders without this response is not a valid
deployment.
