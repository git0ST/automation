"""Composite prediction engine — combines 5 signal layers into one call.

Layers:
  1. Technical — SMA + RSI + (MACD + Bollinger + ADX when available)
  2. Sentiment — per-ticker, credibility-weighted, time-decayed
  3. Analyst — Finnhub recommendations
  4. Sector — sector ETF momentum confirmation
  5. Vol regime — GARCH-derived context modifier

Confidence formula favors signal QUALITY over signal COUNT — a strong
multi-indicator technical signal alone can score high; conflicting
signals drop confidence sharply.
"""
from __future__ import annotations
import math
from typing import Optional


def technical_signal(price: float, sma_20: float | None, sma_50: float | None,
                     sma_200: float | None, rsi_14: float | None,
                     advanced: dict | None = None) -> dict:
    """Convert technical readings to directional bias + strength.

    With `advanced` (MACD/BB/ADX/VWAP), produces 8-12 votes vs basic 4-5.
    Richer signal → less penalty when other layers are silent.
    """
    votes = []
    detail = {}

    # SMA trend votes (4 votes)
    if sma_20 and price > sma_20:   votes.append(+1)
    elif sma_20:                     votes.append(-1)
    if sma_50 and price > sma_50:   votes.append(+1)
    elif sma_50:                     votes.append(-1)
    if sma_200 and price > sma_200: votes.append(+1)
    elif sma_200:                    votes.append(-1)
    if sma_50 and sma_200:
        votes.append(+1 if sma_50 > sma_200 else -1)
        detail["cross"] = "golden" if sma_50 > sma_200 else "death"

    # RSI extremes / momentum (1 vote)
    if rsi_14 is not None:
        if rsi_14 > 70:   votes.append(-1); detail["rsi"] = "overbought"
        elif rsi_14 < 30: votes.append(+1); detail["rsi"] = "oversold"
        elif rsi_14 > 55: votes.append(+1); detail["rsi"] = "bull_momo"
        elif rsi_14 < 45: votes.append(-1); detail["rsi"] = "bear_momo"

    # Advanced technicals — adds up to 4 more votes
    if advanced:
        # MACD crossover (1 vote when cross detected)
        macd_data = advanced.get("macd") or {}
        cross = macd_data.get("cross", "neutral")
        if cross in ("bullish_cross", "bullish_expanding"):
            votes.append(+1); detail["macd"] = cross
        elif cross in ("bearish_cross", "bearish_expanding"):
            votes.append(-1); detail["macd"] = cross

        # Bollinger Bands (1 vote when at extremes)
        bb = advanced.get("bbands") or {}
        bb_sig = bb.get("signal", "neutral")
        if bb_sig in ("below_lower_band", "near_lower_band"):
            votes.append(+1); detail["bb"] = "oversold_band"
        elif bb_sig in ("above_upper_band", "near_upper_band"):
            votes.append(-1); detail["bb"] = "overbought_band"

        # ADX trend strength (1 vote when strong trend)
        adx = advanced.get("adx") or {}
        adx_val = adx.get("adx")
        if adx_val and adx_val > 25:
            votes.append(+1 if adx.get("direction") == "up" else -1)
            detail["adx"] = f"{adx.get('trend', '')}_{adx.get('direction', '')}"

        # VWAP extension (1 vote when extended)
        vwap = advanced.get("vwap") or {}
        v_sig = vwap.get("signal", "neutral")
        if v_sig in ("very_extended_above", "extended_above"):
            votes.append(-1); detail["vwap"] = "extended_above"
        elif v_sig in ("very_extended_below", "extended_below"):
            votes.append(+1); detail["vwap"] = "extended_below"

    if not votes:
        return {"direction": "neutral", "strength": 0.0, "vote_count": 0,
                "detail": detail}

    avg = sum(votes) / len(votes)
    direction = "bullish" if avg > 0.2 else "bearish" if avg < -0.2 else "neutral"
    return {
        "direction":  direction,
        "strength":   abs(avg),
        "vote_count": len(votes),
        "raw_avg":    round(avg, 3),
        "detail":     detail,
    }


