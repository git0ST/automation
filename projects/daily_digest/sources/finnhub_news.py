"""Finnhub real-time financial news.

Free tier: 60 calls/min, real-time news from major wires.
Categories: general, forex, crypto, merger.
"""
from __future__ import annotations
import asyncio


async def fetch_finnhub_news(limit: int = 25) -> list[dict]:
    try:
        from shared.finnhub_client import market_news, normalize_news, is_available
    except ImportError:
        return []
    if not is_available():
        return []

    # Pull from multiple categories in parallel for breadth
    categories = ["general", "forex", "crypto", "merger"]
    per_cat = max(5, limit // len(categories))
    results = await asyncio.gather(
        *[market_news(category=cat, limit=per_cat) for cat in categories],
        return_exceptions=True,
    )

    items, seen_ids = [], set()
    for cat_articles in results:
        if isinstance(cat_articles, Exception):
            continue
        for article in cat_articles or []:
            normalized = normalize_news(article)
            if not normalized:
                continue
            if normalized["id"] in seen_ids:
                continue
            seen_ids.add(normalized["id"])
            items.append(normalized)

    # Finance filter (Finnhub is finance-focused but defensive anyway)
    try:
        from shared.finance_filter import finance_relevance, extract_tickers
        filtered = []
        for it in items[:limit]:
            is_rel, score, evidence = finance_relevance(it["title"], it["preview"])
            # Finnhub is finance-curated → lenient threshold
            if is_rel or score >= 0.30:
                it["finance_score"] = round(max(score, 0.70), 3)
                it["entities"]      = extract_tickers(f"{it['title']} {it['preview']}")
                it["evidence"]      = evidence[:6]
                filtered.append(it)
        return filtered
    except ImportError:
        return items[:limit]
