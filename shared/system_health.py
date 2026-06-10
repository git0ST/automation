"""System health — is the machine that grows your money actually running?

The biggest accuracy threat observed so far wasn't a model defect, it was an
11-day silent collection outage (Mac reboot dropped the cron). Calibration,
weight learning and the paper book all starve without uptime. This module
turns that into a measurable, visible grade.

Works from both runtimes: Supabase-first (cloud app), local artifacts as
fallback (cron machine). All fields None-safe.
"""
from __future__ import annotations
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
    if not (url and key):
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None


def health_snapshot() -> dict:
    """→ {runs_7d, expected_7d, hours_since_run, predictions_7d, settled_total,
         india_predictions, paper_open, paper_closed, paper_win_rate,
         paper_avg_pnl, grade, issues}"""
    now = datetime.now(timezone.utc)
    out = {"runs_7d": None, "expected_7d": 21, "hours_since_run": None,
           "predictions_7d": None, "settled_total": None,
           "india_predictions": None, "paper_open": 0, "paper_closed": 0,
           "paper_win_rate": None, "paper_avg_pnl": None,
           "grade": "RED", "issues": []}
    c = _client()
    week = (now - timedelta(days=7)).isoformat()

    if c:
        try:
            snaps = (c.table("pipeline_snapshots").select("snapshot_at")
                     .gte("snapshot_at", week).order("snapshot_at", desc=True)
                     .limit(60).execute()).data or []
            out["runs_7d"] = len(snaps)
            if snaps:
                last = datetime.fromisoformat(
                    snaps[0]["snapshot_at"].replace("Z", "+00:00"))
                out["hours_since_run"] = round(
                    (now - last).total_seconds() / 3600, 1)
        except Exception:
            pass
        try:
            preds = (c.table("predictions").select("id,ticker,return_7d")
                     .gte("predicted_at", week).limit(2000).execute()).data or []
            out["predictions_7d"] = len(preds)
            out["india_predictions"] = sum(
                1 for p in preds if str(p.get("ticker", "")).endswith(".NS"))
        except Exception:
            pass
        try:
            settled = (c.table("predictions").select("id", count="exact")
                       .not_.is_("return_7d", "null").execute())
            out["settled_total"] = settled.count
        except Exception:
            pass
        try:
            pt = (c.table("paper_trades").select("status,pnl_pct")
                  .limit(1000).execute()).data or []
        except Exception:
            pt = []
    else:
        pt = []

    if not pt:  # local paper book fallback
        try:
            import json
            pt = json.loads((Path.home() / ".intl_snapshots" /
                             "paper_trades.json").read_text())
        except Exception:
            pt = []
    closed = [t for t in pt if t.get("status") == "closed"]
    out["paper_open"] = sum(1 for t in pt if t.get("status") == "open")
    out["paper_closed"] = len(closed)
    if closed:
        wins = sum(1 for t in closed if (t.get("pnl_pct") or 0) > 0)
        out["paper_win_rate"] = wins / len(closed)
        out["paper_avg_pnl"] = sum(t.get("pnl_pct") or 0
                                   for t in closed) / len(closed)

    # Grade
    issues = []
    if out["hours_since_run"] is None or out["hours_since_run"] > 24:
        issues.append("pipeline silent >24h — keep the Mac awake through "
                      "06:00/12:00/17:00 IST")
    if (out["runs_7d"] or 0) < 10:
        issues.append(f"only {out['runs_7d'] or 0}/21 runs last 7d — "
                      "calibration is starving")
    if (out["predictions_7d"] or 0) == 0:
        issues.append("no predictions logged this week")
    out["issues"] = issues
    out["grade"] = ("GREEN" if not issues else
                    "AMBER" if len(issues) == 1 else "RED")
    return out
