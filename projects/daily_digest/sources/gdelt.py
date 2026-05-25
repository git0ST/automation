"""
GDELT Project — World's largest open database of human society.

Updates every 15 minutes. No API key. No rate limit (reasonable use).
Rivals: Bloomberg News Analytics, Refinitiv News Sentiment.

DOC 2.0 API: full-text search across 100+ languages with:
  - Entity extraction (people, organizations, locations)
  - Tone/sentiment scoring
  - Geolocation
  - CAMEO event codes
"""

import httpx
from datetime import datetime, timezone

DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"

QUERIES = [
    ("AI market economy", "ai_economy"),
    ("Federal Reserve inflation interest rate", "macro"),
    ("merger acquisition earnings guidance", "corporate"),
    ("geopolitical crisis energy supply", "geo"),
    ("technology breakthrough innovation", "tech"),
]


async def _query_gdelt(client: httpx.AsyncClient, query: str, tag: str, n: int) -> list[dict]:
    try:
        params = {
            "query":      query,
            "mode":       "artlist",
            "format":     "json",
            "maxrecords": str(n),
            "timespan":   "4h",
            "sort":       "ToneDesc",
        }
        r = await client.get(DOC_API, params=params, timeout=12)
        if r.status_code != 200:
            return []
        data = r.json()
        articles = data.get("articles", [])
        items = []
        for a in articles:
            title = (a.get("title") or "").strip()
            url   = (a.get("url") or "").strip()
            if not title or not url:
                continue
            tone = float(a.get("tone", 0) or 0)
            sentiment = "bullish" if tone > 2 else "bearish" if tone < -2 else "neutral"
            items.append({
                "id":              f"gdelt-{hash(url) & 0xFFFFFF}",
                "source":         "gdelt",
                "title":          title[:200],
                "url":            url,
                "score":          max(0, int(abs(tone) * 3)),
                "preview":        (a.get("seendescription") or "")[:300],
                "meta":           f"GDELT · {a.get('domain','')[:30]}",
                "tags":           ["world", tag],
                "sector":         "world",
                "sentiment_score": round(tone / 10, 4),
                "sentiment_label": sentiment,
                "entities":       [],
                "gdelt_tone":     tone,
                "gdelt_domain":   a.get("domain", ""),
                "gdelt_lang":     a.get("language", "English"),
            })
        return items
    except Exception:
        return []


async def fetch_gdelt(limit: int = 25) -> list[dict]:
    import asyncio
    per_query = max(3, limit // len(QUERIES))
    async with httpx.AsyncClient(timeout=14) as client:
        results = await asyncio.gather(
            *[_query_gdelt(client, q, tag, per_query) for q, tag in QUERIES],
            return_exceptions=True,
        )

    seen, items = set(), []
    for batch in results:
        if isinstance(batch, list):
            for item in batch:
                if item["url"] not in seen:
                    seen.add(item["url"])
                    items.append(item)
    return items[:limit]
