"""Commodities — oil, gold, silver, copper, gas via Yahoo Finance.

Commodity moves often precede inflation surprises and risk regime shifts.
Energy + metals form the inflation-trade complex; copper is "Dr. Copper"
for global growth.
"""
from __future__ import annotations
import asyncio
from datetime import datetime

COMMODITIES = {
    "CL=F":  ("WTI Crude Oil",          "$/bbl",  "energy"),
    "BZ=F":  ("Brent Crude Oil",        "$/bbl",  "energy"),
    "NG=F":  ("Natural Gas",            "$/mmBtu", "energy"),
    "GC=F":  ("Gold",                   "$/oz",   "metals"),
    "SI=F":  ("Silver",                 "$/oz",   "metals"),
    "HG=F":  ("Copper",                 "$/lb",   "metals"),
    "PL=F":  ("Platinum",               "$/oz",   "metals"),
    "ZC=F":  ("Corn",                   "¢/bu",   "agri"),
    "ZW=F":  ("Wheat",                  "¢/bu",   "agri"),
    "ZS=F":  ("Soybeans",               "¢/bu",   "agri"),
}


async def fetch_commodities(limit: int = 10) -> list[dict]:
    """Fetch latest commodity futures via yfinance."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_fetch, limit)


def _sync_fetch(limit: int) -> list[dict]:
    try:
        import yfinance as yf
    except ImportError:
        return []

    items = []
    commodities = list(COMMODITIES.items())[:limit]
    for symbol, (name, unit, sector) in commodities:
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period="5d", interval="1d", auto_adjust=True)
            if hist.empty or len(hist) < 2:
                continue
            last = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            chg_1d = (last / prev - 1) * 100 if prev else 0
            # Strong moves in commodities → sentiment signal for inflation regime
            label = "neutral"
            if sector == "energy":
                # Energy spike = inflationary pressure = mild bearish for risk assets
                label = "bearish" if chg_1d > 3 else ("bullish" if chg_1d < -3 else "neutral")
            elif sector == "metals" and symbol == "GC=F":
                # Gold rally = flight to safety = risk-off signal
                label = "bearish" if chg_1d > 2 else "neutral"
            elif sector == "metals" and symbol == "HG=F":
                # Dr. Copper: rising = growth, falling = slowdown
                label = "bullish" if chg_1d > 2 else ("bearish" if chg_1d < -2 else "neutral")
            items.append({
                "id":         f"commodity-{symbol}",
                "source":     "commodity",
                "title":      f"{name} {last:,.2f} {unit} ({chg_1d:+.2f}%)",
                "url":        f"https://finance.yahoo.com/quote/{symbol}",
                "preview":    f"{name} trading at {last:,.2f} {unit}, 1D change {chg_1d:+.2f}%. Sector: {sector}.",
                "sentiment_label": label,
                "sentiment_score": -abs(chg_1d) / 10 if label == "bearish" else (abs(chg_1d) / 10 if label == "bullish" else 0),
                "terminal_score": min(abs(chg_1d) * 15, 100),
                "macro_data": {
                    "series_id": symbol,
                    "value":     last,
                    "change_pct": round(chg_1d, 3),
                    "unit":      unit,
                    "name":      name,
                    "sector":    sector,
                    "period":    hist.index[-1].strftime("%Y-%m-%d"),
                },
                "published_at": datetime.utcnow().isoformat(),
            })
        except Exception:
            continue
    return items
