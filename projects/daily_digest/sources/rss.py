"""RSS source — finance/markets-only feed registry.

Curated wire/financial-media feeds. NO general news, NO tech blogs,
NO science. Bloomberg-style terminal scope.
"""

import asyncio
import re
import feedparser
from typing import Optional

# ── Finance-only feed registry — wire services + financial media ────────────
#  Format: (display_name, url, sector, base_score_boost)

FEED_REGISTRY = [
    # ── Wire services (highest credibility) ─────────────────────────────────
    ("Reuters Business",    "https://www.reuters.com/business/feed/",                     "finance",  8),
    ("Reuters Markets",     "https://www.reuters.com/markets/us/feed/",                   "finance",  8),
    ("Bloomberg Markets",   "https://feeds.bloomberg.com/markets/news.rss",               "finance",  8),
    ("Bloomberg Wealth",    "https://feeds.bloomberg.com/wealth/news.rss",                "finance",  7),
    ("Bloomberg Economics", "https://feeds.bloomberg.com/economics/news.rss",             "finance",  8),
    ("FT Markets",          "https://www.ft.com/markets?format=rss",                      "finance",  7),
    ("FT Companies",        "https://www.ft.com/companies?format=rss",                    "finance",  6),

    # ── Financial media ─────────────────────────────────────────────────────
    ("WSJ Markets",         "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",              "finance",  7),
    ("WSJ Business",        "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml",            "finance",  6),
    ("CNBC Top News",       "https://www.cnbc.com/id/100003114/device/rss/rss.html",      "finance",  6),
    ("CNBC Markets",        "https://www.cnbc.com/id/15839135/device/rss/rss.html",       "finance",  6),
    ("CNBC Investing",      "https://www.cnbc.com/id/15839069/device/rss/rss.html",       "finance",  5),
    ("CNBC Economy",        "https://www.cnbc.com/id/20910258/device/rss/rss.html",       "finance",  5),
    ("MarketWatch Top",     "https://feeds.marketwatch.com/marketwatch/topstories/",      "finance",  5),
    ("MarketWatch Bulletins","https://feeds.marketwatch.com/marketwatch/bulletins/",      "finance",  5),
    ("Yahoo Finance",       "https://finance.yahoo.com/news/rssindex",                    "finance",  4),

    # ── Regulator + central bank ────────────────────────────────────────────
    ("SEC Press Releases",  "https://www.sec.gov/news/pressreleases.rss",                 "finance",  9),
    ("Fed Reserve Press",   "https://www.federalreserve.gov/feeds/press_all.xml",         "finance",  9),

    # ── Sector-specific finance ─────────────────────────────────────────────
    ("CoinDesk",            "https://www.coindesk.com/arc/outboundfeeds/rss/",            "crypto",   5),
    ("Decrypt",             "https://decrypt.co/feed",                                    "crypto",   4),
]

SECTOR_TAGS = {
    "finance": ["finance", "markets"],
    "crypto":  ["crypto"],
}


async def fetch_rss(
    feeds: Optional[list] = None,
    limit: int = 5,
    sector: Optional[str] = None,
) -> list[dict]:
    """
    Fetch all RSS feeds (or a subset by sector).
    `limit` = max items per feed.
    """
    if feeds is not None:
        registry = [(n, u, "rss", 0) for n, u in feeds]
    elif sector:
        registry = [(n, u, s, b) for n, u, s, b in FEED_REGISTRY if s == sector]
    else:
        registry = FEED_REGISTRY

    def _parse_all():
        items = []
        for name, url, sec, boost in registry:
            try:
                d = feedparser.parse(url)
                for entry in d.entries[:limit]:
                    raw   = entry.get("summary", entry.get("description", ""))
                    clean = re.sub(r"<[^>]+>", "", raw).strip()
                    pub   = entry.get("published", "")
                    items.append({
                        "id":      f"rss-{abs(hash(entry.get('link', '') + name))}",
                        "source":  "rss",
                        "title":   entry.get("title", "").strip(),
                        "url":     entry.get("link", ""),
                        "score":   boost,
                        "preview": clean[:400] + ("…" if len(clean) > 400 else ""),
                        "meta":    name + (f"  ·  {pub[:16]}" if pub else ""),
                        "tags":    SECTOR_TAGS.get(sec, ["news"]),
                        "sector":  sec,
                    })
            except Exception:
                continue
        return items

    items = await asyncio.to_thread(_parse_all)

    # Safety net: even from finance feeds, drop items with off-topic titles
    try:
        from shared.finance_filter import finance_relevance, extract_tickers
        filtered = []
        for it in items:
            is_rel, score, _ = finance_relevance(it.get("title", ""), it.get("preview", ""))
            # Lenient — feed is already finance-curated, but kill obvious non-finance leakage
            if is_rel or score >= 0.3:
                it["finance_score"] = round(max(score, 0.5), 3)
                it["entities"]      = extract_tickers(f"{it.get('title','')} {it.get('preview','')}")
                filtered.append(it)
        return filtered
    except ImportError:
        return items
