"""Headless India swing scan — runs inside the pipeline cron.

Calls the SAME engine as the India Invest page (shared/india_swing.py) so the
learning loop accumulates India-specific predictions + feature rows daily:
calibration for the Indian book builds exactly the way it did for the US one.
"""
from __future__ import annotations
import os
import sys
from datetime import datetime, timezone


def _bootstrap() -> None:
    here = os.path.abspath(__file__)
    root = here
    for _ in range(6):
        root = os.path.dirname(root)
        if (os.path.isdir(os.path.join(root, "streamlit"))
                and os.path.isdir(os.path.join(root, "shared"))):
            break
    for p in (root, os.path.join(root, "streamlit")):
        if p not in sys.path:
            sys.path.insert(0, p)


_bootstrap()


def run_india_scan() -> dict:
    """Scan NIFTY 50 → log directional predictions + capture feature rows."""
    try:
        from shared.india_swing import scan_india
    except Exception as e:
        return {"error": f"engine import failed: {e}"}

    try:
        results, regime = scan_india()
    except Exception as e:
        return {"error": f"scan failed: {e}"}

    ts = datetime.now(timezone.utc).isoformat()
    logged = 0
    try:
        from shared.prediction_tracker import log_prediction
        for r in results:
            if r["confidence"] >= 55 and r["direction"] != "neutral" \
                    and r["avoid_level"] != "AVOID":
                if log_prediction(
                    ticker=r["ticker"], direction=r["direction"],
                    confidence_pct=r["confidence"], price=r["price"],
                    source_page="india_runner", sector=r["sector"],
                    quant_score=r["quant_score"], quant_grade=r["quant_grade"],
                    regime_at_pred=f"india_{regime['trend']}",
                    srs_at_pred=regime["srs"], horizon=r.get("horizon"),
                ):
                    logged += 1
    except Exception:
        pass

    n_features = 0
    try:
        from shared.data_lake import build_scan_feature_row, write_scan_features
        rows = []
        for r in results:
            rows.append(build_scan_feature_row(
                ticker=r["ticker"], sector=r["sector"], price=r["price"],
                chg_1d=r["chg_1d"], ret_3m=r.get("ret_3m"), ret_6m=None,
                ret_12m=None, rsi_14=r["rsi_14"], sma_20=None, sma_50=None,
                sma_200=None, realized_vol_annual=r.get("realized_vol"),
                advanced={}, fundamentals=r.get("_fund", {}),
                quant={"composite_score": r["quant_score"],
                       "composite_grade": r["quant_grade"],
                       "factors": r.get("factors", {})},
                prediction=r.get("_prediction", {}),
                avoidance=r.get("_avoidance", {}),
                regime=f"india_{regime['trend']}", srs=regime["srs"], ts=ts))
        n_features = write_scan_features(rows)
    except Exception:
        pass

    return {"n_scanned": len(results), "n_predicted": logged,
            "n_features": n_features, "regime": regime.get("label")}
