"""Headless opportunity scanner — runs inside the pipeline cron.

Replicates streamlit/pages/6_Opportunities.py:scan_universe() but with
zero Streamlit dependencies. Results are written to opportunity_snapshots
for Streamlit pages to read instantly.

Called from agents/pipeline.py after the main pipeline finishes.
"""
from __future__ import annotations
import os
import math
import uuid
import json
from datetime import datetime, timezone
from typing import Optional


# Default scan universe — 50 diversified S&P names
DEFAULT_UNIVERSE = [
    "NVDA", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "TSLA", "AVGO", "ORCL",
    "AMD", "INTC", "QCOM", "ARM", "SMCI", "TSM", "MU", "MRVL",
    "CRM", "ADBE", "NOW", "PLTR", "CRWD", "PANW", "SHOP",
    "JPM", "GS", "MS", "BAC", "BRK-B", "V", "MA", "BLK",
    "XOM", "CVX", "COP", "SLB",
    "UNH", "LLY", "JNJ", "MRK", "ABBV",
    "WMT", "COST", "HD", "MCD", "DIS", "NFLX",
    "BA", "CAT", "GE", "RTX",
]


# ── Signal evaluators (mirror of streamlit/_stock_analysis.py) ──────────────

def _technical_signal(price: float, sma_20, sma_50, sma_200, rsi_14,
                      macd_cross: str = "neutral", adx_val=None, adx_dir=None,
                      bb_signal: str = "neutral") -> dict:
    """Lightweight tech-signal vote tallying."""
    votes = []
    if sma_20  and price > sma_20:  votes.append(1)
    elif sma_20:                     votes.append(-1)
    if sma_50  and price > sma_50:  votes.append(1)
    elif sma_50:                     votes.append(-1)
    if sma_200 and price > sma_200: votes.append(1)
    elif sma_200:                    votes.append(-1)
    if sma_50 and sma_200:
        votes.append(1 if sma_50 > sma_200 else -1)
    if rsi_14 is not None:
        if rsi_14 > 70:   votes.append(-1)
        elif rsi_14 < 30: votes.append(1)
        elif rsi_14 > 55: votes.append(1)
        elif rsi_14 < 45: votes.append(-1)
    if macd_cross in ("bullish_cross", "bullish_expanding"): votes.append(1)
    elif macd_cross in ("bearish_cross", "bearish_expanding"): votes.append(-1)
    if bb_signal in ("below_lower_band", "near_lower_band"): votes.append(1)
    elif bb_signal in ("above_upper_band", "near_upper_band"): votes.append(-1)
    if adx_val and adx_val > 25 and adx_dir:
        votes.append(1 if adx_dir == "up" else -1)

    if not votes:
        return {"direction": "neutral", "strength": 0.0, "vote_count": 0}
    avg = sum(votes) / len(votes)
    direction = "bullish" if avg > 0.2 else "bearish" if avg < -0.2 else "neutral"
    return {"direction": direction, "strength": abs(avg),
            "vote_count": len(votes), "raw_avg": round(avg, 3)}


def _analyst_signal(recommendations: list) -> dict:
    if not recommendations:
        return {"direction": "neutral", "strength": 0.0, "analysts": 0}
    latest = recommendations[0]
    sb = latest.get("strongBuy", 0); b = latest.get("buy", 0)
    h = latest.get("hold", 0); s = latest.get("sell", 0); ss = latest.get("strongSell", 0)
    total = sb + b + h + s + ss
    if total == 0:
        return {"direction": "neutral", "strength": 0.0, "analysts": 0}
    score = (2 * sb + b - s - 2 * ss) / (2 * total)
    direction = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return {"direction": direction, "strength": min(1.0, abs(score) * 2),
            "analysts": total}


