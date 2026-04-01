#!/bin/bash
set -euo pipefail

# Navigate to project root (one level up from scripts/)
cd "$(dirname "$0")/.."

# Kill any orphan process holding the port before starting
ORPHAN_PID=$(lsof -ti:8001 2>/dev/null || true)
if [ -n "$ORPHAN_PID" ]; then
    echo "Port 8001 occupied by PID $ORPHAN_PID — killing orphan"
    kill -9 $ORPHAN_PID 2>/dev/null || true
    sleep 1
fi

# Activate virtual environment
source .venv/bin/activate

# Start uvicorn in production mode (no reload)
exec python -m uvicorn main:app --host 127.0.0.1 --port 8001
