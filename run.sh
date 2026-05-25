#!/usr/bin/env bash
# Run any project without needing conda activated.
#
# Usage:
#   ./run.sh daily_digest            # start localhost dashboard
#   ./run.sh notion                  # push to Notion (all sources)
#   ./run.sh notion --summarize      # push with AI summaries
#   ./run.sh notion --sources hn,arxiv --limit 20
#   ./run.sh doc_qa ask "question"

PYTHON="/Users/shivamthakur/anaconda3/envs/automation/bin/python"
ROOT="$(cd "$(dirname "$0")" && pwd)"

# Shortcut: "notion" maps to the daily_digest Notion push script
if [ "$1" = "notion" ]; then
    shift
    exec "$PYTHON" "$ROOT/projects/daily_digest/notion_push.py" "$@"
fi

exec "$PYTHON" "$ROOT/run.py" "$@"
