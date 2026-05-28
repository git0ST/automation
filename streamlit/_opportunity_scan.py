"""Shared opportunity-scan engine — no page side effects.

Both the Opportunity Scanner page and the Strategies page import `scan_universe`
from here. It must NOT be obtained by exec'ing a page module (that re-runs the
page chrome/widgets inside a cached function → CachedWidgetWarning +
StreamlitDuplicateElementKey). Keeping the scan in a plain importable module
avoids that entirely.
"""
from __future__ import annotations
import sys
from pathlib import Path

# Self-contained path bootstrap so engine + shared modules import regardless of
# which page imports this first.
_HERE = Path(__file__).resolve().parent          # .../streamlit
_ROOT = _HERE.parent                             # repo root
for _p in (_ROOT, _ROOT / "projects" / "daily_digest", _HERE):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import streamlit as st
from _stock_analysis     import (technical_signal, sentiment_signal, analyst_signal,
                                  sector_signal, composite_prediction)
from _advanced_technicals import compute_all_technicals
from _quant_score        import compute_quant_score
from _components         import TICKER_META


@st.cache_data(ttl=600, show_spinner=False)
def _sector_returns_map() -> dict:
    """Pull 5-day sector ETF returns for sector-confirmation signal."""
    try:
        import yfinance as yf
        ETF_MAP = {
            # Information technology
            "Tech": "XLK", "Software": "XLK", "Semis": "XLK",
            # Financials
            "Fin": "XLF", "Bank": "XLF", "Payments": "XLF", "Financials": "XLF",
            "AssetMgmt": "XLF", "Insurance": "XLF",
            # Healthcare
            "Health": "XLV", "Pharma": "XLV", "Biotech": "XLV", "MedTech": "XLV",
            # Energy / materials / utilities / real estate
            "Energy": "XLE", "Materials": "XLB", "Utility": "XLU", "REIT": "XLRE",
            # Consumer
            "Auto": "XLY", "Discretionary": "XLY", "Restaurant": "XLY", "Apparel": "XLY",
            "Retail": "XLP", "Staples": "XLP",
            # Communication
            "Media": "XLC", "Telecom": "XLC",
            # Industrials
            "Industrial": "XLI", "Aerospace": "XLI", "Conglomerate": "XLI",
        }
        returns = {}
        for sector, etf in ETF_MAP.items():
            try:
                hist = yf.Ticker(etf).history(period="10d", auto_adjust=True)
                if len(hist) >= 5:
                    ret = (float(hist["Close"].iloc[-1]) /
                           float(hist["Close"].iloc[-5]) - 1) * 100
                    returns[sector] = ret
            except Exception:
                continue
        return returns
    except Exception:
        return {}


