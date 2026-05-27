"""
Supabase persistence layer for the Intelligence Terminal.

Handles upsert of articles, market snapshots, macro indicators,
briefings, alerts and fear/greed readings.
"""

import os
from datetime import date, datetime, timezone
from typing import Optional

_client = None


def get_client():
    global _client
    if _client is not None:
        return _client
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        _client = create_client(url, key)
    except Exception as e:
        print(f"[supabase] client init failed: {e}")
        _client = None
    return _client


def is_available() -> bool:
    return get_client() is not None


# ── Articles ──────────────────────────────────────────────────────────────────

def upsert_articles(items: list[dict]) -> dict:
    """Upsert a batch of pipeline items into the articles table."""
    client = get_client()
    if not client:
        return {"created": 0, "skipped": 0, "errors": 0}

    rows = []
    today = date.today().isoformat()
    for it in items:
        if it.get("source") == "finance":
            continue
        rows.append({
            "id":             it.get("id", ""),
            "source":         it.get("source", ""),
            "title":          (it.get("title") or "")[:500],
            "url":            it.get("url", ""),
            "preview":        (it.get("preview") or "")[:1000],
            "score":          it.get("score", 0),
            "terminal_score": it.get("terminal_score", 0),
            "sentiment_score":it.get("sentiment_score"),
            "sentiment_label":it.get("sentiment_label"),
            "tags":           it.get("tags", []),
            "sector":         it.get("sector"),
            "meta":           (it.get("meta") or "")[:200],
            "entities":       it.get("entities", []),
            "briefing_date":  today,
        })

    if not rows:
        return {"created": 0, "skipped": 0, "errors": 0}

    created = skipped = errors = 0
    batch_size = 100
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        try:
            resp = client.table("articles").upsert(
                batch,
                on_conflict="url",
                ignore_duplicates=False,
            ).execute()
            created += len(resp.data or [])
        except Exception as e:
            print(f"[supabase] articles batch error: {e}")
            errors += len(batch)

    return {"created": created, "skipped": skipped, "errors": errors}


def get_today_urls() -> set[str]:
    """Return URLs already stored today — for local dedup."""
    client = get_client()
    if not client:
        return set()
    try:
        today = date.today().isoformat()
        resp = (client.table("articles")
                .select("url")
                .eq("briefing_date", today)
                .execute())
        return {r["url"] for r in (resp.data or [])}
    except Exception:
        return set()


# ── Market Snapshots ──────────────────────────────────────────────────────────

def save_market_snapshot(market_items: list[dict]):
    client = get_client()
    if not client or not market_items:
        return
    now = datetime.now(timezone.utc).isoformat()
    rows = [{
        "ticker":     m.get("ticker", ""),
        "name":       m.get("name", ""),
        "price":      m.get("price", 0),
        "change_pct": m.get("change_pct", 0),
        "type":       m.get("type", "stock"),
        "snapshot_at":now,
    } for m in market_items]
    try:
        client.table("market_snapshots").insert(rows).execute()
    except Exception as e:
        print(f"[supabase] market snapshot error: {e}")


def get_market_history(ticker: str, limit: int = 50) -> list[dict]:
    """Recent snapshots for sparkline rendering."""
    client = get_client()
    if not client:
        return []
    try:
        resp = (client.table("market_snapshots")
                .select("price,change_pct,snapshot_at")
                .eq("ticker", ticker)
                .order("snapshot_at", desc=True)
                .limit(limit)
                .execute())
        return list(reversed(resp.data or []))
    except Exception:
        return []


# ── Macro Indicators ──────────────────────────────────────────────────────────

def save_macro_indicators(indicators: list[dict]):
    client = get_client()
    if not client or not indicators:
        return
    try:
        client.table("macro_indicators").upsert(
            indicators, on_conflict="series_id,period"
        ).execute()
    except Exception as e:
        print(f"[supabase] macro error: {e}")


def get_latest_macro() -> list[dict]:
    client = get_client()
    if not client:
        return []
    try:
        resp = (client.table("macro_indicators")
                .select("series_id,name,value,unit,period")
                .order("fetched_at", desc=True)
                .limit(20)
                .execute())
        # Return only the latest reading per series
        seen = set()
        result = []
        for r in (resp.data or []):
            if r["series_id"] not in seen:
                seen.add(r["series_id"])
                result.append(r)
        return result
    except Exception:
        return []


# ── Briefings ─────────────────────────────────────────────────────────────────

