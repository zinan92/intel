#!/usr/bin/env bash
set -euo pipefail

PLIST_DST="$HOME/Library/LaunchAgents/com.wendy.park-intel-weekly-finance-newsletter.plist"
launchctl bootout "gui/$(id -u)" "$PLIST_DST" 2>/dev/null || true
rm -f "$PLIST_DST"
echo "uninstalled com.wendy.park-intel-weekly-finance-newsletter"
