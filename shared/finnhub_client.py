"""Finnhub API client — free real-time market data.

Free tier:
  - 60 calls / minute
  - Real-time US stocks (no 15-min delay vs yfinance free)
  - Forex + crypto quotes
  - Financial news (categorized + per-symbol)
  - Company profiles + earnings

Sign up: https://finnhub.io/register (no credit card)
Set FINNHUB_API_KEY in env or Streamlit secrets.
"""
from __future__ import annotations
import asyncio
import os
import time
from datetime import datetime, timezone

import httpx


BASE = "https://finnhub.io/api/v1"


def _api_key() -> str | None:
    """Read key from Streamlit secrets first, then env."""
    try:
        import streamlit as st
        key = st.secrets.get("FINNHUB_API_KEY")
        if key:
            return key
    except Exception:
        pass
    return os.getenv("FINNHUB_API_KEY")


def is_available() -> bool:
    return bool(_api_key())


# ── Simple in-memory rate limiter (60 calls/min) ────────────────────────────
_call_timestamps: list[float] = []
_RATE_LIMIT = 55  # leave headroom below 60/min
_WINDOW = 60.0


def _rate_limit_wait():
    now = time.time()
    global _call_timestamps
    _call_timestamps = [t for t in _call_timestamps if now - t < _WINDOW]
    if len(_call_timestamps) >= _RATE_LIMIT:
        sleep_for = _WINDOW - (now - _call_timestamps[0]) + 0.5
        if sleep_for > 0:
            time.sleep(sleep_for)
    _call_timestamps.append(time.time())


# ── Endpoints ───────────────────────────────────────────────────────────────

def quote_sync(symbol: str) -> dict | None:
    """Real-time quote: c (current), h (high), l (low), o (open),
    pc (prev close), t (timestamp). NOTE: returns 0s for invalid symbols."""
    key = _api_key()
    if not key:
        return None
    _rate_limit_wait()
    try:
        with httpx.Client(timeout=6) as client:
            r = client.get(f"{BASE}/quote", params={"symbol": symbol, "token": key})
            if r.status_code == 200:
                data = r.json()
                if data and data.get("c", 0) > 0:
                    return data
    except Exception:
        pass
    return None


def quotes_batch_sync(symbols: list[str]) -> dict[str, dict]:
    """Fetch many symbols. Returns {symbol: quote_dict}."""
    results = {}
    for sym in symbols:
        q = quote_sync(sym)
        if q:
            results[sym] = q
    return results


async def quote(symbol: str) -> dict | None:
    """Async wrapper using thread executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, quote_sync, symbol)


async def quotes_batch(symbols: list[str]) -> dict[str, dict]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, quotes_batch_sync, symbols)


def market_news_sync(category: str = "general", limit: int = 20) -> list[dict]:
    """Real-time financial news. category: general | forex | crypto | merger."""
    key = _api_key()
    if not key:
        return []
    _rate_limit_wait()
    try:
        with httpx.Client(timeout=8) as client:
            r = client.get(f"{BASE}/news", params={"category": category, "token": key})
            if r.status_code == 200:
                return r.json()[:limit]
    except Exception:
        pass
    return []


async def market_news(category: str = "general", limit: int = 20) -> list[dict]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, market_news_sync, category, limit)


def company_news_sync(symbol: str, lookback_days: int = 7, limit: int = 15) -> list[dict]:
    """Recent company-specific news."""
    key = _api_key()
    if not key:
        return []
    _rate_limit_wait()
    from datetime import date, timedelta
    to_date = date.today().isoformat()
    from_date = (date.today() - timedelta(days=lookback_days)).isoformat()
    try:
        with httpx.Client(timeout=8) as client:
            r = client.get(f"{BASE}/company-news", params={
                "symbol": symbol, "from": from_date, "to": to_date, "token": key,
            })
            if r.status_code == 200:
                return r.json()[:limit]
    except Exception:
        pass
    return []


def company_profile_sync(symbol: str) -> dict | None:
    """Company profile — name, exchange, industry, market cap, web, IPO date."""
    key = _api_key()
    if not key:
        return None
    _rate_limit_wait()
    try:
        with httpx.Client(timeout=6) as client:
            r = client.get(f"{BASE}/stock/profile2", params={"symbol": symbol, "token": key})
            if r.status_code == 200:
                data = r.json()
                return data if data else None
    except Exception:
        pass
    return None


def basic_financials_sync(symbol: str) -> dict | None:
    """Key ratios — P/E, P/B, EPS growth, ROE, debt/equity, dividend yield."""
    key = _api_key()
    if not key:
        return None
    _rate_limit_wait()
    try:
        with httpx.Client(timeout=8) as client:
            r = client.get(f"{BASE}/stock/metric",
                           params={"symbol": symbol, "metric": "all", "token": key})
            if r.status_code == 200:
                data = r.json()
                return data.get("metric", {}) if data else None
    except Exception:
        pass
    return None


def recommendations_sync(symbol: str) -> list[dict]:
    """Analyst recommendation trends — buy/hold/sell counts per month."""
    key = _api_key()
    if not key:
        return []
    _rate_limit_wait()
    try:
        with httpx.Client(timeout=6) as client:
            r = client.get(f"{BASE}/stock/recommendation",
                           params={"symbol": symbol, "token": key})
            if r.status_code == 200:
                return r.json() or []
    except Exception:
        pass
    return []


def earnings_sync(symbol: str, limit: int = 4) -> list[dict]:
    """Recent earnings — actual vs estimated EPS."""
    key = _api_key()
    if not key:
        return []
    _rate_limit_wait()
    try:
        with httpx.Client(timeout=6) as client:
            r = client.get(f"{BASE}/stock/earnings",
                           params={"symbol": symbol, "limit": limit, "token": key})
            if r.status_code == 200:
                return r.json() or []
    except Exception:
        pass
    return []


# ── Normalisers — convert Finnhub payloads to our pipeline schema ───────────

def normalize_quote(symbol: str, q: dict) -> dict | None:
    """Convert Finnhub quote → our standard {price, change_pct, history}."""
    if not q or q.get("c", 0) <= 0:
        return None
    curr = float(q["c"])
    prev = float(q.get("pc") or curr)
    return {
        "price":      round(curr, 2),
        "change_pct": round((curr / prev - 1) * 100, 2) if prev else 0,
        "high":       round(float(q.get("h") or curr), 2),
        "low":        round(float(q.get("l") or curr), 2),
        "open":       round(float(q.get("o") or curr), 2),
        "prev_close": round(prev, 2),
        "timestamp":  int(q.get("t") or 0),
        "source":     "finnhub_realtime",
    }


def normalize_news(article: dict) -> dict | None:
    """Convert Finnhub news article → our pipeline item schema."""
    if not article:
        return None
    ts = article.get("datetime")
    published_at = (datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                    if ts else datetime.now(timezone.utc).isoformat())
    return {
        "id":       f"finnhub-{article.get('id') or article.get('url', '')[:50]}",
        "source":   "finnhub",
        "title":    (article.get("headline") or "")[:500],
        "url":      article.get("url") or "",
        "preview":  (article.get("summary") or "")[:600],
        "score":    0,
        "tags":     [article.get("category", "general")],
        "meta":     article.get("source", ""),
        "published_at": published_at,
    }
