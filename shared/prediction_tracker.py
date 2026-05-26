"""Log predictions to Supabase and retrieve backtested track record.

Foundation for self-tuning system — every prediction logged with its
component breakdown so we can later correlate which signals predict moves.
"""
from __future__ import annotations
import os
from datetime import datetime, timezone


def _client():
    """Supabase client — anon key for read/write (RLS allows insert)."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None


def log_prediction(ticker: str, direction: str, confidence_pct: float,
                   price: float, source_page: str = "scan",
                   components: list[dict] | None = None,
                   quant_score: float | None = None,
                   quant_grade: str | None = None,
                   vol_regime: str | None = None,
                   strategy_name: str | None = None,
                   regime_at_pred: str | None = None,
                   srs_at_pred: float | None = None,
                   sector: str | None = None,
                   horizon: str | None = None) -> bool:
    """Log a single prediction with full provenance for self-improvement."""
    client = _client()
    if not client:
        return False

    comp_map = {c["name"]: c for c in (components or [])}
    row = {
        "ticker":           ticker,
        "direction":        direction,
        "confidence_pct":   confidence_pct,
        "source_page":      source_page,
        "predicted_at":     datetime.now(timezone.utc).isoformat(),
        "price_at_pred":    price,
        "tech_signal":      (comp_map.get("technical") or {}).get("direction"),
        "tech_strength":    (comp_map.get("technical") or {}).get("strength"),
        "sent_signal":      (comp_map.get("sentiment") or {}).get("direction"),
        "sent_strength":    (comp_map.get("sentiment") or {}).get("strength"),
        "analyst_signal":   (comp_map.get("analyst") or {}).get("direction"),
        "analyst_strength": (comp_map.get("analyst") or {}).get("strength"),
        "vol_regime":       vol_regime,
        "quant_score":      quant_score,
        "quant_grade":      quant_grade,
        # Self-improvement fields (Migration 010)
        "strategy_name":    strategy_name,
        "regime_at_pred":   regime_at_pred,
        "srs_at_pred":      srs_at_pred,
        "sector":           sector,
        "horizon":          horizon,
    }
    # Strip None values to avoid issues on older schemas
    row = {k: v for k, v in row.items() if v is not None}
    try:
        client.table("predictions").insert(row).execute()
        return True
    except Exception:
        # Retry without the migration-010 columns in case schema not updated
        legacy = {k: v for k, v in row.items()
                  if k not in {"strategy_name", "regime_at_pred", "srs_at_pred",
                                "sector", "horizon"}}
        try:
            client.table("predictions").insert(legacy).execute()
            return True
        except Exception:
            return False


def fetch_track_record(days: int = 90) -> list[dict]:
    """Pull all predictions from last N days with their outcomes."""
    client = _client()
    if not client:
        return []
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        rows = (client.table("predictions")
                .select("*")
                .gte("predicted_at", cutoff)
                .order("predicted_at", desc=True)
                .execute()).data or []
        return rows
    except Exception:
        return []


def fetch_stats() -> list[dict]:
    """Pre-aggregated stats by direction × confidence band (from v_prediction_stats)."""
    client = _client()
    if not client:
        return []
    try:
        rows = (client.table("v_prediction_stats")
                .select("*")
                .execute()).data or []
        return rows
    except Exception:
        return []


def correlate_outcomes_inline(batch_limit: int = 100) -> dict:
    """Fill return columns for predictions older than 1 day using yfinance.

    Called by pipeline post-run. Returns {processed, updated, errors}.
    """
    client = _client()
    if not client:
        return {"processed": 0, "updated": 0, "errors": 0}

    try:
        import yfinance as yf
    except ImportError:
        return {"processed": 0, "updated": 0, "errors": 0, "msg": "yfinance not installed"}

    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    try:
        rows = (client.table("predictions")
                .select("id,ticker,predicted_at,price_at_pred")
                .is_("return_1d", "null")
                .lte("predicted_at", cutoff)
                .limit(batch_limit)
                .execute()).data or []
    except Exception:
        return {"processed": 0, "updated": 0, "errors": 0}

    processed = updated = errors = 0
    for r in rows:
        processed += 1
        try:
            ticker = r["ticker"]
            pred_dt = datetime.fromisoformat(r["predicted_at"].replace("Z", "+00:00"))
            base = float(r["price_at_pred"] or 0)
            if base <= 0:
                continue
            # Fetch from prediction date + 30 days
            start = pred_dt.strftime("%Y-%m-%d")
            hist = yf.Ticker(ticker).history(start=start, period="40d", auto_adjust=True)
            if hist.empty:
                continue

            closes = hist["Close"].values
            ret_1d  = (closes[0]  / base - 1) * 100 if len(closes) >= 1  else None
            ret_3d  = (closes[2]  / base - 1) * 100 if len(closes) >= 3  else None
            ret_7d  = (closes[6]  / base - 1) * 100 if len(closes) >= 7  else None
            ret_30d = (closes[29] / base - 1) * 100 if len(closes) >= 30 else None

            # MFE/MAE — best/worst movement during window
            window = closes[:min(30, len(closes))]
            max_fav = ((window.max() / base) - 1) * 100
            max_adv = ((window.min() / base) - 1) * 100

            client.table("predictions").update({
                "return_1d":     ret_1d,
                "return_3d":     ret_3d,
                "return_7d":     ret_7d,
                "return_30d":    ret_30d,
                "max_favorable": float(max_fav),
                "max_adverse":   float(max_adv),
                "correlated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", r["id"]).execute()
            updated += 1
        except Exception:
            errors += 1
    return {"processed": processed, "updated": updated, "errors": errors}
