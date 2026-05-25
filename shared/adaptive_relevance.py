"""Adaptive relevance scoring — incorporates historical predictive power.

The static finance_filter scores by keyword/entity rules. This layer
adjusts those scores using `entity_weights` learned from past
correlation between mentions and subsequent ticker moves.

Workflow:
  1. Static filter returns base score
  2. Adaptive layer multiplies by learned entity weight (default 1.0)
  3. Result is the final terminal_score multiplier

Falls back gracefully when DB/weights unavailable — never breaks pipeline.
"""
from __future__ import annotations
import os
import time
from typing import Optional


_weights_cache: dict[str, float] = {}
_cache_ts: float = 0
_CACHE_TTL = 600  # 10 minutes — entity weights update daily, no need to hammer DB


def _load_entity_weights() -> dict[str, float]:
    """Load current entity weights from Supabase, cached for 10 minutes."""
    global _weights_cache, _cache_ts
    if _weights_cache and (time.time() - _cache_ts) < _CACHE_TTL:
        return _weights_cache

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return {}

    try:
        from supabase import create_client
        client = create_client(url, key)
        rows = client.table("entity_weights").select("entity,current_weight").execute().data or []
        _weights_cache = {r["entity"]: float(r["current_weight"]) for r in rows}
        _cache_ts = time.time()
        return _weights_cache
    except Exception:
        return {}


def adaptive_score(base_score: float, evidence: list[str]) -> tuple[float, dict]:
    """Multiply base score by learned entity weights.

    evidence: list of "tier:value" strings from finance_relevance(), e.g.
        ["ticker:NVDA", "person:elon musk", "org:openai", "innov:agi"]

    Returns (adjusted_score, debug_info).
    """
    weights = _load_entity_weights()
    if not weights:
        return base_score, {"weights_loaded": 0, "adjustments": []}

    multipliers = []
    debug = {"weights_loaded": len(weights), "adjustments": []}

    for ev in evidence:
        # Normalise "tier:value" → entity key matching what update_entity_weights writes
        if ":" not in ev:
            continue
        tier, val = ev.split(":", 1)
        val = val.strip().lower()

        # Try direct match
        key = val
        if key in weights:
            multipliers.append(weights[key])
            debug["adjustments"].append({"entity": key, "weight": weights[key]})
            continue
        # Try prefixed match (e.g. ticker mentioned without prefix in weights table)
        if tier in {"person", "org", "ticker"} and val in weights:
            multipliers.append(weights[val])
            debug["adjustments"].append({"entity": val, "weight": weights[val]})

    if not multipliers:
        return base_score, debug

    # Average multiplier (cap [0.5, 1.75])
    avg_mult = sum(multipliers) / len(multipliers)
    adjusted = base_score * avg_mult
    debug["avg_multiplier"] = round(avg_mult, 3)
    return min(1.0, max(0.0, adjusted)), debug


def record_observation(item: dict) -> bool:
    """Record a scored article observation for later outcome correlation.

    Pipeline calls this after scoring each item. The correlation job runs
    daily to fill in next_1d/3d/7d_return columns.
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return False

    try:
        from supabase import create_client
        client = create_client(url, key)
        client.table("relevance_observations").insert({
            "article_id":      item.get("id", ""),
            "source":          item.get("source", ""),
            "title":           (item.get("title") or "")[:500],
            "url":             item.get("url", ""),
            "finance_score":   item.get("finance_score"),
            "tier_matches":    item.get("evidence", []),
            "entities":        {
                "tickers": item.get("entities", []),
                "hot":     item.get("hot_entities", []),
            },
            "sentiment_label": item.get("sentiment_label"),
        }).execute()
        return True
    except Exception:
        return False
