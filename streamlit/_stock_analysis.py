"""Single-stock deep-analysis helpers.

Composite prediction model combines:
  1. Technical momentum (SMA crossovers + RSI)
  2. Volatility regime (GARCH forecast)
  3. Sentiment score (per-ticker, time-decayed)
  4. Analyst consensus (Finnhub recommendations)
  5. Insider/options flow signals (from signals table)

Final output: directional bias (bullish/bearish/neutral) + confidence 0-100%.
Confidence drops when signals disagree; rises when they converge.
"""
from __future__ import annotations
import math
from typing import Optional


def technical_signal(price: float, sma_20: float | None, sma_50: float | None,
                     sma_200: float | None, rsi_14: float | None) -> dict:
    """Convert technical readings to directional bias + strength."""
    votes = []  # +1 bullish, -1 bearish, 0 neutral

    # Trend (price vs SMAs)
    if sma_20 and price > sma_20:   votes.append(+1)
    elif sma_20:                     votes.append(-1)
    if sma_50 and price > sma_50:   votes.append(+1)
    elif sma_50:                     votes.append(-1)
    if sma_200 and price > sma_200: votes.append(+1)
    elif sma_200:                    votes.append(-1)

    # Trend strength — Golden Cross (SMA50 > SMA200) is strongly bullish
    if sma_50 and sma_200:
        votes.append(+1 if sma_50 > sma_200 else -1)

    # RSI extremes
    if rsi_14 is not None:
        if rsi_14 > 70:   votes.append(-1)   # overbought → pullback risk
        elif rsi_14 < 30: votes.append(+1)   # oversold → bounce possible
        elif rsi_14 > 55: votes.append(+1)   # momentum bullish
        elif rsi_14 < 45: votes.append(-1)

    if not votes:
        return {"direction": "neutral", "strength": 0.0, "vote_count": 0}

    avg = sum(votes) / len(votes)
    direction = "bullish" if avg > 0.2 else "bearish" if avg < -0.2 else "neutral"
    return {
        "direction": direction,
        "strength":  abs(avg),
        "vote_count": len(votes),
        "raw_avg":   round(avg, 3),
    }


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
                         regime: str | None = None) -> dict:
    """Blend all signals into one directional call + confidence %.

    Weights are loaded from the active model_weights row (regime-aware
    if available, else default). System learns from outcomes and rebalances
    these over time via the Track Record → Model Evolution page.
    """
    # Load learned weights if available, fall back to defaults
    try:
        from shared.learning_loop import load_active_weights
        active = load_active_weights(regime=regime)
        weights = {
            "technical": float(active.get("technical_w") or 0.35),
            "sentiment": float(active.get("sentiment_w") or 0.25),
            "analyst":   float(active.get("analyst_w")   or 0.25),
            "vol":       float(active.get("vol_w")       or 0.15),
        }
    except Exception:
        weights = {"technical": 0.35, "sentiment": 0.25, "analyst": 0.25, "vol": 0.15}

    def to_vote(d):
        if d == "bullish": return +1
        if d == "bearish": return -1
        return 0

    components = []
    if technical.get("strength", 0) > 0:
        components.append(("technical", to_vote(technical["direction"]),
                           technical["strength"], weights["technical"]))
    if sentiment.get("strength", 0) > 0:
        components.append(("sentiment", to_vote(sentiment["direction"]),
                           sentiment["strength"], weights["sentiment"]))
    if analyst.get("strength", 0) > 0:
        components.append(("analyst", to_vote(analyst["direction"]),
                           analyst["strength"], weights["analyst"]))

    if not components:
        return {"direction": "neutral", "confidence": 0,
                "rationale": "No signals available", "components": []}

    # Direction = weighted vote
    weighted_sum = sum(vote * strength * weight for _, vote, strength, weight in components)
    total_weight = sum(weight for _, _, _, weight in components)
    score = weighted_sum / total_weight

    direction = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"

    # Confidence = agreement metric. If all 3 directional signals point same way,
    # confidence is high. If they conflict, confidence drops.
    dirs = [c[1] for c in components if c[1] != 0]
    if not dirs:
        agreement = 0.3
    else:
        same = sum(1 for d in dirs if (d > 0) == (score > 0))
        agreement = same / len(dirs)

    avg_strength = sum(c[2] * c[3] for c in components) / total_weight
    # Confidence is product: agreement × avg strength × signal coverage
    coverage = min(1.0, len(components) / 3)
    confidence = round(agreement * avg_strength * coverage * 100, 1)

    # Vol regime modifier — high vol reduces confidence in directional calls
    vol_regime = vol.get("regime", "normal") if vol else "normal"
    if vol_regime == "elevated":
        confidence *= 0.8

    rationale = _build_rationale(direction, components, vol_regime)

    return {
        "direction":  direction,
        "confidence": round(confidence, 1),
        "score":      round(score, 3),
        "agreement":  round(agreement, 3),
        "vol_regime": vol_regime,
        "rationale":  rationale,
        "components": [
            {"name": n, "direction": "bullish" if v > 0 else "bearish" if v < 0 else "neutral",
             "strength": s, "weight": w}
            for n, v, s, w in components
        ],
    }


def _build_rationale(direction: str, components: list, vol_regime: str) -> str:
    """Plain-English explanation of the prediction."""
    bull_count = sum(1 for _, v, _, _ in components if v > 0)
    bear_count = sum(1 for _, v, _, _ in components if v < 0)
    parts = []
    if direction == "bullish":
        parts.append(f"**{bull_count} of {len(components)}** signals lean bullish.")
    elif direction == "bearish":
        parts.append(f"**{bear_count} of {len(components)}** signals lean bearish.")
    else:
        parts.append("**Signals are mixed** — no clear directional edge.")
    names = [c[0].title() for c in components]
    parts.append(f"Combined: {', '.join(names)}.")
    if vol_regime == "elevated":
        parts.append("⚠ Volatility is elevated — wider stops + smaller position size recommended.")
    elif vol_regime == "compressed":
        parts.append("Volatility is compressed — watch for breakouts in either direction.")
    return " ".join(parts)
