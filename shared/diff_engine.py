"""'What changed' diff engine — compare today vs yesterday's state.

Used by the Overview page to surface salient deltas without the user
having to remember yesterday's numbers.
"""
from __future__ import annotations
import os
from datetime import datetime, timezone, timedelta


def _client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None


def diff_regime() -> dict:
    """Compare today's regime to yesterday's. Returns:
        {changed, current, previous, growth_delta, inflation_delta, srs_delta, ...}
    """
    client = _client()
    if not client:
        return {}
    try:
        rows = (client.table("regime_snapshots")
                .select("regime,label,confidence_pct,growth_score,inflation_score,captured_at")
                .order("captured_at", desc=True)
                .limit(2)
                .execute()).data or []
        if len(rows) < 2:
            return {"changed": False, "current": rows[0] if rows else {}, "previous": None}
        current, previous = rows[0], rows[1]
        return {
            "changed":          current["regime"] != previous["regime"],
            "current":          current,
            "previous":         previous,
            "growth_delta":     (current["growth_score"] or 0)    - (previous["growth_score"] or 0),
            "inflation_delta":  (current["inflation_score"] or 0) - (previous["inflation_score"] or 0),
            "confidence_delta": (current["confidence_pct"] or 0)  - (previous["confidence_pct"] or 0),
        }
    except Exception:
        return {}


def diff_risk() -> dict:
    """Compare today's SRS to yesterday's."""
    client = _client()
    if not client:
        return {}
    try:
        rows = (client.table("risk_scores")
                .select("srs,level,captured_at")
                .order("captured_at", desc=True)
                .limit(2)
                .execute()).data or []
        if len(rows) < 2:
            return {"changed": False, "current": rows[0] if rows else {}, "previous": None}
        current, previous = rows[0], rows[1]
        return {
            "changed":   current.get("level") != previous.get("level"),
            "current":   current,
            "previous":  previous,
            "srs_delta": (current["srs"] or 0) - (previous["srs"] or 0),
        }
    except Exception:
        return {}


def diff_sentiment() -> dict:
    """Compare last-24h sentiment to prior-24h."""
    client = _client()
    if not client:
        return {}
    try:
        now = datetime.now(timezone.utc)
        cutoff_24h = (now - timedelta(hours=24)).isoformat()
        cutoff_48h = (now - timedelta(hours=48)).isoformat()

        # Recent 24h
        recent = (client.table("articles")
                  .select("sentiment_label")
                  .gte("briefing_date", cutoff_24h[:10])
                  .execute()).data or []
        # Prior 24h
        prior = (client.table("articles")
                 .select("sentiment_label")
                 .gte("briefing_date", cutoff_48h[:10])
                 .lt("briefing_date",  cutoff_24h[:10])
                 .execute()).data or []

        def _summarize(rows):
            if not rows: return {"bull": 0, "bear": 0, "neutral": 0, "total": 0}
            bull = sum(1 for r in rows if r.get("sentiment_label") == "bullish")
            bear = sum(1 for r in rows if r.get("sentiment_label") == "bearish")
            return {"bull": bull, "bear": bear,
                    "neutral": len(rows) - bull - bear,
                    "total": len(rows),
                    "bull_pct": round(bull / len(rows) * 100, 1),
                    "bear_pct": round(bear / len(rows) * 100, 1)}

        r_sum = _summarize(recent)
        p_sum = _summarize(prior)
        return {
            "current":   r_sum,
            "previous":  p_sum,
            "bull_delta": r_sum.get("bull_pct", 0) - p_sum.get("bull_pct", 0),
            "bear_delta": r_sum.get("bear_pct", 0) - p_sum.get("bear_pct", 0),
        }
    except Exception:
        return {}


def diff_signals(limit: int = 30) -> dict:
    """Surface new alpha signals since yesterday — insider trades, options, etc."""
    client = _client()
    if not client:
        return {}
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        new_signals = (client.table("signals")
                       .select("*")
                       .gte("created_at", cutoff)
                       .order("created_at", desc=True)
                       .limit(limit)
                       .execute()).data or []
        # Group by source for summary
        from collections import Counter
        by_source = Counter(s.get("source") for s in new_signals if isinstance(s, dict))
        by_sent = Counter(s.get("sentiment_label") for s in new_signals if isinstance(s, dict))
        return {
            "new_count":  len(new_signals),
            "by_source":  dict(by_source),
            "by_sentiment": dict(by_sent),
            "items":      new_signals[:10],
        }
    except Exception:
        return {}


def summary() -> dict:
    """All diffs in one call — for the 'What changed today' Overview section."""
    return {
        "regime":    diff_regime(),
        "risk":      diff_risk(),
        "sentiment": diff_sentiment(),
        "signals":   diff_signals(),
    }