def sector_signal(ticker_sector: str | None, sector_returns: dict | None) -> dict:
    """Sector ETF momentum — does the ticker's sector confirm/refute the trade?

    Args:
        ticker_sector: short sector name (Tech, Fin, Energy, etc.)
        sector_returns: {sector_name: 5d_pct} from sector rotation data

    Returns same shape as technical_signal output.
    """
    if not ticker_sector or not sector_returns:
        return {"direction": "neutral", "strength": 0.0, "items": 0}

    # Look up by short or full name — flexible matching
    ret = None
    target_l = ticker_sector.lower()
    for sec, value in sector_returns.items():
        if target_l in sec.lower() or sec.lower() in target_l:
            ret = value
            break
    if ret is None:
        return {"direction": "neutral", "strength": 0.0, "items": 0}

    # Strong sector move → strong signal
    if ret > 2:
        return {"direction": "bullish", "strength": min(1.0, abs(ret) / 4),
                "sector_5d_return": ret}
    if ret < -2:
        return {"direction": "bearish", "strength": min(1.0, abs(ret) / 4),
                "sector_5d_return": ret}
    return {"direction": "neutral", "strength": abs(ret) / 4,
            "sector_5d_return": ret}


def sentiment_signal(sentiment: dict) -> dict:
    """Convert per-ticker sentiment to directional bias."""
    if not sentiment or sentiment.get("n_items", 0) == 0:
        return {"direction": "neutral", "strength": 0.0, "items": 0}

    bull = sentiment.get("bullish_pct", 0)
    bear = sentiment.get("bearish_pct", 0)
    spread = bull - bear   # -100 to +100

    direction = "bullish" if spread > 15 else "bearish" if spread < -15 else "neutral"
    # Strength scales with both spread + sample size
    n = sentiment.get("n_items", 0)
    sample_factor = min(1.0, n / 10)  # 10 articles = full confidence
    strength = min(1.0, abs(spread) / 50) * sample_factor
    return {
        "direction": direction,
        "strength":  round(strength, 3),
        "spread":    spread,
        "items":     n,
    }


def analyst_signal(recommendations: list[dict]) -> dict:
    """Aggregate analyst recommendations to directional bias."""
    if not recommendations:
        return {"direction": "neutral", "strength": 0.0, "analysts": 0}

    latest = recommendations[0]
    strong_buy = latest.get("strongBuy", 0)
    buy        = latest.get("buy", 0)
    hold       = latest.get("hold", 0)
    sell       = latest.get("sell", 0)
    strong_sell = latest.get("strongSell", 0)
    total = strong_buy + buy + hold + sell + strong_sell
    if total == 0:
        return {"direction": "neutral", "strength": 0.0, "analysts": 0}

    # Weighted score: strong actions count 2×
    score = (2 * strong_buy + buy - sell - 2 * strong_sell) / (2 * total)
    direction = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return {
        "direction": direction,
        "strength":  min(1.0, abs(score) * 2),
        "analysts":  total,
        "buy_pct":   round((strong_buy + buy) / total * 100, 1),
        "sell_pct":  round((sell + strong_sell) / total * 100, 1),
        "hold_pct":  round(hold / total * 100, 1),
    }


def vol_signal(garch: dict) -> dict:
    """Convert GARCH forecast to risk regime context."""
    if not garch or "forecast_vol" not in garch:
        return {"regime": "unknown", "annualized_pct": None}
    daily_vol = garch.get("forecast_vol", 0)
    long_run  = garch.get("long_run_vol", daily_vol)
    annual = daily_vol * math.sqrt(252) * 100

    if long_run > 0:
        ratio = daily_vol / long_run
        if ratio > 1.3:    regime = "elevated"
        elif ratio < 0.8:  regime = "compressed"
        else:               regime = "normal"
    else:
        regime = "unknown"
    return {
        "regime":         regime,
        "annualized_pct": round(annual, 2),
        "daily_pct":      round(daily_vol * 100, 3),
        "persistence":    garch.get("persistence"),
    }