def save_briefing(content: str, item_count: int, time_of_day: str):
    client = get_client()
    if not client or not content:
        return
    try:
        client.table("briefings").insert({
            "date":        date.today().isoformat(),
            "time_of_day": time_of_day,
            "content":     content,
            "item_count":  item_count,
        }).execute()
    except Exception as e:
        print(f"[supabase] briefing error: {e}")


def get_latest_briefing() -> Optional[str]:
    client = get_client()
    if not client:
        return None
    try:
        resp = (client.table("briefings")
                .select("content")
                .order("created_at", desc=True)
                .limit(1)
                .execute())
        rows = resp.data or []
        return rows[0]["content"] if rows else None
    except Exception:
        return None


# ── Alerts ────────────────────────────────────────────────────────────────────

def create_alert(type_: str, title: str, body: str, priority: int = 0, ticker: str = None):
    client = get_client()
    if not client:
        return
    try:
        client.table("alerts").insert({
            "type":     type_,
            "title":    title,
            "body":     body,
            "priority": priority,
            "ticker":   ticker,
        }).execute()
    except Exception as e:
        print(f"[supabase] alert error: {e}")


def get_recent_alerts(limit: int = 10) -> list[dict]:
    client = get_client()
    if not client:
        return []
    try:
        resp = (client.table("alerts")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute())
        return resp.data or []
    except Exception:
        return []


# ── Fear & Greed ──────────────────────────────────────────────────────────────

def save_fear_greed(value: int, label: str, source: str = "crypto"):
    client = get_client()
    if not client:
        return
    try:
        client.table("fear_greed").insert({
            "value":  value,
            "label":  label,
            "source": source,
        }).execute()
    except Exception as e:
        print(f"[supabase] fear_greed error: {e}")


def get_latest_fear_greed() -> Optional[dict]:
    client = get_client()
    if not client:
        return None
    try:
        resp = (client.table("fear_greed")
                .select("value,label,source,fetched_at")
                .order("fetched_at", desc=True)
                .limit(1)
                .execute())
        rows = resp.data or []
        return rows[0] if rows else None
    except Exception:
        return None


# ── Signals (insider trades, options flow, congress) ──────────────────────────

def save_signals(items: list[dict]):
    """Upsert trade signals — insider, options, congress."""
    client = get_client()
    if not client or not items:
        return
    rows = []
    for it in items:
        row = {
            "id":              it.get("id", ""),
            "source":          it.get("source", ""),
            "title":           (it.get("title") or "")[:500],
            "url":             it.get("url", ""),
            "preview":         (it.get("preview") or "")[:1000],
            "sentiment_label": it.get("sentiment_label", "neutral"),
            "sentiment_score": it.get("sentiment_score", 0),
            "entities":        it.get("entities", []),
            "tags":            it.get("tags", []),
        }
        # Attach source-specific payload
        for key in ("option_data", "macro_data", "market_data"):
            if it.get(key):
                row["payload"] = it[key]
                break
        rows.append(row)
    batch_size = 50
    for i in range(0, len(rows), batch_size):
        try:
            client.table("signals").upsert(
                rows[i:i + batch_size], on_conflict="id", ignore_duplicates=False
            ).execute()
        except Exception as e:
            print(f"[supabase] signals batch error: {e}")


def get_recent_signals(source: Optional[str] = None, limit: int = 30) -> list[dict]:
    client = get_client()
    if not client:
        return []
    try:
        q = (client.table("signals")
             .select("id,source,title,url,preview,sentiment_label,sentiment_score,entities,tags,payload,created_at")
             .order("created_at", desc=True)
             .limit(limit))
        if source:
            q = q.eq("source", source)
        return (q.execute()).data or []
    except Exception:
        return []


# ── Intelligence: Regime + Risk persistence ───────────────────────────────────

def save_regime_snapshot(regime: dict):
    """Persist a regime reading for historical trend analysis."""
    client = get_client()
    if not client or not regime:
        return
    try:
        client.table("regime_snapshots").insert({
            "regime":          regime.get("regime", ""),
            "label":           regime.get("label", ""),
            "color":           regime.get("color"),
            "description":     regime.get("description"),
            "confidence_pct":  regime.get("confidence_pct", 0),
            "growth_score":    regime.get("growth_score", 0),
            "inflation_score": regime.get("inflation_score", 0),
            "transition_risk": regime.get("transition_risk", "low"),
            "favors":          regime.get("favors", []),
            "avoids":          regime.get("avoids", []),
            "signals":         regime.get("signals", []),
        }).execute()
    except Exception as e:
        print(f"[supabase] regime snapshot error: {e}")


