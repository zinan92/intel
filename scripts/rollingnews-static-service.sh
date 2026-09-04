#!/bin/bash
set -euo pipefail

# Serve the packaged Rolling News surface and proxy read-only /api/ requests
# to the existing Park Intel API so localhost and the tunnel share one origin.
cd "$(dirname "$0")/.."
exec /usr/bin/python3 "$PWD/scripts/serve_rollingnews.py"