def quant_signal(quant: dict | None) -> dict:
    """Turn the 5-factor quant score into a directional quality tilt.

    Quality, value and momentum factors carry forward-return information
    (Fama-French 1993; Novy-Marx 2013 'profitability'; Asness/Frazzini/Pedersen
    'Quality Minus Junk' 2019). A high composite score leans the call bullish,
    a low score bearish — proportional to distance from the neutral midpoint (50).
    Used as a *factor layer* alongside the timing signals, not a replacement.
    """
    if not quant:
        return {"direction": "neutral", "strength": 0.0}
    s = quant.get("composite_score")
    if s is None:
        return {"direction": "neutral", "strength": 0.0}
    dev = (s - 50.0) / 50.0                      # -1 .. +1
    direction = "bullish" if dev > 0.12 else "bearish" if dev < -0.12 else "neutral"
    return {"direction": direction,
            "strength": min(1.0, abs(dev) * 1.4),
            "composite_score": s}


# Annualized vol the engine treats as "normal" conviction. Barroso & Santa-Clara
# (2015, "Momentum has its moments") show scaling exposure to a constant vol
# target sharply improves risk-adjusted returns — we scale CONVICTION likewise.
_TARGET_VOL_ANNUAL = 0.20  # 20% — typical single-name equity baseline


def _vol_modifier(vol: dict | None, realized_vol_annual: float | None) -> tuple[str, float]:
    """Volatility-targeting conviction scalar.

    Returns (regime_label, multiplier). Multiplier > 1 when vol is below target
    (calmer tape → trust the signal more), < 1 when above (noisier → trim).
    Prefers a directly-measured realized vol; falls back to GARCH annualized,
    then to the coarse regime label.
    """
    rv = None
    if realized_vol_annual is not None and realized_vol_annual > 0:
        # accept either a fraction (0.30) or a percent (30.0)
        rv = realized_vol_annual / 100.0 if realized_vol_annual > 3 else float(realized_vol_annual)
    elif vol and vol.get("annualized_pct"):
        rv = float(vol["annualized_pct"]) / 100.0

    if rv and rv > 0:
        mult = (_TARGET_VOL_ANNUAL / rv) ** 0.5         # sqrt damps the scaling
        mult = max(0.70, min(1.10, mult))
        regime = "elevated" if rv > 0.35 else "compressed" if rv < 0.15 else "normal"
        return regime, mult

    regime = vol.get("regime", "normal") if vol else "normal"
    mult = {"elevated": 0.85, "compressed": 1.03}.get(regime, 1.0)
    return regime, mult


def _srs_modifier(srs: float | None, direction: str) -> float:
    """Systemic-Risk-Score conviction haircut.

    High systemic risk (risk-off) compresses conviction across the board and
    penalizes LONGS harder than shorts — mirroring how pro risk desks cut gross
    and net exposure as breadth/credit/vol stress rises.
    """
    if srs is None:
        return 1.0
    try:
        srs = float(srs)
    except (TypeError, ValueError):
        return 1.0
    mult = 1.0 - max(0.0, (srs - 50.0)) / 250.0     # srs 100 → 0.80
    mult += max(0.0, (50.0 - srs)) / 600.0          # srs 0   → +0.083
    mult = max(0.80, min(1.06, mult))
    if srs >= 65 and direction == "bullish":         # risk-off: trim longs extra
        mult *= 0.90
    return mult


def _conf_band(c: float) -> str:
    """Map a confidence value to the same bands used by the v_calibration view."""
    if c >= 80: return "80-100%"
    if c >= 70: return "70-79%"
    if c >= 60: return "60-69%"
    if c >= 50: return "50-59%"
    return "<50%"


