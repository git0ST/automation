"""Alert rule engine — user-defined thresholds, runtime-evaluated.

Alert types:
  - price_above / price_below   — ticker threshold
  - rsi_above / rsi_below       — momentum threshold
  - srs_above                   — systemic risk threshold
  - sentiment_shift             — bullish/bearish swing > N pct points
  - hot_entity                  — cross-source mention of entity
  - regime_change               — regime transition detected
"""
from __future__ import annotations
import os
from datetime import datetime, timezone


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


# ── Rule management ─────────────────────────────────────────────────────────

def create_rule(name: str, rule_type: str, ticker: str | None = None,
                threshold: float | None = None) -> bool:
    client = _client()
    if not client:
        return False
    try:
        client.table("alert_rules").insert({
            "name":      name,
            "rule_type": rule_type,
            "ticker":    ticker,
            "threshold": threshold,
            "active":    True,
        }).execute()
        return True
    except Exception:
        return False


def list_rules(active_only: bool = True) -> list[dict]:
    client = _client()
    if not client:
        return []
    try:
        q = client.table("alert_rules").select("*").order("created_at", desc=True)
        if active_only:
            q = q.eq("active", True)
        return q.execute().data or []
    except Exception:
        return []


def toggle_rule(rule_id: int, active: bool) -> bool:
    client = _client()
    if not client:
        return False
    try:
        client.table("alert_rules").update({"active": active}).eq("id", rule_id).execute()
        return True
    except Exception:
        return False


def delete_rule(rule_id: int) -> bool:
    client = _client()
    if not client:
        return False
    try:
        client.table("alert_rules").delete().eq("id", rule_id).execute()
        return True
    except Exception:
        return False


# ── Event log ───────────────────────────────────────────────────────────────

def fire_event(rule_id: int | None, ticker: str | None, message: str,
               level: str = "info", data: dict | None = None) -> bool:
    client = _client()
    if not client:
        return False
    try:
        client.table("alert_events").insert({
            "rule_id":      rule_id,
            "ticker":       ticker,
            "message":      message,
            "level":        level,
            "data":         data or {},
        }).execute()
        if rule_id:
            try:
                client.rpc("increment", {"x": 1})  # noop if RPC missing
            except Exception:
                pass
            try:
                client.table("alert_rules").update({
                    "last_triggered": datetime.now(timezone.utc).isoformat(),
                }).eq("id", rule_id).execute()
            except Exception:
                pass
        return True
    except Exception:
        return False


def recent_events(limit: int = 20, unacknowledged_only: bool = False) -> list[dict]:
    client = _client()
    if not client:
        return []
    try:
        q = client.table("alert_events").select("*").order("triggered_at", desc=True).limit(limit)
        if unacknowledged_only:
            q = q.eq("acknowledged", False)
        return q.execute().data or []
    except Exception:
        return []


def acknowledge_event(event_id: int) -> bool:
    client = _client()
    if not client:
        return False
    try:
        client.table("alert_events").update({"acknowledged": True}).eq("id", event_id).execute()
        return True
    except Exception:
        return False


# ── Evaluator: runs each active rule against current data ────────────────────

def evaluate_rules(quotes: dict, regime: dict, risk: dict,
                   sentiment: dict, hot_entities: list[str]) -> int:
    """Run all active rules. Fires events when conditions met.

    Args:
        quotes:        {ticker: {price, change_pct, rsi}}
        regime:        latest regime dict
        risk:          latest risk dict (with 'srs')
        sentiment:     {bullish_pct, bearish_pct} aggregate
        hot_entities:  list of cross-source amplified entities

    Returns count of events fired.
    """
    rules = list_rules(active_only=True)
    fired = 0
    for rule in rules:
        try:
            triggered, msg, level = _check_rule(rule, quotes, regime, risk,
                                                 sentiment, hot_entities)
            if triggered:
                fire_event(rule["id"], rule.get("ticker"), msg, level,
                           data={"rule_type": rule["rule_type"]})
                fired += 1
        except Exception:
            continue
    return fired


def _check_rule(rule: dict, quotes: dict, regime: dict, risk: dict,
                sentiment: dict, hot_entities: list[str]) -> tuple[bool, str, str]:
    rule_type = rule["rule_type"]
    ticker    = rule.get("ticker")
    threshold = rule.get("threshold")
    q         = (quotes or {}).get(ticker) if ticker else None

    if rule_type == "price_above" and q and threshold is not None:
        if q.get("price", 0) >= threshold:
            return True, f"{ticker} crossed ${threshold:.2f} (now ${q['price']:.2f})", "info"

    if rule_type == "price_below" and q and threshold is not None:
        if q.get("price", 0) <= threshold:
            return True, f"{ticker} fell below ${threshold:.2f} (now ${q['price']:.2f})", "warning"

    if rule_type == "rsi_above" and q and threshold is not None:
        rsi = q.get("rsi")
        if rsi is not None and rsi >= threshold:
            return True, f"{ticker} RSI {rsi:.0f} ≥ {threshold:.0f} (overbought signal)", "warning"

    if rule_type == "rsi_below" and q and threshold is not None:
        rsi = q.get("rsi")
        if rsi is not None and rsi <= threshold:
            return True, f"{ticker} RSI {rsi:.0f} ≤ {threshold:.0f} (oversold opportunity)", "info"

    if rule_type == "srs_above" and threshold is not None:
        srs = (risk or {}).get("srs", 0)
        if srs >= threshold:
            return True, f"Systemic Risk Score {srs:.0f} ≥ {threshold:.0f}", "critical"

    if rule_type == "hot_entity" and hot_entities:
        if any(rule.get("ticker", "").upper() in (e or "").upper() for e in hot_entities):
            return True, f"{ticker} mentioned across 3+ sources (consensus signal)", "info"

    return False, "", "info"
