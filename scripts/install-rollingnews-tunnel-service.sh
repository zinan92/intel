#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.park-intel.rollingnews-tunnel"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/$LABEL.plist"

test -r "$HOME/.cloudflared/rollingnews.yml"
test -r "$HOME/.cloudflared/48d96989-7cbb-45bd-83db-fcfeacdd2b05.json"
mkdir -p "$PLIST_DIR"
sed "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
  "$PROJECT_DIR/$LABEL.plist" > "$PLIST_PATH"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
launchctl enable "gui/$(id -u)/$LABEL"
echo "Installed $LABEL from $PLIST_PATH"