def _apply_calibration(direction: str, raw_conf: float) -> tuple[float, str | None]:
    """Re-scale stated confidence toward the empirically observed hit rate.

    Reliability calibration (Platt 1999; isotonic regression) is standard in
    professional probabilistic forecasting: a model that says "70%" should be
    right ~70% of the time. We pull stated confidence toward the realized
    band hit-rate using Bayesian shrinkage — the more settled observations a
    band has, the more we trust the empirical number over the model's prior.
    """
    try:
        from shared.learning_loop import load_calibration_map
        cmap = load_calibration_map()
    except Exception:
        return raw_conf, None
    if not cmap:
        return raw_conf, None

    band = _conf_band(raw_conf)
    entry = cmap.get((band, direction))
    if not entry:
        return raw_conf, None
    hit_rate, n = entry                              # hit_rate in 0..1
    if hit_rate is None or n < 10:                   # too little data to trust
        return raw_conf, None

    K = 40.0                                         # shrinkage strength
    alpha = n / (n + K)                              # n=40 → 0.5, n=120 → 0.75
    calibrated = raw_conf * (1 - alpha) + (hit_rate * 100.0) * alpha
    note = (f"calibrated {raw_conf:.0f}→{calibrated:.0f}% "
            f"(band {band}, n={n}, observed {hit_rate * 100:.0f}%)")
    return calibrated, note


# ── Holding-horizon inference ────────────────────────────────────────────────
# Which signal layer drives the call implies the natural holding period:
# fast technicals/news decay quickly (short); fundamentals/quality persist (long).
_SIGNAL_TENOR = {"technical": 1.0, "sentiment": 1.0, "sector": 2.0,
                 "analyst": 3.0, "quant": 3.0}
_HORIZON_LABEL = {"short": "1–2 weeks", "medium": "3–8 weeks", "long": "3–6 months"}
# Which stored outcome window best scores each horizon (tracker has 1d/7d/30d).
_HORIZON_RETURN_KEY = {"short": "return_7d", "medium": "return_7d", "long": "return_30d"}


def _infer_horizon(components: list, score: float) -> tuple[str, str]:
    """Infer the natural holding horizon from which layers drive the call.

    Only signals AGREEING with the directional call set the tenor, weighted by
    their strength × weight. Technicals/sentiment pull short; analyst/quant
    (fundamentals) pull long; sector is medium.
    """
    num = den = 0.0
    for name, vote, strength, weight in components:
        if vote == 0 or (vote > 0) != (score > 0):
            continue
        w = strength * weight
        num += _SIGNAL_TENOR.get(name, 2.0) * w
        den += w
    if den == 0:
        return "medium", _HORIZON_LABEL["medium"]
    avg = num / den
    horizon = "short" if avg < 1.6 else "medium" if avg < 2.3 else "long"
    return horizon, _HORIZON_LABEL[horizon]


# ── Avoid / Reduce classification (the "where NOT to invest" layer) ───────────

def classify_avoidance(direction: str, confidence: float,
                       quant_score: float | None = None,
                       quant_grade: str | None = None,
                       rsi_14: float | None = None,
                       srs: float | None = None) -> dict:
    """Classify a name as AVOID (don't buy / short candidate), REDUCE
    (trim / handle with caution) or OK, with plain-English reasons.

    Mirrors how risk-aware desks screen OUT names: fade bearish conviction,
    avoid deteriorating fundamentals, don't chase overbought weak names, and
    de-risk fresh longs when the systemic-risk tape is hostile.
    Returns {level, severity, reasons}.
    """
    reasons: list[str] = []
    severity = 0

    if direction == "bearish":
        severity += 2 if confidence >= 60 else 1
        reasons.append(f"Bearish signal ({confidence:.0f}% conf)")

    q_disp = quant_grade or (f"{quant_score:.0f}" if quant_score is not None else "?")
    if quant_grade in ("D", "F") or (quant_score is not None and quant_score < 35):
        severity += 2
        reasons.append(f"Weak fundamentals (quant {q_disp})")
    elif quant_grade in ("C", "C+") or (quant_score is not None and quant_score < 45):
        severity += 1
        reasons.append(f"Below-average fundamentals (quant {q_disp})")

    if rsi_14 is not None and rsi_14 > 75:
        severity += 1
        reasons.append(f"Overbought (RSI {rsi_14:.0f})")

    try:
        if srs is not None and float(srs) >= 65 and direction != "bearish":
            severity += 1
            reasons.append(f"Risk-off tape (SRS {float(srs):.0f})")
    except (TypeError, ValueError):
        pass

    if severity >= 3 or (direction == "bearish" and confidence >= 65):
        level = "AVOID"
    elif severity >= 1:
        level = "REDUCE"
    else:
        level = "OK"
    return {"level": level, "severity": severity, "reasons": reasons}


