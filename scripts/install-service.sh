#!/bin/bash
set -euo pipefail

# Resolve absolute project directory
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_SRC="${PROJECT_DIR}/com.park-intel.agent.plist"
PLIST_DST="${HOME}/Library/LaunchAgents/com.park-intel.agent.plist"
SERVICE_LABEL="com.park-intel.agent"

echo "Installing park-intel service..."
echo "Project directory: ${PROJECT_DIR}"

# Create logs directory
mkdir -p "${PROJECT_DIR}/logs"

# Check if service is already loaded — unload first
if launchctl print "gui/$(id -u)/${SERVICE_LABEL}" &>/dev/null; then
    echo "Service already loaded, stopping first..."
    launchctl bootout "gui/$(id -u)/${SERVICE_LABEL}" 2>/dev/null || true
fi

# Copy plist and resolve __PROJECT_DIR__ placeholder
sed "s|__PROJECT_DIR__|${PROJECT_DIR}|g" "${PLIST_SRC}" > "${PLIST_DST}"

# Load the service
launchctl bootstrap "gui/$(id -u)" "${PLIST_DST}"

echo ""
echo "park-intel service installed and started."
echo "Check status with: ${PROJECT_DIR}/scripts/service-status.sh"
