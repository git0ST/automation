"""
Data Lake — compressed pipeline snapshot store.

Every pipeline run writes a zlib-compressed JSON snapshot containing the
complete market state: all scored items, market prices, macro indicators,
sentiment, regime, risk, signals, and options flow.

This archive fuels:
  - ML feature engineering (time-series of market state)
  - Backtesting (replay historical snapshots)
  - Prediction validation (what did the market look like when signal fired?)
  - Regime transition analysis

Storage:
  - Supabase pipeline_snapshots table: metadata + top items queryable in SQL
  - Local disk: ~/.intl_snapshots/YYYYMMDD_HHMMSS.json.gz (full payload)
    Falls back gracefully when disk write fails.

Usage:
    from shared.data_lake import write_snapshot, read_snapshots, load_features
"""
from __future__ import annotations

import base64
import gzip
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# Local snapshot dir — create on first write
_SNAP_DIR = Path.home() / ".intl_snapshots"


# ── Compression helpers ───────────────────────────────────────────────────────

def _compress(obj: dict) -> str:
    """Serialize → UTF-8 → zlib compress → base64 encode. Returns ASCII string."""
    raw = json.dumps(obj, default=str).encode("utf-8")
    compressed = gzip.compress(raw, compresslevel=6)
    return base64.b64encode(compressed).decode("ascii")


def _decompress(data: str) -> dict:
    """Reverse of _compress."""
    compressed = base64.b64decode(data.encode("ascii"))
    raw = gzip.decompress(compressed)
    return json.loads(raw.decode("utf-8"))


# ── Snapshot metadata extractor ───────────────────────────────────────────────

def _build_metadata(payload: dict) -> dict:
    """Extract lightweight, queryable metadata from a full pipeline payload."""
    regime_data = payload.get("regime") or {}
    risk_data   = payload.get("risk")   or {}
    sentiment   = payload.get("sentiment") or {}
    items       = payload.get("items", [])
    signals     = payload.get("signals", [])
    alerts      = payload.get("alerts", [])
    market      = payload.get("market", [])
    macro       = payload.get("macro", [])

    top_items = [
        {
            "title":     it.get("title", "")[:120],
            "source":    it.get("source"),
            "score":     it.get("terminal_score"),
            "sentiment": it.get("sentiment_label"),
            "entities":  it.get("entities", [])[:5],
        }
        for it in sorted(items, key=lambda x: x.get("terminal_score", 0), reverse=True)[:20]
    ]

    market_summary = {
        m["ticker"]: {"price": m.get("price"), "chg": m.get("change_pct")}
        for m in market if m.get("ticker")
    }

    macro_snapshot = {
        m.get("series_id"): m.get("value")
        for m in macro if m.get("series_id")
    }

    return {
        "regime":         regime_data.get("regime"),
        "srs":            risk_data.get("srs"),
        "sentiment_bull": sentiment.get("bullish_pct"),
        "sentiment_bear": sentiment.get("bearish_pct"),
        "item_count":     len(items),
        "signal_count":   len(signals),
        "alert_count":    len(alerts),
        "top_items":      top_items,
        "market_summary": market_summary,
        "macro_snapshot": macro_snapshot,
    }


# ── Write ─────────────────────────────────────────────────────────────────────

def write_snapshot(payload: dict) -> dict:
    """
    Compress and persist a full pipeline payload.

    1. Writes to local disk as .json.gz for ML use.
    2. Writes metadata + compressed blob to Supabase pipeline_snapshots.

    Returns {"local": path|None, "supabase": bool, "size_kb": float}.
    """
    ts = datetime.now(timezone.utc)
    ts_str = ts.strftime("%Y%m%d_%H%M%S")
    meta = _build_metadata(payload)
    compressed = _compress(payload)
    size_kb = round(len(compressed) * 0.75 / 1024, 1)  # base64 is ~4/3 of binary

    # ── Local disk ──
    local_path = None
    try:
        _SNAP_DIR.mkdir(parents=True, exist_ok=True)
        local_path = str(_SNAP_DIR / f"{ts_str}.json.gz")
        raw = json.dumps(payload, default=str).encode("utf-8")
        with gzip.open(local_path, "wb", compresslevel=6) as f:
            f.write(raw)
    except Exception as e:
        print(f"[data_lake] local write failed: {e}")
        local_path = None

    # ── Supabase ──
    sb_ok = False
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    if url and key:
        try:
            from supabase import create_client
            client = create_client(url, key)
            client.table("pipeline_snapshots").insert({
                "snapshot_at":     ts.isoformat(),
                "regime":          meta["regime"],
                "srs":             meta["srs"],
                "sentiment_bull":  meta["sentiment_bull"],
                "sentiment_bear":  meta["sentiment_bear"],
                "item_count":      meta["item_count"],
                "signal_count":    meta["signal_count"],
                "alert_count":     meta["alert_count"],
                "top_items":       meta["top_items"],
                "market_summary":  meta["market_summary"],
                "macro_snapshot":  meta["macro_snapshot"],
                "compressed_data": compressed,
            }).execute()
            sb_ok = True
        except Exception as e:
            print(f"[data_lake] supabase write failed: {e}")

    print(f"  [data_lake] snapshot written — {size_kb}KB local={local_path is not None} sb={sb_ok}")
    return {"local": local_path, "supabase": sb_ok, "size_kb": size_kb}


# ── Read (metadata) ───────────────────────────────────────────────────────────

