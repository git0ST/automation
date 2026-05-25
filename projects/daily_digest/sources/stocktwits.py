"""
StockTwits — Real-time trader sentiment by ticker.
No API key required for public symbol streams (Cloudflare-protected).
Rivals: Bloomberg social sentiment, Refinitiv MarketPsych.

Covers: trending stocks, sector sentiment, individual ticker streams.
Note: If Cloudflare blocks requests, returns empty list gracefully.
"""

import httpx
from datetime import datetime, timezone

BASE = "https://api.stocktwits.com/api/2"

# Realistic browser headers to pass Cloudflare validation
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://stocktwits.com/",
    "Origin": "https://stocktwits.com",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
}

WATCHLIST = [
    "NVDA", "AAPL", "MSFT", "TSLA", "META", "GOOGL", "AMZN",
    "AMD", "SPY", "QQQ", "BTC.X", "ETH.X", "SOL.X",
]


def _parse_message(msg: dict, ticker: str) -> dict | None:
    body = (msg.get("body") or "").strip()
    if not body or len(body) < 15:
        return None
    mid  = msg.get("id", "")
    sent = (msg.get("entities", {}).get("sentiment") or {}).get("basic", "")
    label = "bullish" if sent == "Bullish" else "bearish" if sent == "Bearish" else "neutral"
    score_map = {"bullish": 1, "bearish": -1, "neutral": 0}

    username = (msg.get("user", {}).get("username") or "anon")[:20]
    followers = msg.get("user", {}).get("followers", 0) or 0
    created   = msg.get("created_at", "")

    return {
        "id":              f"st-{ticker}-{mid}",
        "source":         "stocktwits",
        "title":          f"[{ticker}] {body[:140]}",
        "url":            f"https://stocktwits.com/{username}",
        "score":          min(followers // 100, 50),
        "preview":        body[:300],
        "meta":           f"StockTwits · {username} ({followers:,} followers)",
        "tags":           ["sentiment", "trader", ticker.lower().replace(".x", "")],
        "sector":         "finance",
        "sentiment_label": label,
        "sentiment_score": round(score_map[label] * 0.6, 4),
        "entities":       [ticker.replace(".X", "")],
        "ticker":         ticker,
        "st_followers":   followers,
    }


async def fetch_stocktwits(limit: int = 30) -> list[dict]:
    import asyncio

    async def _symbol_stream(client: httpx.AsyncClient, ticker: str) -> list[dict]:
        try:
            r = await client.get(f"{BASE}/streams/symbol/{ticker}.json", timeout=8)
            if r.status_code != 200:
                return []
            msgs = r.json().get("messages", [])
            results = []
            for m in msgs[:4]:
                parsed = _parse_message(m, ticker)
                if parsed:
                    results.append(parsed)
            return results
        except Exception:
            return []

    # Also fetch trending
    async def _trending(client: httpx.AsyncClient) -> list[dict]:
        try:
            r = await client.get(f"{BASE}/streams/trending.json", timeout=8)
            if r.status_code != 200:
                return []
            msgs = r.json().get("messages", [])
            results = []
            for m in msgs[:6]:
                symbols = [s.get("symbol") for s in m.get("symbols", []) if s.get("symbol")]
                ticker = symbols[0] if symbols else "MARKET"
                parsed = _parse_message(m, ticker)
                if parsed:
                    results.append(parsed)
            return results
        except Exception:
            return []

    per_ticker = max(2, limit // (len(WATCHLIST) + 1))
    tickers_to_fetch = WATCHLIST[:min(len(WATCHLIST), limit // 3)]

    async with httpx.AsyncClient(headers=HEADERS, timeout=10, follow_redirects=True) as client:
        tasks = [_symbol_stream(client, t) for t in tickers_to_fetch] + [_trending(client)]
        batches = await asyncio.gather(*tasks, return_exceptions=True)

    items = []
    seen  = set()
    for batch in batches:
        if isinstance(batch, list):
            for item in batch:
                if item["id"] not in seen:
                    seen.add(item["id"])
                    items.append(item)

    return items[:limit]
