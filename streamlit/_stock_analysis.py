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


def composite_prediction(technical: dict, sentiment: dict,
                         analyst: dict, vol: dict,
                         sector: dict | None = None,
                         regime: str | None = None) -> dict:
    """Blend signals into one directional call + confidence %.

    Confidence formula (new):
        confidence = agreement × signal_strength × coverage_bonus
    Where:
        agreement       = % of contributing signals that point same way (0-1)
        signal_strength = weighted strength × signal richness factor
        coverage_bonus  = 1.0 + 0.10 × (n_signals - 1), capped at 1.30

    Coverage now ADDS confidence (corroboration bonus) rather than
    subtracting it — a single strong multi-indicator signal can score
    high if it's high quality, while disagreeing signals always reduce
    confidence sharply.
    """
    # Load learned weights (regime-aware if available)
    try:
        from shared.learning_loop import load_active_weights
        active = load_active_weights(regime=regime)
        weights = {
            "technical": float(active.get("technical_w") or 0.35),
            "sentiment": float(active.get("sentiment_w") or 0.25),
            "analyst":   float(active.get("analyst_w")   or 0.25),
            "sector":    0.15,
            "vol":       float(active.get("vol_w")       or 0.10),
        }
    except Exception:
        weights = {"technical": 0.35, "sentiment": 0.20, "analyst": 0.20,
                   "sector": 0.15, "vol": 0.10}

    def to_vote(d):
        if d == "bullish": return +1
        if d == "bearish": return -1
        return 0

    # Collect contributing signals
    components = []
    for name, sig in [("technical", technical), ("sentiment", sentiment),
                      ("analyst", analyst), ("sector", sector or {})]:
        if sig.get("strength", 0) > 0:
            components.append((name, to_vote(sig["direction"]),
                               float(sig["strength"]), weights.get(name, 0.1)))

    if not components:
        return {"direction": "neutral", "confidence": 0,
                "rationale": "No signals available", "components": []}

    # Direction = weighted sum
    weighted_sum = sum(vote * strength * weight for _, vote, strength, weight in components)
    total_weight = sum(weight for _, _, _, weight in components)
    score = weighted_sum / total_weight if total_weight else 0
    direction = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"

    # Agreement: % of components voting same direction as overall score
    dirs = [c[1] for c in components if c[1] != 0]
    if not dirs:
        agreement = 0.3
    else:
        same = sum(1 for d in dirs if (d > 0) == (score > 0))
        agreement = same / len(dirs)

    # Signal strength (raw weighted average, capped at 0.9 for single signal)
    avg_strength = sum(c[2] * c[3] for c in components) / total_weight
    tech_votes = technical.get("vote_count", 0) if technical else 0

    # Calibrated confidence — base confidence comes from agreement × strength,
    # corroboration bonus tops it up only when multiple signal types align.
    n_signals = len(components)

    # Base ceiling per signal count: single=70, two=82, three=90, four=95
    base_ceiling = {1: 70, 2: 82, 3: 90, 4: 95}.get(n_signals, 95)

    # Score: agreement × strength gives a 0-1 value
    base_score = agreement * avg_strength

    # Technical richness modifier — multi-indicator tech (8+ votes) deserves
    # a small lift, but capped so it can't single-handedly hit 95%+
    if tech_votes >= 8:
        base_score = min(1.0, base_score * 1.05)
    elif tech_votes >= 6:
        base_score = min(1.0, base_score * 1.03)

    confidence = base_score * base_ceiling

    # Vol regime modifier
    vol_regime = vol.get("regime", "normal") if vol else "normal"
    if vol_regime == "elevated":
        confidence *= 0.85
    elif vol_regime == "compressed":
        confidence *= 1.03

    confidence = max(0, min(95, confidence))

    rationale = _build_rationale(direction, components, vol_regime, tech_votes)

    return {
        "direction":   direction,
        "confidence":  round(confidence, 1),
        "score":       round(score, 3),
        "agreement":   round(agreement, 3),
        "vol_regime":  vol_regime,
        "tech_votes":  tech_votes,
        "rationale":   rationale,
        "components": [
            {"name": n, "direction": "bullish" if v > 0 else "bearish" if v < 0 else "neutral",
             "strength": round(s, 3), "weight": w}
            for n, v, s, w in components
        ],
    }


def _build_rationale(direction: str, components: list, vol_regime: str,
                     tech_votes: int = 0) -> str:
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
    if tech_votes >= 8:
        parts.append(f"Technical layer is rich ({tech_votes} indicators agree-direction).")
    if vol_regime == "elevated":
        parts.append("⚠ Elevated vol — wider stops + smaller position.")
    elif vol_regime == "compressed":
        parts.append("Vol compressed — watch for breakouts.")
    return " ".join(parts)