def save_risk_score(risk: dict):
    """Persist a Systemic Risk Score snapshot."""
    client = get_client()
    if not client or not risk:
        return
    try:
        client.table("risk_scores").insert({
            "srs":       risk.get("srs", 0),
            "level":     risk.get("level", "Moderate"),
            "color":     risk.get("color"),
            "top_risks": risk.get("top_risks", []),
            "factors":   risk.get("factors", []),
        }).execute()
    except Exception as e:
        print(f"[supabase] risk score error: {e}")


def get_regime_history(limit: int = 30) -> list[dict]:
    """Fetch recent regime snapshots for trend display."""
    client = get_client()
    if not client:
        return []
    try:
        return (client.table("regime_snapshots")
                .select("id,regime,label,color,confidence_pct,growth_score,inflation_score,transition_risk,captured_at")
                .order("captured_at", desc=True)
                .limit(limit)
                .execute()).data or []
    except Exception:
        return []


def get_risk_history(limit: int = 30) -> list[dict]:
    """Fetch recent SRS history for trend display."""
    client = get_client()
    if not client:
        return []
    try:
        return (client.table("risk_scores")
                .select("id,srs,level,color,top_risks,captured_at")
                .order("captured_at", desc=True)
                .limit(limit)
                .execute()).data or []
    except Exception:
        return []


# ── Intraday Bars ─────────────────────────────────────────────────────────────

def save_intraday_bars(bars: list[dict]) -> int:
    """Upsert 5-min OHLCV bars. Returns count written."""
    client = get_client()
    if not client or not bars:
        return 0
    written = 0
    batch_size = 200
    for i in range(0, len(bars), batch_size):
        batch = bars[i:i + batch_size]
        try:
            client.table("intraday_bars").upsert(
                batch, on_conflict="ticker,bar_time", ignore_duplicates=True
            ).execute()
            written += len(batch)
        except Exception as e:
            print(f"[supabase] intraday bars batch error: {e}")
    return written


def get_intraday_bars(ticker: str, limit: int = 78) -> list[dict]:
    """Fetch intraday bars for a ticker (78 bars ≈ full 6.5h session at 5min)."""
    client = get_client()
    if not client:
        return []
    try:
        return list(reversed(
            (client.table("intraday_bars")
             .select("ticker,bar_time,open,high,low,close,volume,vwap,vwap_dev,vol_ratio,rsi_14")
             .eq("ticker", ticker)
             .order("bar_time", desc=True)
             .limit(limit)
             .execute()).data or []
        ))
    except Exception:
        return []


# ── Trade Signals ─────────────────────────────────────────────────────────────

def get_trade_signals(ticker: Optional[str] = None, status: str = "open",
                      limit: int = 30) -> list[dict]:
    """Fetch execution-grade trade signals."""
    client = get_client()
    if not client:
        return []
    try:
        q = (client.table("trade_signals")
             .select("*")
             .eq("status", status)
             .order("fired_at", desc=True)
             .limit(limit))
        if ticker:
            q = q.eq("ticker", ticker)
        return q.execute().data or []
    except Exception:
        return []


def expire_stale_signals() -> int:
    """Mark signals past their expires_at as expired. Returns count updated."""
    client = get_client()
    if not client:
        return 0
    try:
        now = datetime.now(timezone.utc).isoformat()
        resp = (client.table("trade_signals")
                .update({"status": "expired"})
                .eq("status", "open")
                .lt("expires_at", now)
                .execute())
        return len(resp.data or [])
    except Exception:
        return 0


# ── Earnings Events ───────────────────────────────────────────────────────────

def get_upcoming_earnings(days_ahead: int = 7) -> list[dict]:
    """Fetch tickers with earnings within days_ahead."""
    client = get_client()
    if not client:
        return []
    try:
        from datetime import date, timedelta
        today   = date.today().isoformat()
        cutoff  = (date.today() + timedelta(days=days_ahead)).isoformat()
        return (client.table("earnings_events")
                .select("ticker,earnings_date,days_away,eps_estimate,rev_estimate")
                .gte("earnings_date", today)
                .lte("earnings_date", cutoff)
                .order("earnings_date")
                .execute()).data or []
    except Exception:
        return []
