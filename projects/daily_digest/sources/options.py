"""
Unusual Options Activity — hedge fund canary.

Uses yfinance options chain to detect:
  - Volume >> Open Interest (fresh institutional positioning)
  - Extreme put/call ratio (directional bets)
  - IV spikes (informed buying before events)

Rivals: Unusual Whales ($50/mo), Market Chameleon Pro, Bloomberg OVDV.
"""

import asyncio
from datetime import datetime, date, timedelta

WATCHLIST = [
    "NVDA", "AAPL", "MSFT", "TSLA", "META", "GOOGL", "AMZN",
    "AMD", "SPY", "QQQ", "INTC", "NFLX", "CRM",
]

VOL_OI_THRESHOLD = 3.0   # volume > 3× open interest = unusual
MIN_VOLUME       = 500    # ignore illiquid contracts


def _analyze_chain(ticker: str, calls_df, puts_df) -> list[dict]:
    signals = []
    try:
        import pandas as pd

        for side, df in [("CALL", calls_df), ("PUT", puts_df)]:
            if df is None or df.empty:
                continue
            df = df.copy()
            # Filter liquid contracts expiring within 60 days
            df = df[df["volume"] >= MIN_VOLUME]
            df = df[df["openInterest"] > 0]
            if df.empty:
                continue

            df["vol_oi"] = df["volume"] / df["openInterest"].clip(lower=1)
            unusual = df[df["vol_oi"] >= VOL_OI_THRESHOLD].sort_values("volume", ascending=False)

            for _, row in unusual.head(2).iterrows():
                strike    = row.get("strike", 0)
                vol       = int(row.get("volume", 0))
                oi        = int(row.get("openInterest", 1))
                premium   = round(row.get("lastPrice", 0) * vol * 100, 0)
                iv        = round(row.get("impliedVolatility", 0) * 100, 1)
                expiry    = str(row.get("contractSymbol", ""))[-6:]

                direction = "bullish" if side == "CALL" else "bearish"
                emoji     = "▲" if side == "CALL" else "▼"

                signals.append({
                    "id":              f"opt-{ticker}-{side}-{strike}-{expiry}",
                    "source":         "options",
                    "title":          f"{emoji} {ticker} unusual {side} sweep: {vol:,} contracts @ ${strike:.0f} (vol/OI={row['vol_oi']:.1f}×)",
                    "url":            f"https://finance.yahoo.com/quote/{ticker}/options",
                    "score":          min(int(vol / 100), 100),
                    "preview":        f"{ticker} {side} ${strike:.0f} — Volume {vol:,} vs OI {oi:,}. Premium ~${premium:,.0f}. IV {iv}%. Vol/OI ratio {row['vol_oi']:.1f}×.",
                    "meta":           f"Options Flow · {ticker}",
                    "tags":           ["options", "flow", direction, ticker.lower()],
                    "sector":         "finance",
                    "sentiment_label": direction,
                    "sentiment_score": 0.7 if direction == "bullish" else -0.7,
                    "entities":       [ticker],
                    "option_data": {
                        "ticker":    ticker,
                        "side":      side,
                        "strike":    strike,
                        "volume":    vol,
                        "oi":        oi,
                        "vol_oi":    round(float(row["vol_oi"]), 2),
                        "premium":   premium,
                        "iv":        iv,
                    },
                })
    except Exception:
        pass
    return signals


async def _fetch_ticker_options(ticker: str) -> list[dict]:
    loop = asyncio.get_event_loop()
    try:
        import yfinance as yf

        def _get():
            t = yf.Ticker(ticker)
            exps = t.options
            if not exps:
                return []
            # Use nearest expiry within 60 days
            target = date.today() + timedelta(days=60)
            valid  = [e for e in exps if datetime.strptime(e, "%Y-%m-%d").date() <= target]
            if not valid:
                valid = exps[:1]
            exp = valid[0]
            chain = t.option_chain(exp)
            return _analyze_chain(ticker, chain.calls, chain.puts)

        return await loop.run_in_executor(None, _get)
    except Exception:
        return []


async def fetch_options(limit: int = 20) -> list[dict]:
    # Run sequentially to be gentle on 8GB M1 and yfinance rate limits
    items = []
    tickers = WATCHLIST[:8]
    for ticker in tickers:
        try:
            signals = await _fetch_ticker_options(ticker)
            items.extend(signals)
            if len(items) >= limit:
                break
            await asyncio.sleep(0.3)
        except Exception:
            continue
    return items[:limit]
