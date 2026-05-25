"""
CoinGecko — Comprehensive crypto market intelligence.
Free demo API: 10,000 calls/month, 100 calls/min. No key for basic endpoints.

Provides: price, volume, market cap, 7d sparkline, trending coins, DeFi TVL.
Rivals: Bloomberg crypto terminal ($25k/yr), Messari Pro ($300/mo).
"""

import httpx
from datetime import datetime, timezone

BASE = "https://api.coingecko.com/api/v3"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "IntelligenceTerminal/2.0",
}


async def fetch_coingecko(limit: int = 25) -> list[dict]:
    import asyncio

    async with httpx.AsyncClient(headers=HEADERS, timeout=12) as client:
        markets_task  = _fetch_markets(client, min(limit, 20))
        trending_task = _fetch_trending(client)
        global_task   = _fetch_global(client)

        markets, trending, global_data = await asyncio.gather(
            markets_task, trending_task, global_task, return_exceptions=True
        )

    items = []
    if isinstance(markets, list):
        items.extend(markets)
    if isinstance(trending, list):
        items.extend(trending)
    if isinstance(global_data, dict) and global_data:
        items.append(global_data)

    return items[:limit]


async def _fetch_markets(client: httpx.AsyncClient, n: int) -> list[dict]:
    try:
        r = await client.get(f"{BASE}/coins/markets", params={
            "vs_currency":           "usd",
            "order":                 "market_cap_desc",
            "per_page":              n,
            "page":                  1,
            "price_change_percentage": "24h,7d",
        })
        if r.status_code != 200:
            return []

        items = []
        for c in r.json():
            sym   = (c.get("symbol") or "").upper()
            name  = c.get("name", sym)
            price = c.get("current_price", 0) or 0
            chg24 = c.get("price_change_percentage_24h", 0) or 0
            chg7d = c.get("price_change_percentage_7d_in_currency", 0) or 0
            vol   = c.get("total_volume", 0) or 0
            mcap  = c.get("market_cap", 0) or 0
            rank  = c.get("market_cap_rank", 99)

            sentiment = "bullish" if chg24 > 1 else "bearish" if chg24 < -1 else "neutral"
            trend7 = f"+{chg7d:.1f}%" if chg7d > 0 else f"{chg7d:.1f}%"

            items.append({
                "id":              f"cg-market-{c.get('id',sym)}",
                "source":         "coingecko",
                "title":          f"{name} ({sym}): ${price:,.4g} ({'+' if chg24>=0 else ''}{chg24:.2f}% 24h, {trend7} 7d)",
                "url":            f"https://www.coingecko.com/en/coins/{c.get('id','bitcoin')}",
                "score":          max(0, int(100 - rank * 0.5)),
                "preview":        f"MCap ${mcap/1e9:.2f}B · Vol ${vol/1e6:.0f}M · Rank #{rank}",
                "meta":           f"CoinGecko · Rank #{rank}",
                "tags":           ["crypto", "market", sym.lower()],
                "sector":         "crypto",
                "sentiment_label": sentiment,
                "sentiment_score": round(chg24 / 20, 4),
                "entities":       [sym],
                "market_data": {
                    "ticker":     sym,
                    "name":       name,
                    "price":      price,
                    "change_pct": round(chg24, 4),
                    "arrow":      "▲" if chg24 >= 0 else "▼",
                    "type":       "crypto",
                    "volume_usd": vol,
                    "market_cap": mcap,
                    "change_7d":  round(chg7d, 4),
                },
            })
        return items
    except Exception:
        return []


async def _fetch_trending(client: httpx.AsyncClient) -> list[dict]:
    try:
        r = await client.get(f"{BASE}/search/trending")
        if r.status_code != 200:
            return []
        coins = r.json().get("coins", [])
        items = []
        for entry in coins[:5]:
            c    = entry.get("item", {})
            name = c.get("name", "")
            sym  = (c.get("symbol") or "").upper()
            rank = c.get("market_cap_rank") or 999
            items.append({
                "id":      f"cg-trend-{c.get('id',sym)}",
                "source":  "coingecko",
                "title":   f"Trending: {name} ({sym}) — #{rank} market cap",
                "url":     f"https://www.coingecko.com/en/coins/{c.get('id','bitcoin')}",
                "score":   30,
                "preview": f"{name} is trending on CoinGecko. Market cap rank #{rank}.",
                "meta":    "CoinGecko · Trending",
                "tags":    ["crypto", "trending", sym.lower()],
                "sector":  "crypto",
                "sentiment_label": "bullish",
                "sentiment_score": 0.3,
                "entities": [sym],
            })
        return items
    except Exception:
        return []


async def _fetch_global(client: httpx.AsyncClient) -> dict | None:
    try:
        r = await client.get(f"{BASE}/global")
        if r.status_code != 200:
            return None
        d    = r.json().get("data", {})
        mcap = d.get("total_market_cap", {}).get("usd", 0) or 0
        vol  = d.get("total_volume", {}).get("usd", 0) or 0
        btc  = d.get("market_cap_percentage", {}).get("btc", 0) or 0
        chg  = d.get("market_cap_change_percentage_24h_usd", 0) or 0
        n    = d.get("active_cryptocurrencies", 0)
        sentiment = "bullish" if chg > 1 else "bearish" if chg < -1 else "neutral"
        return {
            "id":              "cg-global",
            "source":         "coingecko",
            "title":          f"Crypto Global: ${mcap/1e12:.2f}T market cap ({'+' if chg>=0 else ''}{chg:.2f}% 24h) · BTC dom {btc:.1f}%",
            "url":            "https://www.coingecko.com/en/global-charts",
            "score":          50,
            "preview":        f"{n:,} active cryptocurrencies. 24h volume ${vol/1e9:.1f}B. Bitcoin dominance {btc:.1f}%.",
            "meta":           "CoinGecko · Global",
            "tags":           ["crypto", "global", "market"],
            "sector":         "crypto",
            "sentiment_label": sentiment,
            "sentiment_score": round(chg / 20, 4),
            "entities":       ["BTC", "ETH"],
        }
    except Exception:
        return None