def composite_prediction(technical: dict, sentiment: dict,
                         analyst: dict, vol: dict,
                         sector: dict | None = None,
                         quant: dict | None = None,
                         regime: str | None = None,
                         srs: float | None = None,
                         realized_vol_annual: float | None = None,
                         calibrate: bool = True) -> dict:
    """Blend every collected signal into one calibrated directional call.

    Pipeline (each step grounded in established practice):
      1. Regime-conditional weights      — signal efficacy varies by regime
                                            (regime-switching models).
      2. Weighted directional vote        — technical + quant factor + analyst
                                            + sentiment + sector.
      3. Agreement × strength → base      — corroboration raises conviction,
                                            disagreement cuts it sharply.
      4. Volatility targeting             — scale conviction inversely to
                                            realized vol (Barroso–Santa-Clara).
      5. Systemic-risk haircut            — trim conviction (esp. longs) when
                                            the SRS flags a risk-off tape.
      6. Empirical calibration            — pull stated confidence toward the
                                            observed band hit-rate (Platt-style).

    All inputs beyond the four core signals are optional and degrade safely.
    """
    # ── 1. Regime-conditional weights ──────────────────────────────────────────
    try:
        from shared.learning_loop import load_active_weights
        active = load_active_weights(regime=regime)
        w_tech = float(active.get("technical_w") or 0.30)
        w_sent = float(active.get("sentiment_w") or 0.15)
        w_anal = float(active.get("analyst_w")   or 0.18)
    except Exception:
        w_tech, w_sent, w_anal = 0.30, 0.15, 0.18

    weights = {
        "technical": w_tech,
        "quant":     0.22,   # fundamental multi-factor alpha (quality/value/mom)
        "analyst":   w_anal,
        "sentiment": w_sent,
        "sector":    0.10,
    }

    q_sig = quant_signal(quant)

    def to_vote(d):
        if d == "bullish": return +1
        if d == "bearish": return -1
        return 0

    # ── 2. Collect contributing directional signals ────────────────────────────
    components = []
    for name, sig in [("technical", technical), ("quant", q_sig),
                      ("analyst", analyst), ("sentiment", sentiment),
                      ("sector", sector or {})]:
        if sig.get("strength", 0) > 0:
            components.append((name, to_vote(sig["direction"]),
                               float(sig["strength"]), weights.get(name, 0.1)))

    if not components:
        return {"direction": "neutral", "confidence": 0,
                "rationale": "No signals available", "components": []}

    weighted_sum = sum(vote * strength * weight for _, vote, strength, weight in components)
    total_weight = sum(weight for _, _, _, weight in components)
    score = weighted_sum / total_weight if total_weight else 0
    direction = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"

    # ── 3. Agreement × strength → base conviction ──────────────────────────────
    dirs = [c[1] for c in components if c[1] != 0]
    if not dirs:
        agreement = 0.3
    else:
        same = sum(1 for d in dirs if (d > 0) == (score > 0))
        agreement = same / len(dirs)

    avg_strength = sum(c[2] * c[3] for c in components) / total_weight
    tech_votes = technical.get("vote_count", 0) if technical else 0

    n_signals = len(components)
    # Ceiling scales with corroboration breadth (1 source caps lower than 5)
    base_ceiling = {1: 68, 2: 80, 3: 88, 4: 93, 5: 96}.get(n_signals, 96)

    base_score = agreement * avg_strength
    if tech_votes >= 8:
        base_score = min(1.0, base_score * 1.05)
    elif tech_votes >= 6:
        base_score = min(1.0, base_score * 1.03)

    confidence = base_score * base_ceiling

    # ── 4. Volatility targeting ────────────────────────────────────────────────
    vol_regime, vol_mult = _vol_modifier(vol, realized_vol_annual)
    confidence *= vol_mult

    # ── 5. Systemic-risk haircut ───────────────────────────────────────────────
    srs_mult = _srs_modifier(srs, direction)
    confidence *= srs_mult

    confidence = max(0, min(96, confidence))
    raw_confidence = confidence

    # ── 6. Empirical calibration ───────────────────────────────────────────────
    cal_note = None
    if calibrate and direction != "neutral":
        confidence, cal_note = _apply_calibration(direction, confidence)

    confidence = max(0, min(97, confidence))

    # Holding horizon implied by the dominant signal layers
    horizon, horizon_label = _infer_horizon(components, score)

    rationale = _build_rationale(direction, components, vol_regime, tech_votes,
                                 srs=srs, regime=regime, cal_note=cal_note)

    return {
        "direction":      direction,
        "confidence":     round(confidence, 1),
        "raw_confidence": round(raw_confidence, 1),
        "score":          round(score, 3),
        "agreement":      round(agreement, 3),
        "vol_regime":     vol_regime,
        "vol_mult":       round(vol_mult, 3),
        "srs_mult":       round(srs_mult, 3),
        "regime":         regime,
        "horizon":        horizon,
        "horizon_label":  horizon_label,
        "tech_votes":     tech_votes,
        "rationale":      rationale,
        "calibration":    cal_note,
        "components": [
            {"name": n, "direction": "bullish" if v > 0 else "bearish" if v < 0 else "neutral",
             "strength": round(s, 3), "weight": round(w, 3)}
            for n, v, s, w in components
        ],
    }


