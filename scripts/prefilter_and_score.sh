#!/bin/bash
# Pre-filter + LLM score pipeline
# Run every 4-6 hours via cron
set -e

cd ~/work/trading-co/park-intel
source .venv/bin/activate

echo "=== Step 1: Pre-filter ==="
python3 scripts/prefilter.py --hours 12

echo "=== Step 2: LLM Score (prefiltered only) ==="
python3 scripts/run_llm_tagger.py --prefiltered --batch-size 10

echo "=== Done ==="
