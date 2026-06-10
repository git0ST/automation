"""India swing/positional engine — the portfolio-growth layer for NSE.

Runs the SAME calibrated multi-factor engine as the US scanner (technicals →
quant factors → analyst consensus → vol targeting → risk haircut → empirical
calibration) on the NIFTY 50 universe, with India-native inputs:

  * Fundamentals + analyst consensus: yfinance .info (verified live — P/E, P/B,
    ROE, growth, margins, mean target, recommendation mean from 30+ analysts).
  * Risk regime: India VIX mapped onto the engine's 0-100 systemic-risk scale
    (VIX 10 → ~0, VIX 30 → ~100), so conviction is haircut in stressed tape.
  * Trend regime: NIFTY vs SMA50/200 — used to gate fresh shorts in bull tape
    and label the environment for the feature store.

Shared by streamlit/pages/0_India_Invest.py (interactive) and
projects/daily_digest/agents/india_runner.py (headless daily cron), so the
learning loop accumulates India-specific calibration data every day.
"""
from __future__ import annotations
import sys
import time as _time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT, _ROOT / "streamlit", _ROOT / "projects" / "daily_digest"):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from shared.india_market import NIFTY50

# In-process fundamentals cache (12h) — .info is one HTTP call per name.
_FUND_CACHE: dict = {"ts": 0.0, "data": {}}
_FUND_TTL = 12 * 3600


def india_regime() -> dict:
    """NIFTY trend + India VIX → {trend, vix, srs, label}. srs feeds the
    engine's systemic-risk haircut (0-100)."""
    import yfinance as yf
    out = {"trend": "chop", "vix": None, "srs": 50.0, "label": "—"}
    try:
        h = yf.Ticker("^NSEI").history(period="1y", interval="1d")["Close"]
        px, s50, s200 = float(h.iloc[-1]), float(h[-50:].mean()), float(h[-200:].mean())
        out["trend"] = ("bull" if px > s50 > s200 else
                        "bear" if px < s50 < s200 else "chop")
    except Exception:
        pass
    try:
        v = yf.Ticker("^INDIAVIX").history(period="5d", interval="1d")["Close"]
        vix = float(v.iloc[-1])
        out["vix"] = vix
        out["srs"] = max(0.0, min(100.0, (vix - 10.0) * 5.0))
    except Exception:
        pass
    out["label"] = (f"NIFTY {out['trend'].upper()}"
                    + (f" · VIX {out['vix']:.1f}" if out["vix"] else ""))
    return out


def _fundamentals(tickers: list[str]) -> dict:
    """Threaded yfinance .info fetch, mapped to the quant engine's key names."""
    now = _time.time()
    if _FUND_CACHE["data"] and now - _FUND_CACHE["ts"] < _FUND_TTL:
        return _FUND_CACHE["data"]
    import yfinance as yf
    from concurrent.futures import ThreadPoolExecutor

    def one(tk):
        try:
            i = yf.Ticker(tk).info
            pct = lambda x: x * 100 if isinstance(x, (int, float)) else None
            return tk, {
                "peExclExtraAnnual":    i.get("trailingPE"),
                "pbAnnual":             i.get("priceToBook"),
                "roeTTM":               pct(i.get("returnOnEquity")),
                "revenueGrowthTTMYoy":  pct(i.get("revenueGrowth")),
                "epsGrowthTTMYoy":      pct(i.get("earningsGrowth")),
                "grossMarginTTM":       pct(i.get("grossMargins")),
                "operatingMarginTTM":   pct(i.get("operatingMargins")),
                "priceTargetMean":      i.get("targetMeanPrice"),
                "_rec_mean":            i.get("recommendationMean"),
                "_n_analysts":          i.get("numberOfAnalystOpinions"),
            }
        except Exception:
            return tk, {}

    data = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for tk, d in ex.map(one, tickers):
            data[tk] = d
    _FUND_CACHE.update(ts=now, data=data)
    return data


def _analyst_sig(fund: dict) -> dict:
    """yfinance recommendationMean (1=strong buy … 5=sell) → analyst layer."""
    mean, n = fund.get("_rec_mean"), fund.get("_n_analysts") or 0
    if not mean or n < 3:
        return {"direction": "neutral", "strength": 0.0, "analysts": n}
    score = (3.0 - float(mean)) / 2.0          # +1 strong buy … -1 sell
    direction = ("bullish" if score > 0.15 else
                 "bearish" if score < -0.15 else "neutral")
    return {"direction": direction,
            "strength": min(1.0, abs(score)) * min(1.0, n / 10),
            "analysts": n}


