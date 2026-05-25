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
