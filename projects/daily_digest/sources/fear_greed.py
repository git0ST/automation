"""
Fear & Greed index.

Crypto F&G: alternative.me free API (no key, updates daily).
Stock market sentiment: derived from VIX level fetched from FRED.
"""

import httpx

CRYPTO_FG_URL = "https://api.alternative.me/fng/?limit=1&format=json"


def _label(v: int) -> str:
    if v <= 25: return "Extreme Fear"
    if v <= 45: return "Fear"
    if v <= 55: return "Neutral"
    if v <= 75: return "Greed"
    return "Extreme Greed"


async def fetch_fear_greed(limit: int = 5) -> list[dict]:
    items = []

    # Crypto Fear & Greed (alternative.me — no key)
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(CRYPTO_FG_URL)
            if r.status_code == 200:
                d = r.json()
                entry = d["data"][0]
                val = int(entry["value"])
                lbl = entry.get("value_classification", _label(val))
                items.append({
                    "id":      "fg-crypto",
                    "source":  "fear_greed",
                    "title":   f"Crypto Fear & Greed: {val}/100 — {lbl}",
                    "url":     "https://alternative.me/crypto/fear-and-greed-index/",
                    "score":   val,
                    "preview": f"Crypto market sentiment: {val}/100 ({lbl}).",
                    "meta":    "Sentiment · Crypto",
                    "tags":    ["sentiment", "crypto"],
                    "sector":  "finance",
                    "fear_greed": {"value": val, "label": lbl, "source": "crypto"},
                })
    except Exception:
        pass

    # Stock Market Fear & Greed (CNN scrape via fear-and-greed package)
    try:
        import fear_and_greed
        fg = fear_and_greed.get()
        val = int(fg.value)
        lbl = fg.description
        items.append({
            "id":      "fg-stocks",
            "source":  "fear_greed",
            "title":   f"Stock Market Fear & Greed: {val}/100 — {lbl}",
            "url":     "https://edition.cnn.com/markets/fear-and-greed",
            "score":   val,
            "preview": f"CNN Fear & Greed Index: {val}/100 ({lbl}). Updated {fg.last_update.strftime('%H:%M')}.",
            "meta":    "Sentiment · Equities",
            "tags":    ["sentiment", "stocks"],
            "sector":  "finance",
            "fear_greed": {"value": val, "label": lbl, "source": "stocks"},
        })
    except Exception:
        pass

    return items
