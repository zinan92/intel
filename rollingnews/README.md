# Rolling News public surface

This directory contains the real-time News Triage Desk served at
`https://news.park-ai-intel.com/`. It is a static read-only surface over the
Park Intel realtime lane; it is not a fixture or a second data store.

## Runtime contract

- Static page: local loopback service on `127.0.0.1:8787`.
- Data: `GET /api/ui/realtime?window=24h&limit=120` from the existing Park Intel
  API on `127.0.0.1:8001`.
- Public routing: the dedicated Cloudflare tunnel sends only
  `/api/ui/realtime` to port 8001 and all other requests to port 8787.
- The page uses a same-origin `/api` base in production. `NEWS_API_BASE` is
  available only as an explicit local-development override.

The page displays the persisted rolling feed, High Impact, Watch, Noise,
Unknown, pending/failed operational counts, and source health. It does not
write triage decisions, execute trades, expose the SQLite database, or expose
the rest of the private Park Intel API.
