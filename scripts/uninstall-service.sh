#!/bin/bash
set -euo pipefail

SERVICE_LABEL="com.park-intel.agent"
PLIST_DST="${HOME}/Library/LaunchAgents/com.park-intel.agent.plist"

echo "Uninstalling park-intel service..."

# Stop and unload the service (ignore error if not loaded)
launchctl bootout "gui/$(id -u)/${SERVICE_LABEL}" 2>/dev/null || true

# Remove the plist
if [ -f "${PLIST_DST}" ]; then
    rm "${PLIST_DST}"
    echo "Removed ${PLIST_DST}"
else
    echo "Plist not found at ${PLIST_DST} (already removed?)"
fi

echo "park-intel service uninstalled."
