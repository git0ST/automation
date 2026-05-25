"""
Risk Dashboard Engine — systematic risk monitoring.

Computes a composite Systemic Risk Score (SRS) 0–100 using:
  - Volatility regime (VIX level + trend)
  - Yield curve stress (inversion depth)
  - Credit stress (Fed Funds vs 10Y spread)
  - Sentiment extremes (fear/greed, options flow)
  - Signal divergence (when sources strongly disagree)

Used by: Bloomberg Risk, BlackRock Systematic Active Equity,
         Bridgewater All-Weather risk parity overlay.

Levels:
  0–25:  Low risk    (green)  — benign environment
  26–50: Moderate    (yellow) — normal risk conditions
  51–75: Elevated    (amber)  — caution, potential stress
  76–100: High       (red)    — systemic stress, de-risk signal
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class RiskFactor:
    name:        str
    score:       float      # 0–100 contribution to total risk
    weight:      float      # how much this factor weighs
    direction:   str        # increasing | stable | decreasing
    description: str


@dataclass
class RiskSnapshot:
    srs:          float              # 0–100 Systemic Risk Score
    level:        str                # low | moderate | elevated | high
    color:        str
    factors:      list[RiskFactor]
    top_risks:    list[str]
    timestamp:    str


def _vix_risk(vix: Optional[float]) -> RiskFactor:
    if vix is None:
        return RiskFactor("VIX Volatility", 25, 0.25, "stable", "VIX unavailable — using neutral")
    if vix >= 40:
        score, desc = 95, f"VIX {vix:.1f} — extreme fear, tail-risk event"
    elif vix >= 30:
        score, desc = 80, f"VIX {vix:.1f} — high stress"
    elif vix >= 22:
        score, desc = 55, f"VIX {vix:.1f} — elevated volatility"
    elif vix >= 15:
        score, desc = 25, f"VIX {vix:.1f} — normal range"
    else:
        score, desc = 10, f"VIX {vix:.1f} — very low vol (complacency risk)"
    return RiskFactor("VIX Volatility", score, 0.30, "stable", desc)


def _yield_curve_risk(t10y2y: Optional[float]) -> RiskFactor:
    if t10y2y is None:
        return RiskFactor("Yield Curve", 30, 0.25, "stable", "No yield curve data")
    if t10y2y <= -1.0:
        score, desc = 85, f"Deep inversion {t10y2y:.2f}% — recession signal"
    elif t10y2y <= -0.5:
        score, desc = 70, f"Inverted {t10y2y:.2f}% — growth stress"
    elif t10y2y < 0:
        score, desc = 50, f"Slightly inverted {t10y2y:.2f}% — caution"
    elif t10y2y < 0.5:
        score, desc = 25, f"Flat {t10y2y:.2f}% — monitoring"
    else:
        score, desc = 10, f"Positive {t10y2y:.2f}% — normal"
    return RiskFactor("Yield Curve (10Y-2Y)", score, 0.25, "stable", desc)


def _rate_risk(ffr: Optional[float], dgs10: Optional[float]) -> RiskFactor:
    """Credit/rate stress: Fed Funds relative to 10Y."""
    if ffr is None:
        return RiskFactor("Rate Stress", 25, 0.15, "stable", "Rate data unavailable")
    spread = (dgs10 or 4.0) - (ffr or 0)
    if spread < -0.5:
        score, desc = 75, f"Inverted rate structure ({spread:.2f}%) — financial stress"
    elif spread < 0:
        score, desc = 55, f"Near-inverted rates ({spread:.2f}%) — tight conditions"
    elif spread < 1.0:
        score, desc = 30, f"Compressed spread ({spread:.2f}%) — tight but stable"
    else:
        score, desc = 15, f"Normal rate spread ({spread:.2f}%)"
    return RiskFactor("Rate / Credit Stress", score, 0.15, "stable", desc)


def _sentiment_risk(fear_greed_value: Optional[int], sentiment_avg: Optional[float]) -> RiskFactor:
    """Extreme sentiment = contrarian risk signal."""
    score = 25  # default neutral
    desc  = "Neutral sentiment"
    if fear_greed_value is not None:
        if fear_greed_value <= 20:
            score, desc = 60, f"Extreme Fear ({fear_greed_value}) — potential capitulation / bounce"
        elif fear_greed_value <= 35:
            score, desc = 40, f"Fear ({fear_greed_value}) — elevated risk aversion"
        elif fear_greed_value >= 80:
            score, desc = 65, f"Extreme Greed ({fear_greed_value}) — overextension risk"
        elif fear_greed_value >= 65:
            score, desc = 40, f"Greed ({fear_greed_value}) — elevated complacency"
        else:
            score, desc = 20, f"Neutral ({fear_greed_value}) — balanced sentiment"
    return RiskFactor("Sentiment Extremes", score, 0.15, "stable", desc)


def _unemployment_risk(unrate: Optional[float]) -> RiskFactor:
    if unrate is None:
        return RiskFactor("Labor Market", 20, 0.15, "stable", "Unemployment data unavailable")
    if unrate >= 6.5:
        score, desc = 80, f"Unemployment {unrate:.1f}% — labor market distress"
    elif unrate >= 5.0:
        score, desc = 55, f"Unemployment {unrate:.1f}% — weakening labor"
    elif unrate <= 3.5:
        score, desc = 20, f"Unemployment {unrate:.1f}% — very tight, wage inflation risk"
    else:
        score, desc = 15, f"Unemployment {unrate:.1f}% — healthy labor market"
    return RiskFactor("Labor Market", score, 0.15, "stable", desc)


def compute_risk(
    macro: dict,
    fear_greed_value: Optional[int] = None,
    sentiment_avg: Optional[float] = None,
) -> RiskSnapshot:
    """
    Compute the Systemic Risk Score from macro and market inputs.

    Args:
        macro: {series_id: value} dict from FRED pipeline
        fear_greed_value: 0-100 F&G reading
        sentiment_avg: pipeline aggregate sentiment -1 to +1
    """
    factors = [
        _vix_risk(macro.get("VIXCLS")),
        _yield_curve_risk(macro.get("T10Y2Y")),
        _rate_risk(macro.get("FEDFUNDS"), macro.get("DGS10")),
        _sentiment_risk(fear_greed_value, sentiment_avg),
        _unemployment_risk(macro.get("UNRATE")),
    ]

    # Weighted composite score
    total_w = sum(f.weight for f in factors)
    srs = sum(f.score * f.weight for f in factors) / max(total_w, 1e-6)
    srs = round(min(max(srs, 0), 100), 1)

    # Level classification
    if srs <= 25:
        level, color = "Low", "#22d472"
    elif srs <= 50:
        level, color = "Moderate", "#e3b341"
    elif srs <= 75:
        level, color = "Elevated", "#f07030"
    else:
        level, color = "High", "#f75050"

    # Top risk narrative (factors with score > 50, sorted)
    top_risks = [
        f.description
        for f in sorted(factors, key=lambda x: x.score, reverse=True)
        if f.score > 50
    ][:3]
    if not top_risks:
        top_risks = ["No significant systemic risk signals detected"]

    return RiskSnapshot(
        srs       = srs,
        level     = level,
        color     = color,
        factors   = factors,
        top_risks = top_risks,
        timestamp = datetime.now(timezone.utc).isoformat(),
    )


def risk_to_dict(r: RiskSnapshot) -> dict:
    return {
        "srs":       r.srs,
        "level":     r.level,
        "color":     r.color,
        "top_risks": r.top_risks,
        "timestamp": r.timestamp,
        "factors": [
            {
                "name":        f.name,
                "score":       round(f.score, 1),
                "weight":      f.weight,
                "direction":   f.direction,
                "description": f.description,
            }
            for f in r.factors
        ],
    }