def _composite_prediction(tech: dict, sent: dict, anal: dict, sect: dict) -> dict:
    """Calibrated composite — same formula as streamlit/_stock_analysis."""
    weights = {"technical": 0.35, "sentiment": 0.20, "analyst": 0.20,
               "sector": 0.15, "vol": 0.10}

    def to_vote(d): return 1 if d == "bullish" else -1 if d == "bearish" else 0

    components = []
    for name, sig in [("technical", tech), ("sentiment", sent),
                      ("analyst", anal), ("sector", sect)]:
        if sig.get("strength", 0) > 0:
            components.append((name, to_vote(sig["direction"]),
                                float(sig["strength"]), weights.get(name, 0.1)))

    if not components:
        return {"direction": "neutral", "confidence": 0,
                "rationale": "No signals", "components": []}

    weighted_sum = sum(v * s * w for _, v, s, w in components)
    total_w = sum(w for _, _, _, w in components)
    score = weighted_sum / total_w if total_w else 0
    direction = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"

    dirs = [c[1] for c in components if c[1] != 0]
    agreement = (sum(1 for d in dirs if (d > 0) == (score > 0)) / len(dirs)) if dirs else 0.3
    avg_strength = sum(c[2] * c[3] for c in components) / total_w
    tech_votes = tech.get("vote_count", 0)

    n_signals = len(components)
    base_ceiling = {1: 70, 2: 82, 3: 90, 4: 95}.get(n_signals, 95)
    base_score = agreement * avg_strength
    if tech_votes >= 8:   base_score = min(1.0, base_score * 1.05)
    elif tech_votes >= 6: base_score = min(1.0, base_score * 1.03)
    confidence = min(95, max(0, base_score * base_ceiling))

    return {
        "direction":  direction,
        "confidence": round(confidence, 1),
        "score":      round(score, 3),
        "agreement":  round(agreement, 3),
        "tech_votes": tech_votes,
        "rationale":  _build_rationale(direction, components),
        "components": [
            {"name": n, "direction": "bullish" if v > 0 else "bearish" if v < 0 else "neutral",
             "strength": round(s, 3), "weight": w}
            for n, v, s, w in components
        ],
    }


def _build_rationale(direction: str, components: list) -> str:
    bull = sum(1 for _, v, _, _ in components if v > 0)
    bear = sum(1 for _, v, _, _ in components if v < 0)
    names = [c[0].title() for c in components]
    if direction == "bullish":
        return (f"{bull}/{len(components)} signals lean bullish. "
                f"Sources: {', '.join(names)}.")
    if direction == "bearish":
        return (f"{bear}/{len(components)} signals lean bearish. "
                f"Sources: {', '.join(names)}.")
    return f"Mixed signals across {', '.join(names)}."


# ── Quant scoring (mirror of streamlit/_quant_score.py) ─────────────────────

def _pct_to_grade(pct: float) -> str:
    for thr, grade in [(95, "A+"), (85, "A"), (75, "B+"), (60, "B"),
                        (45, "C+"), (30, "C"), (15, "D")]:
        if pct >= thr: return grade
    return "F"