@st.cache_data(ttl=900, show_spinner=False)  # 15 min — scan is expensive
def scan_universe(tickers: tuple, period: str = "1y",
                  regime: str | None = None, srs: float | None = None) -> list[dict]:
    """For each ticker: fetch data, compute prediction + quant score.

    Passes the live regime + systemic-risk score into the prediction engine so
    weighting and conviction are calibrated to the current environment, and
    fuses the quant factor + per-ticker sentiment + realized vol into each call.

    Returns list of dicts with all signals merged.
    """
    import numpy as np
    import yfinance as yf

    try:
        from shared.finnhub_client import (is_available, basic_financials_sync,
                                            recommendations_sync, quote_sync,
                                            normalize_quote)
        finnhub_ready = is_available()
    except ImportError:
        finnhub_ready = False
        basic_financials_sync = recommendations_sync = quote_sync = None

    # Batch-load per-ticker sentiment once (not per-iteration) so the collected
    # news sentiment actually feeds the scanner instead of being thrown away.
    sent_map: dict = {}
    try:
        from _data import load_per_ticker_sentiment
        sent_map = load_per_ticker_sentiment(tuple(tickers)) or {}
    except Exception:
        sent_map = {}

    # Sector ETF momentum map — fetched once, reused across tickers
    sector_returns = _sector_returns_map()

    results = []
    for ticker in tickers:
        try:
            # Historical for momentum + technicals
            hist = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=True)
            if hist.empty or len(hist) < 50:
                continue

            closes = hist["Close"].tolist()
            arr    = np.array(closes)
            price  = float(arr[-1])

            sma_20  = float(arr[-20:].mean())  if len(arr) >= 20  else None
            sma_50  = float(arr[-50:].mean())  if len(arr) >= 50  else None
            sma_200 = float(arr[-200:].mean()) if len(arr) >= 200 else None

            # RSI 14
            deltas = np.diff(arr[-15:])
            ups = deltas[deltas > 0].sum() if any(deltas > 0) else 0
            downs = -deltas[deltas < 0].sum() if any(deltas < 0) else 1e-9
            rs = ups / downs if downs else 0
            rsi_14 = 100 - 100 / (1 + rs) if rs else 50

            # Multi-period returns (momentum factor)
            ret_3m  = (arr[-1] / arr[-63] - 1) * 100  if len(arr) >= 63  else None
            ret_6m  = (arr[-1] / arr[-126] - 1) * 100 if len(arr) >= 126 else None
            ret_12m = (arr[-1] / arr[-252] - 1) * 100 if len(arr) >= 252 else (arr[-1] / arr[0] - 1) * 100

            # Finnhub fundamentals + analyst data
            fin = basic_financials_sync(ticker) if finnhub_ready else {}
            recs = recommendations_sync(ticker) if finnhub_ready else []

            # Build enriched technical signal (uses MACD + BB + ADX + VWAP)
            highs   = hist["High"].values
            lows    = hist["Low"].values
            volumes = hist["Volume"].values
            advanced = compute_all_technicals(highs, lows, arr, volumes)

            tech_sig = technical_signal(price, sma_20, sma_50, sma_200, rsi_14,
                                         advanced=advanced)
            # Real per-ticker news sentiment (was previously fed an empty dict)
            sent_sig = sentiment_signal(sent_map.get(ticker, {}))
            anal_sig = analyst_signal(recs)
            # Sector confirmation signal
            meta_sector = TICKER_META.get(ticker, {}).get("sector", "")
            sect_sig = sector_signal(meta_sector, sector_returns)

            # Realized annualized volatility from the last ~3mo of daily log
            # returns — feeds the engine's volatility-targeting step.
            realized_vol_annual = None
            if len(arr) >= 21:
                logret = np.diff(np.log(arr[-63:])) if len(arr) >= 63 else np.diff(np.log(arr))
                if logret.size > 1:
                    realized_vol_annual = float(np.std(logret, ddof=1) * np.sqrt(252) * 100)

            # Quant factor score — computed BEFORE the prediction so its quality
            # tilt can be fused into the directional call.
            target_upside = None
            if fin and fin.get("priceTargetMean") and fin.get("priceTargetMean") > 0:
                target_upside = (fin["priceTargetMean"] / price - 1) * 100

            quant = compute_quant_score(
                fundamentals=fin,
                momentum_data={"ret_3m": ret_3m, "ret_6m": ret_6m, "ret_12m": ret_12m},
                analyst_data={
                    "eps_revisions_up":   None,
                    "eps_revisions_down": None,
                    "target_upside_pct":  target_upside,
                },
            )

            prediction = composite_prediction(
                tech_sig, sent_sig, anal_sig,
                vol={},                              # realized vol passed directly below
                sector=sect_sig,
                quant=quant,
                regime=regime,
                srs=srs,
                realized_vol_annual=realized_vol_annual,
            )

            chg_1d = (arr[-1] / arr[-2] - 1) * 100 if len(arr) >= 2 else 0
            meta = TICKER_META.get(ticker, {})

            results.append({
                "ticker":      ticker,
                "name":        meta.get("name", ticker),
                "sector":      meta.get("sector", "—"),
                "price":       round(price, 2),
                "chg_1d":      round(chg_1d, 2),
                "ret_3m":      round(ret_3m, 2)  if ret_3m  is not None else None,
                "ret_6m":      round(ret_6m, 2)  if ret_6m  is not None else None,
                "ret_12m":     round(ret_12m, 2) if ret_12m is not None else None,
                "rsi_14":      round(rsi_14, 1),
                "vs_sma_50":   round((price / sma_50  - 1) * 100, 2) if sma_50  else None,
                "vs_sma_200":  round((price / sma_200 - 1) * 100, 2) if sma_200 else None,
                "direction":     prediction["direction"],
                "confidence":    prediction["confidence"],
                "rationale":     prediction["rationale"],
                "components":    prediction["components"],
                "horizon":       prediction.get("horizon"),
                "horizon_label": prediction.get("horizon_label"),
                "quant_score":   quant["composite_score"],
                "quant_grade":   quant["composite_grade"],
                "factors":       quant["factors"],
            })
        except Exception:
            continue
    return results
