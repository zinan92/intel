#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$PROJECT_DIR/.venv/bin/python}"
PLIST_LABEL="com.wendy.park-intel-weekly-finance-newsletter"
PLIST_SRC="$PROJECT_DIR/$PLIST_LABEL.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"

test -x "$PYTHON" || { echo "missing Python runtime: $PYTHON" >&2; exit 1; }
mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/logs"
sed -e "s|__PYTHON__|$PYTHON|g" -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" -e "s|__HOME__|$HOME|g" "$PLIST_SRC" > "$PLIST_DST"
plutil -lint "$PLIST_DST"
launchctl bootout "gui/$(id -u)" "$PLIST_DST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
echo "installed $PLIST_LABEL for Sunday and Monday 08:30 Asia/Shanghai"