def _quant_score(fundamentals: dict, ret_3m, ret_6m, ret_12m,
                  target_upside_pct=None) -> dict:
    fin = fundamentals or {}

    # Value (P/E + P/B)
    pe = fin.get("peExclExtraAnnual") or fin.get("peNormalizedAnnual")
    pb = fin.get("pbAnnual")
    v_score = 50.0
    if pe and pe > 0:
        if pe < 10:    v_score += 25
        elif pe < 15:  v_score += 15
        elif pe < 20:  v_score += 8
        elif pe < 30:  pass
        elif pe < 50:  v_score -= 10
        else:           v_score -= 20
    if pb and pb > 0:
        if pb < 1.5:   v_score += 15
        elif pb < 3:   v_score += 8
        elif pb >= 10: v_score -= 15
    v_score = max(0, min(100, v_score))

    # Growth
    rev_g = fin.get("revenueGrowthTTMYoy") or fin.get("revenueGrowth5Y")
    eps_g = fin.get("epsGrowthTTMYoy")     or fin.get("epsGrowth5Y")
    g_score = 50.0
    if rev_g is not None:
        if rev_g > 30: g_score += 25
        elif rev_g > 20: g_score += 18
        elif rev_g > 10: g_score += 10
        elif rev_g > 5:  g_score += 5
        elif rev_g < -10: g_score -= 25
        elif rev_g < 0:   g_score -= 15
    if eps_g is not None:
        if eps_g > 30: g_score += 20
        elif eps_g > 15: g_score += 12
        elif eps_g > 0: g_score += 5
        elif eps_g < -10: g_score -= 15
    g_score = max(0, min(100, g_score))

    # Profitability
    roe = fin.get("roeTTM") or fin.get("roeRfy")
    gm = fin.get("grossMarginTTM")     or fin.get("grossMarginAnnual")
    om = fin.get("operatingMarginTTM") or fin.get("operatingMarginAnnual")
    p_score = 50.0
    if roe is not None:
        if roe > 30: p_score += 25
        elif roe > 20: p_score += 18
        elif roe > 15: p_score += 12
        elif roe > 10: p_score += 6
        elif roe < 0:  p_score -= 20
    if gm is not None:
        if gm > 60: p_score += 12
        elif gm > 40: p_score += 8
        elif gm < 15: p_score -= 8
    if om is not None:
        if om > 25: p_score += 13
        elif om > 15: p_score += 8
        elif om < 0: p_score -= 15
    p_score = max(0, min(100, p_score))

    # Momentum
    m_score = 50.0
    for ret, w in [(ret_12m, 0.30), (ret_6m, 0.40), (ret_3m, 0.30)]:
        if ret is None: continue
        if ret > 50: contrib = 30
        elif ret > 25: contrib = 22
        elif ret > 10: contrib = 12
        elif ret > 0:  contrib = 4
        elif ret > -10: contrib = -8
        elif ret > -25: contrib = -18
        else: contrib = -30
        m_score += contrib * w
    m_score = max(0, min(100, m_score))

    # Revisions / target upside
    r_score = 50.0
    if target_upside_pct is not None:
        if target_upside_pct > 30: r_score += 20
        elif target_upside_pct > 15: r_score += 12
        elif target_upside_pct > 5:  r_score += 6
        elif target_upside_pct < -25: r_score -= 25
        elif target_upside_pct < -10: r_score -= 15
    r_score = max(0, min(100, r_score))

    composite = (v_score * 0.20 + g_score * 0.20 + p_score * 0.20 +
                  m_score * 0.25 + r_score * 0.15)
    return {
        "composite_score": round(composite, 1),
        "composite_grade": _pct_to_grade(composite),
        "factors": {
            "value":     {"score": round(v_score, 1), "grade": _pct_to_grade(v_score)},
            "growth":    {"score": round(g_score, 1), "grade": _pct_to_grade(g_score)},
            "profit":    {"score": round(p_score, 1), "grade": _pct_to_grade(p_score)},
            "momentum":  {"score": round(m_score, 1), "grade": _pct_to_grade(m_score)},
            "revisions": {"score": round(r_score, 1), "grade": _pct_to_grade(r_score)},
        },
    }


# ── Main scan runner ────────────────────────────────────────────────────────

def run_scan(tickers: Optional[list[str]] = None,
             current_regime: Optional[str] = None) -> dict:
    """Run the opportunity scanner across the universe + persist to Supabase.

    Returns: {scan_id, n_scanned, n_written, errors}
    """
    try:
        import yfinance as yf
        import numpy as np
    except ImportError:
        return {"error": "yfinance + numpy required"}

    tickers = tickers or DEFAULT_UNIVERSE
    scan_id = str(uuid.uuid4())
    scanned_at = datetime.now(timezone.utc).isoformat()

    # Optional Finnhub for fundamentals + analyst data
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from shared.finnhub_client import (is_available, basic_financials_sync,
                                            recommendations_sync)
        finnhub_ready = is_available()
    except ImportError:
        finnhub_ready = False

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

            # Fundamentals + analyst (Finnhub)
            fin = basic_financials_sync(ticker) if finnhub_ready else {}
            recs = recommendations_sync(ticker) if finnhub_ready else []

            target_upside = None
            if fin and fin.get("priceTargetMean") and fin["priceTargetMean"] > 0:
                target_upside = (fin["priceTargetMean"] / price - 1) * 100

            tech = _technical_signal(price, sma_20, sma_50, sma_200, rsi_14)
            anal = _analyst_signal(recs)
            pred = _composite_prediction(tech, {}, anal, {})
            quant = _quant_score(fin, ret_3m, ret_6m, ret_12m, target_upside)

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

    # Persist
    written = _write_snapshot(rows)
    return {
        "scan_id":   scan_id,
        "n_scanned": len(rows),
        "n_written": written,
        "errors":    errors,
        "finnhub":   finnhub_ready,
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
