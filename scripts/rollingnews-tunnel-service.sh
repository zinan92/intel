#!/bin/bash
set -euo pipefail

exec /opt/homebrew/bin/cloudflared tunnel \
  --config "$HOME/.cloudflared/rollingnews.yml" \
  run rollingnews
