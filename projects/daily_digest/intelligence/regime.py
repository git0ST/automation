"""
Market Regime Detection Engine — BlackRock Aladdin-inspired.

BlackRock's regime framework classifies markets into four quadrants
based on the Growth / Inflation axes — a technique developed over 30+
years of factor research and embedded into the $21T Aladdin platform.

Quadrants:
  GOLDILOCKS   — Growth↑  Inflation↓  (risk-on, equities, tech)
  REFLATION    — Growth↑  Inflation↑  (late cycle, commodities, financials)
  STAGFLATION  — Growth↓  Inflation↑  (real assets, gold, defensive)
  DEFLATION    — Growth↓  Inflation↓  (recession, bonds, cash)

Inputs (all from FRED — free, no key):
  Growth  axis: 10Y-2Y yield spread, unemployment trend, VIX trend
  Inflation ax: CPI YoY proxy, Fed Funds Rate trajectory
  Risk overlay: VIX absolute level, options flow sentiment

Confidence scoring:
  Each signal votes ±1 on growth and inflation axes.
  Confidence = convergence of signals (0–100%).
  High confidence ≥ 70 % (≥ 3 signals agree on both axes).

Reference:
  BlackRock Investment Institute — Regime-Based Asset Allocation (2022)
  https://www.blackrock.com/institutions/en-axj/insights/bii-systematic-factors
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# ── Regime definitions ────────────────────────────────────────────────────────

REGIMES = {
    "goldilocks":  {
        "label":       "Goldilocks",
        "color":       "#22d472",
        "description": "High growth, low inflation — risk-on. Favour equities, tech, growth assets.",
        "favors":      ["Equities", "Tech", "Small-cap", "EM"],
        "avoids":      ["Bonds", "Gold", "Cash"],
    },
    "reflation":   {
        "label":       "Reflation",
        "color":       "#e8a435",
        "description": "High growth, high inflation — late cycle. Favour commodities, financials, real assets.",
        "favors":      ["Commodities", "Financials", "Energy", "TIPS"],
        "avoids":      ["Long-duration bonds", "High-P/E growth"],
    },
    "stagflation": {
        "label":       "Stagflation",
        "color":       "#f75050",
        "description": "Low growth, high inflation — risk-off. Favour gold, real assets, short duration.",
        "favors":      ["Gold", "Commodities", "Real estate", "Defensive"],
        "avoids":      ["Equities", "High-yield credit", "Tech"],
    },
    "deflation":   {
        "label":       "Deflation / Recession",
        "color":       "#4da6ff",
        "description": "Low growth, low inflation — recession risk. Favour bonds, cash, quality.",
        "favors":      ["Long Treasuries", "Cash", "Quality stocks", "USD"],
        "avoids":      ["Cyclicals", "Commodities", "EM"],
    },
}

# ── Signal definitions ─────────────────────────────────────────────────────────

@dataclass
class MacroSignal:
    name: str
    value: float
    growth_vote:    int   # +1 = growth bullish, -1 = growth bearish, 0 = neutral
    inflation_vote: int   # +1 = inflation up,   -1 = inflation down,  0 = neutral
    confidence:     float # 0–1 how reliable this reading is
    description:    str


@dataclass
class RegimeReading:
    regime:          str                 # goldilocks | reflation | stagflation | deflation
    confidence_pct:  float               # 0–100
    growth_score:    float               # -1 to +1
    inflation_score: float               # -1 to +1
    signals:         list[MacroSignal] = field(default_factory=list)
    transition_risk: str = "low"         # low | medium | high
    timestamp:       str = ""
    # Asset allocation implications
    favors:          list[str] = field(default_factory=list)
    avoids:          list[str] = field(default_factory=list)
    label:           str = ""
    color:           str = "#888"
    description:     str = ""


# ── Signal classifiers ────────────────────────────────────────────────────────

def _yield_curve_signal(t10y2y: Optional[float]) -> MacroSignal:
    """10Y-2Y spread. Inverted curve = recession signal."""
    if t10y2y is None:
        return MacroSignal("Yield Curve", 0, 0, 0, 0.0, "No data")
    if t10y2y <= -0.5:
        return MacroSignal("Yield Curve (10Y-2Y)", t10y2y, -1, 0, 0.9,
                           f"Deeply inverted at {t10y2y:.2f}% — strong recession signal")
    if t10y2y < 0:
        return MacroSignal("Yield Curve (10Y-2Y)", t10y2y, -1, 0, 0.7,
                           f"Inverted at {t10y2y:.2f}% — growth concern")
    if t10y2y < 0.5:
        return MacroSignal("Yield Curve (10Y-2Y)", t10y2y, 0, 0, 0.4,
                           f"Flat at {t10y2y:.2f}% — neutral")
    return MacroSignal("Yield Curve (10Y-2Y)", t10y2y, +1, 0, 0.7,
                       f"Positive at {t10y2y:.2f}% — growth-supportive")


def _vix_signal(vix: Optional[float]) -> MacroSignal:
    """VIX. High VIX = risk-off, low VIX = complacency / risk-on."""
    if vix is None:
        return MacroSignal("VIX", 0, 0, 0, 0.0, "No data")
    if vix >= 35:
        return MacroSignal("VIX", vix, -1, 0, 0.9,
                           f"VIX {vix:.1f} — extreme fear, growth crisis signal")
    if vix >= 25:
        return MacroSignal("VIX", vix, -1, 0, 0.7,
                           f"VIX {vix:.1f} — elevated risk, growth bearish")
    if vix >= 18:
        return MacroSignal("VIX", vix, 0, 0, 0.4,
                           f"VIX {vix:.1f} — neutral range")
    return MacroSignal("VIX", vix, +1, 0, 0.6,
                       f"VIX {vix:.1f} — low volatility, risk-on environment")


def _fedfunds_signal(ffr: Optional[float]) -> MacroSignal:
    """Fed Funds Rate. Rising = inflation-fighting (inflation bullish signal)."""
    if ffr is None:
        return MacroSignal("Fed Funds Rate", 0, 0, 0, 0.0, "No data")
    if ffr >= 5.0:
        return MacroSignal("Fed Funds Rate", ffr, -1, +1, 0.85,
                           f"FFR {ffr:.2f}% — restrictive policy, inflation-fighting, growth drag")
    if ffr >= 3.0:
        return MacroSignal("Fed Funds Rate", ffr, 0, +1, 0.7,
                           f"FFR {ffr:.2f}% — tight policy, inflation elevated")
    if ffr >= 1.5:
        return MacroSignal("Fed Funds Rate", ffr, +1, 0, 0.5,
                           f"FFR {ffr:.2f}% — neutral to accommodative")
    return MacroSignal("Fed Funds Rate", ffr, +1, -1, 0.7,
                       f"FFR {ffr:.2f}% — very accommodative, reflationary")


def _cpi_signal(cpi_value: Optional[float]) -> MacroSignal:
    """CPI index level — used as inflation-high proxy via FRED CPIAUCSL."""
    # CPIAUCSL is an index (~310 range in 2024), not YoY directly
    # We use absolute level as inflation-high proxy (high = persistent inflation)
    if cpi_value is None:
        return MacroSignal("CPI Index", 0, 0, 0, 0.0, "No data")
    if cpi_value > 315:
        return MacroSignal("CPI Index", cpi_value, 0, +1, 0.7,
                           f"CPI index {cpi_value:.1f} — elevated price level")
    if cpi_value > 300:
        return MacroSignal("CPI Index", cpi_value, 0, 0, 0.4,
                           f"CPI index {cpi_value:.1f} — moderate level")
    return MacroSignal("CPI Index", cpi_value, 0, -1, 0.5,
                       f"CPI index {cpi_value:.1f} — lower inflation environment")


def _unemployment_signal(unrate: Optional[float]) -> MacroSignal:
    """Unemployment rate. Rising = growth bearish."""
    if unrate is None:
        return MacroSignal("Unemployment", 0, 0, 0, 0.0, "No data")
    if unrate >= 6.0:
        return MacroSignal("Unemployment", unrate, -1, -1, 0.85,
                           f"Unemployment {unrate:.1f}% — significant labor market weakness")
    if unrate >= 4.5:
        return MacroSignal("Unemployment", unrate, -1, 0, 0.6,
                           f"Unemployment {unrate:.1f}% — softening labor market")
    if unrate <= 3.5:
        return MacroSignal("Unemployment", unrate, +1, +1, 0.7,
                           f"Unemployment {unrate:.1f}% — very tight labor market, wage pressure")
    return MacroSignal("Unemployment", unrate, +1, 0, 0.5,
                       f"Unemployment {unrate:.1f}% — healthy labor market")


def _treasury10y_signal(dgs10: Optional[float]) -> MacroSignal:
    """10Y Treasury yield. Rising = inflation expectations up."""
    if dgs10 is None:
        return MacroSignal("10Y Treasury", 0, 0, 0, 0.0, "No data")
    if dgs10 >= 5.0:
        return MacroSignal("10Y Treasury", dgs10, -1, +1, 0.8,
                           f"10Y at {dgs10:.2f}% — very high, tightening financial conditions")
    if dgs10 >= 4.0:
        return MacroSignal("10Y Treasury", dgs10, 0, +1, 0.65,
                           f"10Y at {dgs10:.2f}% — elevated, inflation premium")
    if dgs10 >= 2.5:
        return MacroSignal("10Y Treasury", dgs10, +1, 0, 0.5,
                           f"10Y at {dgs10:.2f}% — moderate, neutral")
    return MacroSignal("10Y Treasury", dgs10, +1, -1, 0.7,
                       f"10Y at {dgs10:.2f}% — low, deflationary / risk-off")


def _options_sentiment_signal(sentiment_score: Optional[float]) -> MacroSignal:
    """Aggregate options flow + news sentiment."""
    if sentiment_score is None:
        return MacroSignal("Market Sentiment", 0, 0, 0, 0.0, "No data")
    if sentiment_score >= 0.3:
        return MacroSignal("Market Sentiment", sentiment_score, +1, 0, 0.6,
                           f"Sentiment score {sentiment_score:.2f} — broadly bullish")
    if sentiment_score <= -0.3:
        return MacroSignal("Market Sentiment", sentiment_score, -1, 0, 0.6,
                           f"Sentiment score {sentiment_score:.2f} — broadly bearish")
    return MacroSignal("Market Sentiment", sentiment_score, 0, 0, 0.3,
                       f"Sentiment score {sentiment_score:.2f} — neutral")


# ── Main regime classifier ────────────────────────────────────────────────────

def detect_regime(macro: dict, sentiment_score: Optional[float] = None) -> RegimeReading:
    """
    Classify the current market regime from macro indicator readings.

    Args:
        macro: dict mapping series_id → value (from FRED pipeline output)
        sentiment_score: aggregate pipeline sentiment -1 to +1 (optional)

    Returns:
        RegimeReading with regime classification and confidence score
    """
    # Build signals
    signals = [
        _yield_curve_signal(macro.get("T10Y2Y")),
        _vix_signal(macro.get("VIXCLS")),
        _fedfunds_signal(macro.get("FEDFUNDS")),
        _cpi_signal(macro.get("CPIAUCSL")),
        _unemployment_signal(macro.get("UNRATE")),
        _treasury10y_signal(macro.get("DGS10")),
    ]
    if sentiment_score is not None:
        signals.append(_options_sentiment_signal(sentiment_score))

    # Weighted vote aggregation
    growth_num = inflation_num = weight_sum = 0.0
    for s in signals:
        w = s.confidence
        growth_num    += s.growth_vote    * w
        inflation_num += s.inflation_vote * w
        weight_sum    += w

    growth_score    = growth_num    / max(weight_sum, 1e-6)
    inflation_score = inflation_num / max(weight_sum, 1e-6)

    # Regime quadrant
    if growth_score >= 0 and inflation_score <= 0:
        regime = "goldilocks"
    elif growth_score >= 0 and inflation_score > 0:
        regime = "reflation"
    elif growth_score < 0 and inflation_score > 0:
        regime = "stagflation"
    else:
        regime = "deflation"

    # Confidence: how much signals agree (0–100%)
    # Max disagreement would give score near 0; full agreement near 1
    abs_growth    = abs(growth_score)
    abs_inflation = abs(inflation_score)
    raw_conf = (abs_growth + abs_inflation) / 2
    confidence_pct = round(min(raw_conf * 100, 99), 1)

    # Transition risk: how close to axis boundaries
    min_dist = min(abs_growth, abs_inflation)
    if min_dist < 0.15:
        transition_risk = "high"   # near quadrant boundary
    elif min_dist < 0.35:
        transition_risk = "medium"
    else:
        transition_risk = "low"

    info = REGIMES[regime]
    return RegimeReading(
        regime          = regime,
        confidence_pct  = confidence_pct,
        growth_score    = round(growth_score, 4),
        inflation_score = round(inflation_score, 4),
        signals         = signals,
        transition_risk = transition_risk,
        timestamp       = datetime.now(timezone.utc).isoformat(),
        favors          = info["favors"],
        avoids          = info["avoids"],
        label           = info["label"],
        color           = info["color"],
        description     = info["description"],
    )


def regime_to_dict(r: RegimeReading) -> dict:
    return {
        "regime":          r.regime,
        "label":           r.label,
        "color":           r.color,
        "description":     r.description,
        "confidence_pct":  r.confidence_pct,
        "growth_score":    r.growth_score,
        "inflation_score": r.inflation_score,
        "transition_risk": r.transition_risk,
        "timestamp":       r.timestamp,
        "favors":          r.favors,
        "avoids":          r.avoids,
        "signals": [
            {
                "name":           s.name,
                "value":          round(s.value, 4),
                "growth_vote":    s.growth_vote,
                "inflation_vote": s.inflation_vote,
                "confidence":     round(s.confidence, 3),
                "description":    s.description,
            }
            for s in r.signals
            if s.confidence > 0
        ],
    }


def macro_list_to_dict(macro_items: list[dict]) -> dict:
    """Convert pipeline macro_data list to {series_id: value} dict."""
    return {
        item.get("series_id"): item.get("value")
        for item in macro_items
        if item.get("series_id") and item.get("value") is not None
    }
