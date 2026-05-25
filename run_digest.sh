#!/usr/bin/env bash
# Intelligence Terminal v2.0 — pipeline runner
# Runs the 16-source pipeline and persists to Supabase.
# Usage: ./run_digest.sh [--ai]
# Cron / launchd: runs every 5 min via the FastAPI server (preferred)
#                 or manually trigger a full run with this script.

set -euo pipefail

PYTHON="/Users/shivamthakur/anaconda3/envs/automation/bin/python"
ROOT="/Users/shivamthakur/Desktop/Automation"
LOG_DIR="$ROOT/logs"
LOG="$LOG_DIR/digest_$(date +%Y-%m-%d).log"
RUN_AI="${1:-}"

mkdir -p "$LOG_DIR"

echo "──────────────────────────────────────────────────────────" >> "$LOG"
echo "$(date '+%Y-%m-%d %H:%M:%S')  Pipeline run started (RUN_AI=${RUN_AI})" >> "$LOG"

"$PYTHON" - <<EOF >> "$LOG" 2>&1
import asyncio, sys
from pathlib import Path

ROOT = Path("$ROOT")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "projects" / "daily_digest"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from sources import ALL_SOURCES
from agents.pipeline import run_pipeline

async def main():
    run_ai = "${RUN_AI}" == "--ai"
    limits = {
        "hackernews":    15,
        "arxiv":         12,
        "reddit":        15,
        "github":        12,
        "rss":           15,
        "stackoverflow": 10,
        "finance":       25,
        "fred":          12,
        "fear_greed":    5,
        "edgar":         20,
        "options":       15,
        "congress":      15,
        "finra":         15,
        "gdelt":         20,
        "stocktwits":    25,
        "coingecko":     20,
    }

    print(f"Running pipeline: {len(ALL_SOURCES)} sources, run_ai={run_ai}")
    result = await run_pipeline(sources=ALL_SOURCES, limits=limits, run_ai=run_ai, store=True)

    meta    = result.get("run_meta", {})
    sent    = result.get("sentiment", {})
    signals = result.get("signal_data", [])
    store   = result.get("store_stats", {})
    fs      = result.get("fetch_stats", {})

    print(f"Items:    {meta.get('total_clean')} clean / {meta.get('total_raw')} raw")
    print(f"Signals:  {len(signals)} (insider={sum(1 for s in signals if s['source']=='edgar')}, options={sum(1 for s in signals if s['source']=='options')}, congress={sum(1 for s in signals if s['source']=='congress')}, finra={sum(1 for s in signals if s['source']=='finra')})")
    print(f"Sentiment: {sent.get('bullish_pct')}% bull / {sent.get('bearish_pct')}% bear")
    print(f"Alerts:   {len(result.get('alerts', []))}")
    print(f"Supabase: {store}")
    print("Source breakdown:")
    for src, stat in sorted(fs.items()):
        ok = "✓" if "ERROR" not in str(stat) else "✗"
        print(f"  {ok} {src:14s}: {stat}")

asyncio.run(main())
EOF

echo "$(date '+%Y-%m-%d %H:%M:%S')  Run complete" >> "$LOG"