def scan_india(tickers: tuple | None = None) -> tuple[list[dict], dict]:
    """Full positional scan of the India universe → (setups, regime).

    Each setup carries the same fields as the US scanner (direction,
    calibrated confidence, horizon, quant grade, avoidance) plus ₹ levels.
    """
    import numpy as np
    import yfinance as yf
    from _stock_analysis import (technical_signal, composite_prediction,
                                  classify_avoidance)
    from _advanced_technicals import compute_all_technicals
    from _quant_score import compute_quant_score

    tickers = tuple(tickers or NIFTY50.keys())
    regime = india_regime()
    funds = _fundamentals(list(tickers))

    daily = yf.download(list(tickers), period="1y", interval="1d",
                        group_by="ticker", threads=True, progress=False,
                        auto_adjust=True)
    results = []
    for tk in tickers:
        try:
            hist = daily[tk].dropna(subset=["Close"])
            if len(hist) < 60:
                continue
            arr = hist["Close"].to_numpy(dtype=float)
            price = float(arr[-1])

            sma_20  = float(arr[-20:].mean())
            sma_50  = float(arr[-50:].mean())
            sma_200 = float(arr[-200:].mean()) if len(arr) >= 200 else None
            deltas = np.diff(arr[-15:])
            ups = deltas[deltas > 0].sum() if (deltas > 0).any() else 0.0
            downs = -deltas[deltas < 0].sum() if (deltas < 0).any() else 1e-9
            rsi_14 = 100 - 100 / (1 + ups / downs)
            ret_3m  = (arr[-1] / arr[-63] - 1) * 100 if len(arr) >= 63 else None
            ret_6m  = (arr[-1] / arr[-126] - 1) * 100 if len(arr) >= 126 else None
            ret_12m = (arr[-1] / arr[0] - 1) * 100
            logret = np.diff(np.log(arr[-63:]))
            rv = float(np.std(logret, ddof=1) * np.sqrt(252) * 100)

            advanced = compute_all_technicals(hist["High"].to_numpy(),
                                              hist["Low"].to_numpy(), arr,
                                              hist["Volume"].to_numpy())
            tech = technical_signal(price, sma_20, sma_50, sma_200, rsi_14,
                                    advanced=advanced)
            fund = funds.get(tk, {})
            upside = None
            if fund.get("priceTargetMean"):
                upside = (fund["priceTargetMean"] / price - 1) * 100
            quant = compute_quant_score(
                fundamentals=fund,
                momentum_data={"ret_3m": ret_3m, "ret_6m": ret_6m,
                               "ret_12m": ret_12m},
                analyst_data={"eps_revisions_up": None,
                              "eps_revisions_down": None,
                              "target_upside_pct": upside})
            anal = _analyst_sig(fund)

            pred = composite_prediction(
                tech, {"direction": "neutral", "strength": 0}, anal, vol={},
                quant=quant, srs=regime["srs"], realized_vol_annual=rv)

            av = classify_avoidance(direction=pred["direction"],
                                    confidence=pred["confidence"],
                                    quant_score=quant["composite_score"],
                                    quant_grade=quant["composite_grade"],
                                    rsi_14=rsi_14, srs=regime["srs"])
            # Bull-tape discipline: don't short a bull regime on swing horizon
            if regime["trend"] == "bull" and pred["direction"] == "bearish":
                av = {"level": "AVOID", "severity": max(av["severity"], 2),
                      "reasons": av["reasons"] + ["short against NIFTY bull trend"]}

            results.append({
                "ticker": tk, "name": NIFTY50.get(tk, {}).get("name", tk),
                "sector": NIFTY50.get(tk, {}).get("sector", "—"),
                "price": round(price, 1),
                "chg_1d": round((arr[-1] / arr[-2] - 1) * 100, 2),
                "ret_3m": round(ret_3m, 1) if ret_3m is not None else None,
                "rsi_14": round(rsi_14, 1),
                "realized_vol": round(rv, 1),
                "vs_sma_200": (round((price / sma_200 - 1) * 100, 1)
                               if sma_200 else None),
                "direction": pred["direction"],
                "confidence": pred["confidence"],
                "raw_confidence": pred.get("raw_confidence"),
                "horizon": pred.get("horizon"),
                "horizon_label": pred.get("horizon_label"),
                "rationale": pred.get("rationale"),
                "quant_score": quant["composite_score"],
                "quant_grade": quant["composite_grade"],
                "factors": quant["factors"],
                "target_upside": round(upside, 1) if upside is not None else None,
                "n_analysts": anal.get("analysts", 0),
                "avoid_level": av["level"], "avoid_reasons": av["reasons"],
                "_prediction": pred, "_avoidance": av, "_fund": fund,
            })
        except Exception:
            continue
    return results, regime
