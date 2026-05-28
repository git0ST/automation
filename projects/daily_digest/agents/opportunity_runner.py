"""Headless opportunity scanner — runs inside the pipeline cron.

Calls the SAME calibrated prediction engine as the live Streamlit scanner
(streamlit/_stock_analysis.py + _quant_score.py + _advanced_technicals.py) so
the instant snapshot users see is identical in quality to a live scan. Results
are written to opportunity_snapshots for Streamlit pages to read instantly.

Called from agents/pipeline.py after the main pipeline finishes.
"""
from __future__ import annotations
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional


# ── Make the shared engine importable headless ──────────────────────────────
# At cron runtime the repo ROOT and projects/daily_digest are on sys.path; the
# prediction engine lives in ROOT/streamlit. Walk up to the repo root (the dir
# containing both `streamlit` and `shared`) and add ROOT + ROOT/streamlit.
def _ensure_engine_on_path() -> None:
    here = os.path.abspath(__file__)
    root = here
    for _ in range(6):
        root = os.path.dirname(root)
        if (os.path.isdir(os.path.join(root, "streamlit")) and
                os.path.isdir(os.path.join(root, "shared"))):
            break
    for p in (root, os.path.join(root, "streamlit")):
        if p not in sys.path:
            sys.path.insert(0, p)


_ensure_engine_on_path()

# Single source of truth for the universe (shared with the live scanner)
try:
    from shared.scan_universe import SCAN_UNIVERSE as DEFAULT_UNIVERSE
except Exception:
    DEFAULT_UNIVERSE = [
        "NVDA", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "TSLA", "AVGO", "ORCL",
        "AMD", "INTC", "QCOM", "TSM", "JPM", "V", "MA", "XOM", "CVX",
        "UNH", "LLY", "JNJ", "WMT", "COST", "HD", "BA", "CAT",
    ]


# ── Main scan runner ────────────────────────────────────────────────────────

