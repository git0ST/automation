"""Forex sources — DXY index + major pairs via Yahoo Finance.

Wide currency moves often lead equity/bond regime shifts. Tracking DXY +
EUR/USD/JPY/GBP/CHF provides early warning for global risk-on/off rotation.
"""
from __future__ import annotations
import asyncio
from datetime import datetime

FOREX_PAIRS = {
    "DX-Y.NYB": ("US Dollar Index (DXY)", "index"),
    "EURUSD=X": ("EUR / USD",            "rate"),
    "USDJPY=X": ("USD / JPY",            "rate"),
    "GBPUSD=X": ("GBP / USD",            "rate"),
    "USDCHF=X": ("USD / CHF",            "rate"),
    "AUDUSD=X": ("AUD / USD",            "rate"),
    "USDCAD=X": ("USD / CAD",            "rate"),
    "USDCNY=X": ("USD / CNY",            "rate"),
}


async def fetch_forex(limit: int = 8) -> list[dict]:
    """Fetch latest forex pair quotes via yfinance (free, 15-min delayed)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_fetch, limit)


def _sync_fetch(limit: int) -> list[dict]:
    try:
        import yfinance as yf
    except ImportError:
        return []

    items = []
    pairs = list(FOREX_PAIRS.items())[:limit]
    for symbol, (name, unit) in pairs:
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period="5d", interval="1d", auto_adjust=True)
            if hist.empty or len(hist) < 2:
                continue
            last = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            chg_1d = (last / prev - 1) * 100 if prev else 0
            # Strength signal — moves > 0.5% in major pairs are notable
            label = "neutral"
            if symbol == "DX-Y.NYB":  # DXY: rising USD = risk-off
                label = "bearish" if chg_1d > 0.5 else ("bullish" if chg_1d < -0.5 else "neutral")
            else:
                label = "bullish" if abs(chg_1d) < 0.3 else "neutral"
            items.append({
                "id":         f"forex-{symbol}",
                "source":     "forex",
                "title":      f"{name} {last:.4f} ({chg_1d:+.2f}%)",
                "url":        f"https://finance.yahoo.com/quote/{symbol}",
                "preview":    f"{name} at {last:.4f}, change {chg_1d:+.2f}% over 1 day. Unit: {unit}.",
                "sentiment_label": label,
                "sentiment_score": -abs(chg_1d) / 5 if label == "bearish" else (abs(chg_1d) / 5 if label == "bullish" else 0),
                "terminal_score": min(abs(chg_1d) * 20, 100),
                "macro_data": {
                    "series_id": symbol,
                    "value":     last,
                    "change_pct": round(chg_1d, 3),
                    "unit":      unit,
                    "name":      name,
                    "period":    hist.index[-1].strftime("%Y-%m-%d"),
                },
                "published_at": datetime.utcnow().isoformat(),
            })
        except Exception:
            continue
    return items
