#!/bin/bash
set -euo pipefail

# Navigate to project root (one level up from scripts/)
cd "$(dirname "$0")/.."

# Activate virtual environment
source .venv/bin/activate

# Start uvicorn in production mode (no reload)
exec python -m uvicorn main:app --host 127.0.0.1 --port 8001