def run_scan(tickers: Optional[list[str]] = None,
             current_regime: Optional[str] = None,
             current_srs: Optional[float] = None) -> dict:
    """Run the opportunity scanner across the universe + persist to Supabase.

    Uses the production prediction engine: advanced technicals (MACD/BB/ADX/VWAP),
    the 5-factor quant score fused as a quality tilt, volatility targeting,
    a systemic-risk conviction haircut, regime-conditional weights, and empirical
    calibration — exactly what the live Streamlit scanner runs.

    Returns: {scan_id, n_scanned, n_written, errors}
    """
    try:
        import yfinance as yf
        import numpy as np
    except ImportError:
        return {"error": "yfinance + numpy required"}

    # Production engine (no Streamlit dependency in these modules)
    try:
        from _stock_analysis import (technical_signal, analyst_signal,
                                      composite_prediction)
        from _quant_score import compute_quant_score
        from _advanced_technicals import compute_all_technicals
    except Exception as e:
        return {"error": f"engine import failed: {e}"}

    tickers = tickers or DEFAULT_UNIVERSE
    scan_id = str(uuid.uuid4())
    scanned_at = datetime.now(timezone.utc).isoformat()

    # Optional Finnhub for fundamentals + analyst data
    try:
        from shared.finnhub_client import (is_available, basic_financials_sync,
                                            recommendations_sync)
        finnhub_ready = is_available()
    except ImportError:
        finnhub_ready = False
        basic_financials_sync = recommendations_sync = None

    # Strategy engine import (optional)
    try:
        from shared.strategy_engine_lite import find_strategies_for_setup
        strategy_finder = find_strategies_for_setup
    except ImportError:
        strategy_finder = None

    rows = []
    errors = 0
    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(period="1y", auto_adjust=True)
            if hist.empty or len(hist) < 50:
                continue

            closes = hist["Close"].tolist()
            arr    = np.array(closes)
            price  = float(arr[-1])
            chg_1d = ((arr[-1] / arr[-2] - 1) * 100) if len(arr) >= 2 else 0

            sma_20  = float(arr[-20:].mean())  if len(arr) >= 20  else None
            sma_50  = float(arr[-50:].mean())  if len(arr) >= 50  else None
            sma_200 = float(arr[-200:].mean()) if len(arr) >= 200 else None

            # RSI 14
            deltas = np.diff(arr[-15:])
            ups = deltas[deltas > 0].sum() if any(deltas > 0) else 0
            downs = -deltas[deltas < 0].sum() if any(deltas < 0) else 1e-9
            rs = ups / downs if downs else 0
            rsi_14 = float(100 - 100 / (1 + rs)) if rs else 50

            ret_3m  = float((arr[-1] / arr[-63] - 1) * 100)  if len(arr) >= 63  else None
            ret_6m  = float((arr[-1] / arr[-126] - 1) * 100) if len(arr) >= 126 else None
            ret_12m = float((arr[-1] / arr[-252] - 1) * 100) if len(arr) >= 252 else float((arr[-1] / arr[0] - 1) * 100)

            # Realized annualized vol (last ~3mo daily log returns) for vol targeting
            realized_vol_annual = None
            if len(arr) >= 21:
                logret = np.diff(np.log(arr[-63:])) if len(arr) >= 63 else np.diff(np.log(arr))
                if logret.size > 1:
                    realized_vol_annual = float(np.std(logret, ddof=1) * np.sqrt(252) * 100)

            # Fundamentals + analyst (Finnhub)
            fin = basic_financials_sync(ticker) if finnhub_ready else {}
            recs = recommendations_sync(ticker) if finnhub_ready else []

            target_upside = None
            if fin and fin.get("priceTargetMean") and fin["priceTargetMean"] > 0:
                target_upside = (fin["priceTargetMean"] / price - 1) * 100

            # Advanced technicals → rich 8-12 vote technical signal (parity w/ live)
            advanced = compute_all_technicals(hist["High"].values, hist["Low"].values,
                                              arr, hist["Volume"].values)
            tech = technical_signal(price, sma_20, sma_50, sma_200, rsi_14,
                                    advanced=advanced)
            anal = analyst_signal(recs)

            # Quant factor score — computed before the prediction so it can be fused
            quant = compute_quant_score(
                fundamentals=fin,
                momentum_data={"ret_3m": ret_3m, "ret_6m": ret_6m, "ret_12m": ret_12m},
                analyst_data={"eps_revisions_up": None, "eps_revisions_down": None,
                              "target_upside_pct": target_upside},
            )

            pred = composite_prediction(
                tech, {}, anal, vol={},
                quant=quant,
                regime=current_regime,
                srs=current_srs,
                realized_vol_annual=realized_vol_annual,
            )

            strategies = []
            if strategy_finder:
                try:
                    strategies = strategy_finder({
                        "composite_quant":    quant["composite_score"],
                        "quant_grade":        quant["composite_grade"],
                        "value_grade":        quant["factors"]["value"]["grade"],
                        "growth_grade":       quant["factors"]["growth"]["grade"],
                        "profit_grade":       quant["factors"]["profit"]["grade"],
                        "momentum_grade":     quant["factors"]["momentum"]["grade"],
                        "technical_direction": pred["direction"],
                        "rsi":                rsi_14,
                        "above_sma_200":      sma_200 is not None and price > sma_200,
                        "below_sma_200":      sma_200 is not None and price < sma_200,
                        "confidence":         pred["confidence"],
                    })
                except Exception:
                    pass

            rows.append({
                "scan_id":    scan_id,
                "ticker":     ticker,
                "price":      round(price, 2),
                "chg_1d":     round(chg_1d, 2),
                "ret_3m":     round(ret_3m, 2)  if ret_3m  is not None else None,
                "ret_6m":     round(ret_6m, 2)  if ret_6m  is not None else None,
                "ret_12m":    round(ret_12m, 2) if ret_12m is not None else None,
                "rsi_14":     round(rsi_14, 1),
                "vs_sma_50":  round((price / sma_50 - 1)  * 100, 2) if sma_50  else None,
                "vs_sma_200": round((price / sma_200 - 1) * 100, 2) if sma_200 else None,
                "direction":  pred["direction"],
                "confidence": pred["confidence"],
                "rationale":  pred.get("rationale"),
                "components": pred.get("components"),
                "tech_votes": pred.get("tech_votes"),
                "quant_score": quant["composite_score"],
                "quant_grade": quant["composite_grade"],
                "factors":     quant["factors"],
                "strategies":  [{"name": s.get("name"),
                                  "horizon": s.get("horizon"),
                                  "direction": s.get("direction")} for s in strategies],
                "regime_at_scan": current_regime,
                "scanned_at":   scanned_at,
            })
        except Exception:
            errors += 1
            continue

    # Persist the snapshot for instant Streamlit reads
    written = _write_snapshot(rows)

    # Log high-conviction, directional setups to the predictions table so the
    # full 99-ticker scan feeds the self-improvement loop (each gets correlated
    # with realized returns and calibrated over time). This is the system's
    # richest, most consistent prediction source — ~3 logged snapshots/day.
    logged = 0
    try:
        from shared.prediction_tracker import log_prediction
        for r in rows:
            if (r.get("confidence") or 0) >= 55 and r.get("direction") not in (None, "neutral"):
                if log_prediction(
                    ticker=r["ticker"],
                    direction=r["direction"],
                    confidence_pct=r["confidence"],
                    price=r["price"],
                    source_page="opportunity_runner",
                    components=r.get("components"),
                    quant_score=r.get("quant_score"),
                    quant_grade=r.get("quant_grade"),
                    regime_at_pred=current_regime,
                    srs_at_pred=current_srs,
                ):
                    logged += 1
    except Exception:
        pass

    return {
        "scan_id":     scan_id,
        "n_scanned":   len(rows),
        "n_written":   written,
        "n_predicted": logged,
        "errors":      errors,
        "finnhub":     finnhub_ready,
    }


def _write_snapshot(rows: list[dict]) -> int:
    if not rows:
        return 0
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        return 0
    try:
        from supabase import create_client
        client = create_client(url, key)
        # Insert in batches of 50
        written = 0
        for i in range(0, len(rows), 50):
            batch = rows[i:i + 50]
            try:
                client.table("opportunity_snapshots").insert(batch).execute()
                written += len(batch)
            except Exception as e:
                print(f"[opportunity_snapshots] batch error: {e}")
        return written
    except Exception:
        return 0