def _build_rationale(direction: str, components: list, vol_regime: str,
                     tech_votes: int = 0, srs: float | None = None,
                     regime: str | None = None, cal_note: str | None = None) -> str:
    """Plain-English explanation of the prediction."""
    bull = sum(1 for _, v, _, _ in components if v > 0)
    bear = sum(1 for _, v, _, _ in components if v < 0)
    parts = []
    if direction == "bullish":
        parts.append(f"**{bull} of {len(components)}** contributing signals lean bullish.")
    elif direction == "bearish":
        parts.append(f"**{bear} of {len(components)}** contributing signals lean bearish.")
    else:
        parts.append("**Signals mixed** — no directional edge.")
    names = [c[0].title() for c in components]
    parts.append(f"Sources: {', '.join(names)}.")
    if regime:
        parts.append(f"Weights tuned for **{regime}** regime.")
    if tech_votes >= 8:
        parts.append(f"Technical layer is rich ({tech_votes} indicators agree-direction).")
    if vol_regime == "elevated":
        parts.append("⚠ Elevated vol — conviction trimmed, wider stops + smaller size.")
    elif vol_regime == "compressed":
        parts.append("Vol compressed — watch for breakouts.")
    if srs is not None:
        try:
            if float(srs) >= 65:
                parts.append(f"⚠ Systemic risk high (SRS {float(srs):.0f}) — "
                             f"conviction haircut applied{'; longs penalized' if direction == 'bullish' else ''}.")
        except (TypeError, ValueError):
            pass
    if cal_note:
        parts.append(f"📐 {cal_note}.")
    return " ".join(parts)
