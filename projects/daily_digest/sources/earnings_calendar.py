"""
Earnings Calendar — upcoming earnings events for event-risk management.

Fetches next earnings dates for the 50-stock watchlist via yfinance.
Tickers within 5 calendar days of earnings are tagged 'event_risk=high'.

HFT use:
  - Block new position entries on tickers with earnings < 3 days away
  - Reduce position size (Kelly cap 50%) for earnings within 5 days
  - Flag post-earnings gap plays for mean-reversion setups
"""
from __future__ import annotations

import asyncio
import time
from datetime import date, datetime, timezone, timedelta
from typing import Optional

from .intraday import INTRADAY_UNIVERSE

_cache: dict = {"items": [], "ts": 0.0}
_CACHE_TTL = 3600 * 4  # refresh every 4 hours


def _fetch_earnings_for_ticker(ticker: str) -> Optional[dict]:
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).calendar
        if info is None or info.empty:
            return None

        # yfinance returns a DataFrame with columns as dates, rows as metrics
        # 'Earnings Date' is the first column in most versions
        dates = info.columns.tolist()
        if not dates:
            return None

        earn_date = dates[0]
        if hasattr(earn_date, "date"):
            earn_date = earn_date.date()
        elif isinstance(earn_date, str):
            try:
                earn_date = date.fromisoformat(earn_date[:10])
            except Exception:
                return None

        today     = date.today()
        days_away = (earn_date - today).days

        eps_est = None
        rev_est = None
        try:
            rows = info.index.tolist()
            if "EPS Estimate" in rows:
                v = info.loc["EPS Estimate"].iloc[0]
                eps_est = float(v) if v is not None and str(v) != "nan" else None
            if "Revenue Estimate" in rows:
                v = info.loc["Revenue Estimate"].iloc[0]
                rev_est = float(v) if v is not None and str(v) != "nan" else None
        except Exception:
            pass

        return {
            "ticker":        ticker,
            "earnings_date": earn_date.isoformat(),
            "days_away":     days_away,
            "eps_estimate":  eps_est,
            "rev_estimate":  rev_est,
            "event_risk":    "high" if 0 <= days_away <= 3 else "medium" if days_away <= 7 else "low",
        }
    except Exception:
        return None


async def fetch_earnings_calendar(
    tickers: Optional[list[str]] = None,
    limit: int = 50,
    window_days: int = 30,
) -> list[dict]:
    """
    Fetch upcoming earnings for the watchlist.

    Returns pipeline-compatible items for tickers with earnings within
    `window_days`. Each item has `earnings_data` payload.
    """
    global _cache

    tickers = (tickers or INTRADAY_UNIVERSE)[:limit]

    if _cache["items"] and (time.time() - _cache["ts"]) < _CACHE_TTL:
        return _cache["items"]

    loop = asyncio.get_event_loop()
    results = await asyncio.gather(
        *[loop.run_in_executor(None, _fetch_earnings_for_ticker, t) for t in tickers],
        return_exceptions=True,
    )

    items = []
    db_rows = []
    for r in results:
        if isinstance(r, Exception) or not r:
            continue
        days = r.get("days_away", 999)
        if days > window_days or days < -30:
            continue

        risk  = r["event_risk"]
        label = "bullish" if days < 0 else "neutral"
        items.append({
            "id":     f"earnings_{r['ticker']}_{r['earnings_date']}",
            "source": "earnings",
            "title":  (f"{r['ticker']} earnings in {days}d ({r['earnings_date']})"
                       if days >= 0
                       else f"{r['ticker']} earnings {abs(days)}d ago ({r['earnings_date']})"),
            "url":    "",
            "score":  15 if risk == "high" else 8,
            "tags":   ["earnings", f"event_risk_{risk}"],
            "sentiment_label": label,
            "earnings_data": r,
        })
        db_rows.append(r)

    # Persist to Supabase (non-blocking, best-effort)
    if db_rows:
        _save_earnings(db_rows)

    _cache = {"items": items, "ts": time.time()}
    return items


def _save_earnings(rows: list[dict]) -> None:
    import os
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        return
    try:
        from supabase import create_client
        client = create_client(url, key)
        db_rows = [
            {
                "ticker":        r["ticker"],
                "earnings_date": r["earnings_date"],
                "eps_estimate":  r.get("eps_estimate"),
                "rev_estimate":  r.get("rev_estimate"),
                "days_away":     r.get("days_away"),
            }
            for r in rows
        ]
        client.table("earnings_events").upsert(
            db_rows, on_conflict="ticker,earnings_date"
        ).execute()
    except Exception as e:
        print(f"[earnings] save failed: {e}")


def get_event_risk_tickers(days: int = 3) -> set[str]:
    """
    Return set of tickers with earnings within `days`.
    Used by signal_engine to block/reduce positions.
    """
    return {
        it["earnings_data"]["ticker"]
        for it in _cache["items"]
        if 0 <= it["earnings_data"].get("days_away", 999) <= days
    }