def read_snapshot_index(limit: int = 100, regime: Optional[str] = None) -> list[dict]:
    """
    Return snapshot metadata rows (no decompression) from Supabase.
    Useful for charting regime/sentiment/SRS over time.
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        return []
    try:
        from supabase import create_client
        client = create_client(url, key)
        q = (client.table("pipeline_snapshots")
             .select("id,snapshot_at,regime,srs,sentiment_bull,sentiment_bear,"
                     "item_count,signal_count,alert_count,market_summary,macro_snapshot")
             .order("snapshot_at", desc=True)
             .limit(limit))
        if regime:
            q = q.eq("regime", regime)
        return q.execute().data or []
    except Exception as e:
        print(f"[data_lake] read index failed: {e}")
        return []


# ── Read (full payload) ───────────────────────────────────────────────────────

def load_snapshot(snapshot_id: str) -> Optional[dict]:
    """
    Load and decompress a full snapshot by ID from Supabase.
    Use for ML feature extraction or backtesting.
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        client = create_client(url, key)
        rows = (client.table("pipeline_snapshots")
                .select("compressed_data,snapshot_at")
                .eq("id", snapshot_id)
                .limit(1)
                .execute()).data or []
        if not rows or not rows[0].get("compressed_data"):
            return None
        payload = _decompress(rows[0]["compressed_data"])
        payload["_snapshot_at"] = rows[0]["snapshot_at"]
        return payload
    except Exception as e:
        print(f"[data_lake] load snapshot failed: {e}")
        return None


def load_local_snapshots(n: int = 30) -> list[dict]:
    """
    Load the N most recent local .json.gz snapshots.
    Returns list of full pipeline payloads, newest first.
    Useful for local ML training without Supabase.
    """
    if not _SNAP_DIR.exists():
        return []
    files = sorted(_SNAP_DIR.glob("*.json.gz"), reverse=True)[:n]
    out = []
    for f in files:
        try:
            with gzip.open(f, "rb") as fh:
                out.append(json.loads(fh.read().decode("utf-8")))
        except Exception:
            continue
    return out


# ── ML feature extraction ─────────────────────────────────────────────────────

def extract_feature_vector(snapshot: dict) -> dict:
    """
    Convert a pipeline snapshot to a flat feature vector for ML models.

    Features:
        regime_*        : one-hot regime encoding
        srs             : systemic risk score
        bull_pct/bear_pct: sentiment split
        vix, ffr, t10y2y, cpi, unrate, dgs10 : macro
        fg_stocks       : stocks fear & greed value
        n_bull_signals  : count of bullish trade signals
        n_bear_signals  : count of bearish trade signals
        avg_terminal_score : avg score of top-20 items
        options_put_call_*: put/call ratio from options signals
    """
    regime_map = {"goldilocks": 0, "reflation": 1, "stagflation": 2, "deflation": 3}
    r = snapshot.get("regime") or {}
    macro = {m.get("series_id"): m.get("value") for m in snapshot.get("macro", [])}
    fg = next((f.get("value") for f in snapshot.get("fear_greed", []) if f.get("source") == "stocks"), None)
    items = snapshot.get("items", [])
    signals = snapshot.get("signals", [])

    # Sentiment from top items
    s_labels = [it.get("sentiment_label") for it in items[:50] if it.get("sentiment_label")]
    n_bull = sum(1 for s in s_labels if s == "bullish")
    n_bear = sum(1 for s in s_labels if s == "bearish")

    # Options signals put/call breakdown
    n_call = sum(1 for s in signals if s.get("source") == "options" and "call" in (s.get("title") or "").lower())
    n_put  = sum(1 for s in signals if s.get("source") == "options" and "put" in (s.get("title") or "").lower())
    put_call = round(n_put / max(n_call, 1), 3)

    avg_score = (sum(it.get("terminal_score", 0) for it in items[:20]) / 20) if items else 0

    regime_str = r.get("regime", "")
    features = {
        # Regime
        "regime_idx":       regime_map.get(regime_str, -1),
        "regime_goldilocks": int(regime_str == "goldilocks"),
        "regime_reflation":  int(regime_str == "reflation"),
        "regime_stagflation":int(regime_str == "stagflation"),
        "regime_deflation":  int(regime_str == "deflation"),
        "regime_confidence": r.get("confidence_pct", 0),
        "growth_score":      r.get("growth_score", 0),
        "inflation_score":   r.get("inflation_score", 0),
        # Risk
        "srs":               snapshot.get("risk", {}).get("srs", 0) if isinstance(snapshot.get("risk"), dict) else 0,
        # Sentiment
        "bull_pct":          snapshot.get("sentiment", {}).get("bullish_pct", 0),
        "bear_pct":          snapshot.get("sentiment", {}).get("bearish_pct", 0),
        "n_bull_items":      n_bull,
        "n_bear_items":      n_bear,
        # Macro
        "vix":    macro.get("VIXCLS"),
        "ffr":    macro.get("FEDFUNDS"),
        "t10y2y": macro.get("T10Y2Y"),
        "cpi":    macro.get("CPIAUCSL"),
        "unrate": macro.get("UNRATE"),
        "dgs10":  macro.get("DGS10"),
        # Market sentiment
        "fg_stocks":     fg,
        # Signals
        "n_signal_bull": sum(1 for s in signals if s.get("sentiment_label") == "bullish"),
        "n_signal_bear": sum(1 for s in signals if s.get("sentiment_label") == "bearish"),
        "put_call_ratio":put_call,
        # Feed quality
        "avg_terminal_score": round(avg_score, 2),
        "total_items":        len(items),
        "total_signals":      len(signals),
    }
    return {k: v for k, v in features.items() if v is not None}
