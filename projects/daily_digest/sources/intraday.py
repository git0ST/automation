"""
Intraday OHLCV source — 5-minute bars via yfinance (free, no API key).

Fetches the current trading session's bars for a watchlist of tickers.
Computes per-bar:
  - Cumulative VWAP (volume-weighted average price for the session)
  - VWAP deviation % (price vs VWAP — mean reversion signal)
  - Volume ratio vs 20-bar rolling average (unusual volume flag)
  - 14-period RSI on the 5-min closes

HFT use-cases enabled:
  - VWAP breakout / fade entries
  - Unusual volume spike detection (front-run retail order flow)
  - Intraday momentum confirmation before entering daily signal
  - Open Range Breakout (first 30-min high/low)

Only fetches during US market hours (9:30am–4:00pm ET Mon–Fri).
Returns empty list outside market hours — caller should skip gracefully.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Optional

# Compact watchlist — same 50 names as opportunity_runner
INTRADAY_UNIVERSE = [
    "NVDA", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "TSLA", "AVGO", "ORCL",
    "AMD", "INTC", "QCOM", "ARM", "SMCI", "TSM", "MU", "MRVL",
    "CRM", "ADBE", "NOW", "PLTR", "CRWD", "PANW", "SHOP",
    "JPM", "GS", "MS", "BAC", "BRK-B", "V", "MA", "BLK",
    "XOM", "CVX", "COP", "SLB",
    "UNH", "LLY", "JNJ", "MRK", "ABBV",
    "WMT", "COST", "HD", "MCD", "DIS", "NFLX",
    "BA", "CAT", "GE", "RTX",
]

_cache: dict[str, dict] = {}
_CACHE_TTL = 300  # 5 min — matches main market refresh loop


def _is_market_hours() -> bool:
    """True during US regular session (9:30–16:00 ET Mon–Fri)."""
    try:
        import pytz
        et = pytz.timezone("America/New_York")
        now = datetime.now(et)
        if now.weekday() >= 5:
            return False
        market_open  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0,  second=0, microsecond=0)
        return market_open <= now <= market_close
    except ImportError:
        # pytz not available — assume market is open (graceful degradation)
        return True


def _compute_vwap(df) -> list[float]:
    """Cumulative VWAP = Σ(typical_price × volume) / Σvolume."""
    import numpy as np
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    cum_tv  = (typical * df["Volume"]).cumsum()
    cum_v   = df["Volume"].cumsum().replace(0, float("nan"))
    return (cum_tv / cum_v).tolist()


def _compute_rsi(closes: list[float], n: int = 14) -> Optional[float]:
    if len(closes) < n + 1:
        return None
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))][-n:]
    gains  = [max(c, 0.0) for c in changes]
    losses = [max(-c, 0.0) for c in changes]
    avg_g  = sum(gains) / n
    avg_l  = sum(losses) / n
    if avg_l < 1e-9:
        return 100.0
    rs = avg_g / avg_l
    return round(100 - 100 / (1 + rs), 2)


def _fetch_ticker_intraday(ticker: str) -> list[dict]:
    """Fetch 5-min bars for one ticker. Returns list of bar dicts."""
    try:
        import yfinance as yf
        import numpy as np
    except ImportError:
        return []

    hist = yf.Ticker(ticker).history(period="1d", interval="5m", auto_adjust=True)
    if hist.empty or len(hist) < 2:
        return []

    vwap_list = _compute_vwap(hist)
    closes    = hist["Close"].tolist()
    volumes   = hist["Volume"].tolist()

    # 20-bar rolling average volume for ratio
    vol_arr = np.array(volumes, dtype=float)
    avg_20  = np.convolve(vol_arr, np.ones(20) / 20, mode="full")[:len(vol_arr)]
    avg_20[:19] = vol_arr[:19]   # first 19 bars: use cumulative mean

    bars = []
    for i, (ts, row) in enumerate(hist.iterrows()):
        vwap     = vwap_list[i]
        close    = float(row["Close"])
        vol      = float(row["Volume"])
        avg_v    = float(avg_20[i])
        vwap_dev = round((close - vwap) / vwap * 100, 4) if vwap and vwap > 0 else None
        vol_ratio= round(vol / avg_v, 3) if avg_v > 0 else None
        rsi      = _compute_rsi(closes[:i + 1])

        # bar_time as UTC ISO string
        try:
            bar_time = ts.to_pydatetime().astimezone(timezone.utc).isoformat()
        except Exception:
            bar_time = str(ts)

        bars.append({
            "ticker":    ticker,
            "bar_time":  bar_time,
            "open":      round(float(row["Open"]),  4),
            "high":      round(float(row["High"]),  4),
            "low":       round(float(row["Low"]),   4),
            "close":     round(close,               4),
            "volume":    round(vol,                 0),
            "vwap":      round(vwap,                4) if vwap else None,
            "vwap_dev":  vwap_dev,
            "vol_ratio": vol_ratio,
            "rsi_14":    rsi,
        })

    return bars


async def fetch_intraday(
    tickers: Optional[list[str]] = None,
    limit: int = 50,
) -> list[dict]:
    """
    Async entry point — fetch 5-min bars for each ticker in parallel.

    Returns pipeline-compatible items with `intraday_data` payload.
    Each item represents the LATEST bar for a ticker (most recent 5-min close).

    Also computes Open Range (first 6 bars = 30 min) high/low for ORB strategy.
    """
    if not _is_market_hours():
        return []

    tickers = (tickers or INTRADAY_UNIVERSE)[:limit]

    cache_key = ",".join(sorted(tickers))
    entry = _cache.get(cache_key)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL:
        return entry["items"]

    loop = asyncio.get_event_loop()
    all_bars_list = await asyncio.gather(
        *[loop.run_in_executor(None, _fetch_ticker_intraday, t) for t in tickers],
        return_exceptions=True,
    )

    items = []
    for ticker, bars in zip(tickers, all_bars_list):
        if isinstance(bars, Exception) or not bars:
            continue

        latest = bars[-1]
        or_bars = bars[:6]  # open range = first 30 min
        or_high = max(b["high"] for b in or_bars) if or_bars else None
        or_low  = min(b["low"]  for b in or_bars) if or_bars else None

        # Unusual volume flag on latest bar
        vr = latest.get("vol_ratio")
        unusual_vol = vr is not None and vr > 2.5

        # VWAP position
        vd = latest.get("vwap_dev")
        vwap_signal = "above" if (vd and vd > 0.5) else "below" if (vd and vd < -0.5) else "at"

        items.append({
            "id":     f"intraday_{ticker}_{latest['bar_time']}",
            "source": "intraday",
            "title":  f"{ticker} {latest['close']:.2f} | VWAP {vwap_signal} | RSI {latest.get('rsi_14', '—')}",
            "url":    "",
            "score":  10,
            "tags":   ["intraday"] + (["unusual_volume"] if unusual_vol else []),
            "intraday_data": {
                "ticker":      ticker,
                "latest_bar":  latest,
                "all_bars":    bars,
                "open_range":  {"high": or_high, "low": or_low, "bars": len(or_bars)},
                "unusual_vol": unusual_vol,
                "vwap_signal": vwap_signal,
                "bar_count":   len(bars),
            },
        })

    _cache[cache_key] = {"items": items, "ts": time.time()}
    return items
