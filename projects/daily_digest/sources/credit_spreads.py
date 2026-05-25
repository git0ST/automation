"""
Credit Spread Monitor — the institutional risk canary.

ICE BofA credit spread indices via FRED (free, no key required).
These are the same series used by BlackRock, Goldman Sachs, and the
Federal Reserve to monitor credit market stress in real time.

  BAMLH0A0HYM2  — US High-Yield OAS (junk bonds vs Treasuries)
  BAMLC0A0CM    — US Investment-Grade OAS (corporate bonds)
  BAMLHE00EHYOAS — Euro HY OAS (European credit stress)
  BAMLC4A0C10YEY — Global Investment Grade (cross-asset reference)
  TEDRATE        — TED Spread (interbank funding stress)
  T10YIE         — 10Y Breakeven Inflation (market inflation expectations)
  DFII10         — 10Y TIPS Real Yield (real interest rate)

When HY spreads > 600 bps:  crisis territory (2008 peak: 2100 bps)
When HY spreads > 400 bps:  elevated stress, recession risk
When HY spreads 250–400:    caution zone
When HY spreads < 250:      benign credit environment

BlackRock uses HY spread level + direction as a primary regime signal.
Bloomberg's LEIG (Global Aggregate Index) relies on this data for pricing.
"""

import asyncio
import httpx
from datetime import datetime, timezone

BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"

CREDIT_SERIES = {
    "BAMLH0A0HYM2":   ("US HY OAS",           "bps",  "credit", "high_yield"),
    "BAMLC0A0CM":     ("US IG OAS",            "bps",  "credit", "invest_grade"),
    "TEDRATE":        ("TED Spread",           "bps",  "funding","interbank"),
    "T10YIE":         ("10Y Breakeven Infl",   "%",    "inflation","tips_breakeven"),
    "DFII10":         ("10Y Real Yield (TIPS)", "%",   "rates",  "real_yield"),
    "BAMLHE00EHYOAS": ("Euro HY OAS",          "bps",  "credit", "euro_hy"),
}

# Risk thresholds — FRED reports these as percentage points
# (e.g. BAMLH0A0HYM2 = 2.78 means 278 bps; thresholds must match that scale)
HY_THRESHOLDS  = [(6.0, "bearish", "crisis"),   (4.0, "bearish", "elevated"),
                  (3.0, "neutral", "caution"),   (0,   "bullish", "benign")]
IG_THRESHOLDS  = [(2.0, "bearish", "wide"),      (1.5, "neutral", "elevated"),
                  (0.8, "bullish", "normal"),     (0,   "bullish", "tight")]
TED_THRESHOLDS = [(1.0, "bearish", "stress"),    (0.5, "neutral", "caution"),
                  (0,   "bullish", "normal")]


def _credit_sentiment(series_id: str, value: float) -> tuple[str, str]:
    """Return (sentiment_label, stress_level) for a credit series."""
    if series_id == "BAMLH0A0HYM2":
        for threshold, label, stress in HY_THRESHOLDS:
            if value >= threshold:
                return label, stress
    if series_id == "BAMLC0A0CM":
        for threshold, label, stress in IG_THRESHOLDS:
            if value >= threshold:
                return label, stress
    if series_id == "TEDRATE":
        for threshold, label, stress in TED_THRESHOLDS:
            if value >= threshold:
                return label, stress
    if series_id == "T10YIE":
        if value > 3.0:   return "bearish", "high"
        if value > 2.0:   return "neutral", "moderate"
        return "bullish", "low"
    if series_id == "DFII10":
        if value > 2.5:   return "bearish", "restrictive"
        if value > 1.0:   return "neutral", "moderate"
        return "bullish", "accommodative"
    return "neutral", "normal"


async def _fetch_series(client: httpx.AsyncClient, sid: str) -> dict | None:
    try:
        r = await client.get(BASE, params={"id": sid}, timeout=12)
        if r.status_code != 200:
            return None
        lines = r.text.strip().split("\n")
        for line in reversed(lines[1:]):
            parts = line.split(",")
            if len(parts) == 2 and parts[1].strip() not in ("", "."):
                return {
                    "series_id": sid,
                    "value":     float(parts[1].strip()),
                    "period":    parts[0].strip(),
                }
    except Exception:
        return None


async def fetch_credit_spreads(limit: int = 20) -> list[dict]:
    """Fetch credit spread indices from FRED."""
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[_fetch_series(client, sid) for sid in CREDIT_SERIES],
            return_exceptions=True,
        )

    items = []
    for sid, result in zip(CREDIT_SERIES.keys(), results):
        if not isinstance(result, dict):
            continue
        name, unit, sector, subtype = CREDIT_SERIES[sid]
        value = result["value"]
        period = result["period"]
        sentiment, stress = _credit_sentiment(sid, value)

        # Format display value
        # FRED reports OAS as percentage points (2.78 = 278 bps); convert for display
        if unit == "bps":
            val_str = f"{value*100:.0f} bps"
        else:
            val_str = f"{value:.2f}%"

        title = f"[CREDIT] {name}: {val_str} [{stress.upper()}]"
        preview = (
            f"{name} at {val_str} ({period}). "
            f"Credit stress level: {stress}. "
            f"Source: FRED / ICE BofA Index."
        )

        items.append({
            "id":              f"credit-{sid}-{period}",
            "source":         "credit",
            "title":          title,
            "url":            f"https://fred.stlouisfed.org/series/{sid}",
            "score":          50 if sentiment != "neutral" else 30,
            "preview":        preview,
            "meta":           f"Credit · FRED / ICE BofA · {period}",
            "tags":           ["credit", "spreads", subtype],
            "sector":         "credit",
            "sentiment_label": sentiment,
            "sentiment_score": -0.5 if sentiment == "bearish" else (0.3 if sentiment == "bullish" else 0),
            "entities":       [],
            "macro_data": {
                "series_id": sid,
                "name":      name,
                "value":     value,
                "unit":      unit,
                "period":    period,
                "subtype":   subtype,
                "stress":    stress,
            },
        })

    return items[:limit]
