"""
Finance source — stocks via Yahoo Finance API (no yfinance dependency)
+ crypto via CoinGecko free API.

Uses direct httpx calls against Yahoo Finance's chart API, avoiding
any pandas/numpy compatibility issues.
"""

import asyncio
import httpx

STOCK_TICKERS = {
    "^GSPC":  ("S&P 500",    "index"),
    "^IXIC":  ("NASDAQ",     "index"),
    "^DJI":   ("Dow Jones",  "index"),
    "NVDA":   ("NVIDIA",     "stock"),
    "AAPL":   ("Apple",      "stock"),
    "MSFT":   ("Microsoft",  "stock"),
    "GOOGL":  ("Alphabet",   "stock"),
    "META":   ("Meta",       "stock"),
    "TSLA":   ("Tesla",      "stock"),
    "AMZN":   ("Amazon",     "stock"),
}

CRYPTO_IDS = ["bitcoin", "ethereum", "solana"]

YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}


def _arrow(pct: float) -> str:
    return "▲" if pct >= 0 else "▼"


async def _fetch_one_stock(client: httpx.AsyncClient, ticker: str) -> dict | None:
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        r = await client.get(url, params={"range": "1d", "interval": "1d"},
                             headers=YF_HEADERS, timeout=8)
        if r.status_code != 200:
            return None
        data = r.json()
        result = data["chart"]["result"][0]
        meta   = result["meta"]
        price  = meta.get("regularMarketPrice") or meta.get("previousClose")
        prev   = meta.get("chartPreviousClose") or meta.get("previousClose")
        if not price or not prev:
            return None
        pct = (price - prev) / prev * 100
        name, typ = STOCK_TICKERS[ticker]
        return {
            "ticker":     ticker,
            "name":       name,
            "price":      price,
            "change_pct": pct,
            "arrow":      _arrow(pct),
            "type":       typ,
        }
    except Exception:
        return None


async def _fetch_all_stocks() -> list[dict]:
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[_fetch_one_stock(client, t) for t in STOCK_TICKERS],
            return_exceptions=True,
        )
    return [r for r in results if isinstance(r, dict)]


async def _fetch_crypto() -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(
                "https://api.coingecko.com/api/v3/coins/markets",
                params={
                    "vs_currency": "usd",
                    "ids": ",".join(CRYPTO_IDS),
                    "order": "market_cap_desc",
                    "per_page": len(CRYPTO_IDS),
                    "price_change_percentage": "24h",
                },
                headers={"Accept": "application/json"},
            )
            if r.status_code != 200:
                return []
            results = []
            for coin in r.json():
                pct = coin.get("price_change_percentage_24h") or 0.0
                results.append({
                    "ticker":     coin["symbol"].upper(),
                    "name":       coin["name"],
                    "price":      coin["current_price"],
                    "change_pct": pct,
                    "arrow":      _arrow(pct),
                    "market_cap": coin.get("market_cap", 0),
                    "type":       "crypto",
                })
            return results
    except Exception:
        return []


async def fetch_finance(limit: int = 20) -> list[dict]:
    stocks_raw, crypto_raw = await asyncio.gather(
        _fetch_all_stocks(),
        _fetch_crypto(),
    )

    items: list[dict] = []

    for s in stocks_raw:
        pct   = s["change_pct"]
        arrow = s["arrow"]
        price_str = f"${s['price']:,.2f}" if s["type"] != "index" else f"{s['price']:,.2f}"
        items.append({
            "id":          f"finance-{s['ticker']}",
            "source":      "finance",
            "title":       f"{s['name']} ({s['ticker']}) {arrow} {abs(pct):.2f}%",
            "url":         f"https://finance.yahoo.com/quote/{s['ticker']}",
            "score":       max(1, int(abs(pct) * 10)),
            "preview":     f"Price: {price_str}  ·  Change: {arrow}{abs(pct):.2f}%",
            "meta":        "Markets · " + s["type"].title(),
            "tags":        ["news"],
            "market_data": s,
        })

    for c in crypto_raw:
        pct   = c["change_pct"]
        arrow = c["arrow"]
        mcap_b = c.get("market_cap", 0) / 1e9
        items.append({
            "id":          f"crypto-{c['ticker']}",
            "source":      "finance",
            "title":       f"{c['name']} ({c['ticker']}) {arrow} {abs(pct):.2f}%",
            "url":         f"https://www.coingecko.com/en/coins/{c['name'].lower()}",
            "score":       max(1, int(abs(pct) * 10)),
            "preview":     f"Price: ${c['price']:,.0f}  ·  24h: {arrow}{abs(pct):.2f}%  ·  MCap: ${mcap_b:.1f}B",
            "meta":        "Crypto",
            "tags":        ["news"],
            "market_data": c,
        })

    return items[:limit]
