#!/bin/bash
set -euo pipefail

SERVICE_LABEL="com.park-intel.agent"

echo "=== park-intel service status ==="
echo ""

if launchctl print "gui/$(id -u)/${SERVICE_LABEL}" 2>/dev/null; then
    echo ""
    echo "Service is installed and loaded."
else
    echo "Service not installed or not loaded."
    echo "Install with: scripts/install-service.sh"
fi
