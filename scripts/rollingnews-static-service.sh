#!/bin/bash
set -euo pipefail

# Serve only the packaged Rolling News read-only surface.  The Cloudflare
# tunnel routes /api/ui/realtime separately to the existing Park Intel API.
cd "$(dirname "$0")/.."
exec /usr/bin/python3 -m http.server 8787 --bind 127.0.0.1 --directory "$PWD/rollingnews"
