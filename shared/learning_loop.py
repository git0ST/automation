"""Self-improvement loop — outcome correlation + adaptive weight tuning.

Daily flow:
  1. correlate_outcomes()   — fill forward returns for predictions ≥1d old
  2. tune_weights()         — recommend new weights from accumulated data
  3. snapshot_performance() — log per-strategy/regime metrics for the UI

Called by pipeline post-run. UI also surfaces these stats so the user can
see the model evolving and decide whether to trust new weights.
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


# ── Outcome correlation ──────────────────────────────────────────────────────

def correlate_outcomes(batch_limit: int = 200) -> dict:
    """Fill forward returns for all predictions older than 1 day using yfinance.

    Returns {processed, updated, errors, skipped}.
    Idempotent — only updates rows where return_1d IS NULL.
    """
    client = _client()
    if not client:
        return {"processed": 0, "updated": 0, "errors": 0, "msg": "no_client"}
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        return {"processed": 0, "updated": 0, "errors": 0, "msg": "yfinance missing"}

    cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    try:
        rows = (client.table("predictions")
                .select("id,ticker,predicted_at,price_at_pred")
                .is_("return_1d", "null")
                .lte("predicted_at", cutoff)
                .limit(batch_limit)
                .execute()).data or []
    except Exception as e:
        return {"processed": 0, "updated": 0, "errors": 0, "msg": str(e)}

    processed = updated = errors = skipped = 0
    # Batch tickers to reduce yfinance overhead
    from collections import defaultdict
    by_ticker = defaultdict(list)
    for r in rows:
        by_ticker[r["ticker"]].append(r)

    for ticker, ticker_rows in by_ticker.items():
        processed += len(ticker_rows)
        try:
            earliest = min(
                datetime.fromisoformat(r["predicted_at"].replace("Z", "+00:00"))
                for r in ticker_rows
            )
            start = earliest.strftime("%Y-%m-%d")
            hist = yf.Ticker(ticker).history(start=start, period="45d", auto_adjust=True)
            if hist.empty:
                skipped += len(ticker_rows)
                continue
            closes = hist["Close"]

            for r in ticker_rows:
                base = float(r.get("price_at_pred") or 0)
                if base <= 0:
                    skipped += 1
                    continue
                pred_dt = datetime.fromisoformat(r["predicted_at"].replace("Z", "+00:00"))
                # Find closes at +1d, +3d, +7d, +30d from prediction
                future = closes[closes.index.to_pydatetime() >= pred_dt.replace(tzinfo=None)
                                if not closes.index.tz else closes.index >= pred_dt]
                # Defensive: fall back to positional indexing if tz handling differs
                if len(future) == 0:
                    future = closes.iloc[len(closes) // 2:]

                vals = future.values
                ret_1d  = (vals[0]  / base - 1) * 100 if len(vals) >= 1  else None
                ret_3d  = (vals[2]  / base - 1) * 100 if len(vals) >= 3  else None
                ret_7d  = (vals[6]  / base - 1) * 100 if len(vals) >= 7  else None
                ret_30d = (vals[29] / base - 1) * 100 if len(vals) >= 30 else None

                window = vals[:min(30, len(vals))]
                max_fav = ((window.max() / base) - 1) * 100 if len(window) else None
                max_adv = ((window.min() / base) - 1) * 100 if len(window) else None

                try:
                    client.table("predictions").update({
                        "return_1d":     float(ret_1d)  if ret_1d  is not None else None,
                        "return_3d":     float(ret_3d)  if ret_3d  is not None else None,
                        "return_7d":     float(ret_7d)  if ret_7d  is not None else None,
                        "return_30d":    float(ret_30d) if ret_30d is not None else None,
                        "max_favorable": float(max_fav) if max_fav is not None else None,
                        "max_adverse":   float(max_adv) if max_adv is not None else None,
                        "correlated_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("id", r["id"]).execute()
                    updated += 1
                except Exception:
                    errors += 1
        except Exception:
            errors += len(ticker_rows)
    return {"processed": processed, "updated": updated,
            "errors": errors, "skipped": skipped}


# ── Adaptive weight tuning ──────────────────────────────────────────────────

def tune_weights(min_observations: int = 20, lookback_days: int = 90) -> dict:
    """Compute new weights from prediction history.

    Calls the SQL `recommend_model_weights` function. Returns dict with
    recommended weights + metadata.
    """
    client = _client()
    if not client:
        return {"msg": "no_client"}
    try:
        result = client.rpc("recommend_model_weights",
                             {"p_min_observations": min_observations,
                              "p_lookback_days":    lookback_days}).execute()
        rows = result.data or []
        if not rows:
            return {"msg": "no_data"}
        return rows[0]
    except Exception as e:
        return {"msg": f"rpc_error: {e}"}


def activate_weights(version: str, tech_w: float, sent_w: float,
                     analyst_w: float, vol_w: float,
                     regime: str | None = None,
                     trained_on: int = 0, hit_rate: float | None = None,
                     notes: str = "") -> bool:
    """Activate a new weight set. Deactivates the previous one for same regime."""
    client = _client()
    if not client:
        return False
    try:
        # Deactivate previous active row for the same regime
        q = client.table("model_weights").update({"active": False})
        q = q.is_("regime", "null") if regime is None else q.eq("regime", regime)
        q.eq("active", True).execute()
        # Insert new
        client.table("model_weights").insert({
            "version":         version,
            "regime":          regime,
            "technical_w":     tech_w,
            "sentiment_w":     sent_w,
            "analyst_w":       analyst_w,
            "vol_w":           vol_w,
            "trained_on":      trained_on,
            "hit_rate_7d":     hit_rate,
            "active":          True,
            "notes":           notes,
        }).execute()
        return True
    except Exception:
        return False


def load_active_weights(regime: str | None = None) -> dict:
    """Get the active weights for a regime (or default if regime-specific missing)."""
    client = _client()
    if not client:
        return _baseline_weights()
    try:
        # Try regime-specific first
        if regime:
            r = (client.table("model_weights")
                 .select("*")
                 .eq("active", True)
                 .eq("regime", regime)
                 .limit(1)
                 .execute()).data
            if r:
                return r[0]
        # Fall back to default (regime IS NULL)
        r = (client.table("model_weights")
             .select("*")
             .eq("active", True)
             .is_("regime", "null")
             .limit(1)
             .execute()).data
        if r:
            return r[0]
    except Exception:
        pass
    return _baseline_weights()


def _baseline_weights() -> dict:
    return {
        "version":         "v1.0-baseline",
        "technical_w":     0.35,
        "sentiment_w":     0.25,
        "analyst_w":       0.25,
        "vol_w":           0.15,
        "conf_multiplier": 1.0,
        "regime":          None,
    }


# ── Performance snapshots ────────────────────────────────────────────────────

def strategy_performance(min_obs: int = 3) -> list[dict]:
    """Per-strategy hit rate + avg return from v_strategy_performance."""
    client = _client()
    if not client:
        return []
    try:
        rows = (client.table("v_strategy_performance").select("*").execute()).data or []
        return [r for r in rows if (r.get("n_settled") or 0) >= min_obs]
    except Exception:
        return []


def regime_performance(min_obs: int = 3) -> list[dict]:
    """Per-regime hit rate from v_regime_performance."""
    client = _client()
    if not client:
        return []
    try:
        rows = (client.table("v_regime_performance").select("*").execute()).data or []
        return [r for r in rows if (r.get("n_settled") or 0) >= min_obs]
    except Exception:
        return []


def calibration_table() -> list[dict]:
    """Confidence band → actual hit rate (model calibration)."""
    client = _client()
    if not client:
        return []
    try:
        return (client.table("v_calibration").select("*").execute()).data or []
    except Exception:
        return []


# Module-level TTL cache — composite_prediction calls load_calibration_map once
# per scanned ticker (≈100×/scan); we must not hit Supabase that many times.
_CAL_CACHE: dict = {"ts": 0.0, "data": None}


def load_calibration_map(ttl_seconds: int = 300) -> dict:
    """Return {(confidence_band, direction): (hit_rate_7d, n_settled)} from v_calibration.

    Cached in-process for ttl_seconds. Used by the prediction engine to map
    stated confidence onto the empirically observed hit rate (reliability
    calibration). Empty dict when unavailable → caller leaves confidence as-is.
    """
    import time
    now = time.time()
    if _CAL_CACHE["data"] is not None and (now - _CAL_CACHE["ts"]) < ttl_seconds:
        return _CAL_CACHE["data"]

    out: dict = {}
    client = _client()
    if client:
        try:
            rows = (client.table("v_calibration").select("*").execute()).data or []
            for r in rows:
                band = r.get("confidence_band")
                direction = r.get("direction")
                hit = r.get("hit_rate_7d")
                n = r.get("n_settled") or 0
                if band and direction and hit is not None:
                    out[(band, direction)] = (float(hit), int(n))
        except Exception:
            out = {}
    _CAL_CACHE.update(ts=now, data=out)
    return out


# ── Single-call orchestrator ────────────────────────────────────────────────

def run_learning_cycle(auto_activate: bool = False) -> dict:
    """Full daily cycle: correlate → tune → optionally activate.

    auto_activate=True only after at least 50 settled predictions exist.
    Otherwise produces recommendations for human review on the Track Record page.
    """
    out = {"correlation": None, "tuning": None, "activated": False}

    out["correlation"] = correlate_outcomes()

    tuning = tune_weights()
    out["tuning"] = tuning

    if auto_activate and tuning.get("trained_on", 0) >= 50:
        ok = activate_weights(
            version=f"v1.1-learned-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
            tech_w=tuning.get("technical_w", 0.35),
            sent_w=tuning.get("sentiment_w", 0.25),
            analyst_w=tuning.get("analyst_w", 0.25),
            vol_w=tuning.get("vol_w", 0.15),
            trained_on=tuning.get("trained_on", 0),
            hit_rate=tuning.get("hit_rate"),
            notes=tuning.get("notes", "") + " · auto-activated by learning_loop",
        )
        out["activated"] = ok
    return out
