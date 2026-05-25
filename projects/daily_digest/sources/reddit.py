"""
Reddit source — sector-organized subreddits.
Fetches top posts of the day from high-signal communities.
"""

import httpx
from typing import Optional

HEADERS = {"User-Agent": "DailyDigest/2.0 (personal automation; contact via github)"}

# Finance-only subreddits — high-signal investor/trader communities
SUBREDDIT_SECTORS = {
    "finance":   ["investing", "stocks", "StockMarket", "SecurityAnalysis",
                  "ValueInvesting", "Bogleheads", "dividends", "ETFs"],
    "trading":   ["options", "thetagang", "Daytrading", "wallstreetbets",
                  "algotrading", "quant"],
    "crypto":    ["CryptoCurrency", "CryptoMarkets", "Bitcoin", "ethfinance"],
    "macro":     ["economy", "Economics", "geopolitics"],
    "intl":      ["IndianStockMarket", "ASX_Bets", "CanadianInvestor"],
}

# Default: top finance + trading subs only — no general AI/tech/science/world
DEFAULT_SUBREDDITS = (
    SUBREDDIT_SECTORS["finance"][:4] +
    SUBREDDIT_SECTORS["trading"][:3] +
    SUBREDDIT_SECTORS["crypto"][:2]
)


async def fetch_reddit(
    subreddits: Optional[list] = None,
    limit: int = 10,
    sector: Optional[str] = None,
) -> list[dict]:
    if sector and sector in SUBREDDIT_SECTORS:
        subs = SUBREDDIT_SECTORS[sector]
    elif subreddits:
        subs = subreddits
    else:
        subs = DEFAULT_SUBREDDITS

    items = []
    async with httpx.AsyncClient(timeout=12, headers=HEADERS) as client:
        for sub in subs:
            try:
                url  = f"https://www.reddit.com/r/{sub}/top.json?limit={limit}&t=day"
                data = (await client.get(url)).json()
                for post in data.get("data", {}).get("children", []):
                    p = post["data"]
                    if p.get("stickied"):
                        continue
                    if p.get("is_self") and not p.get("selftext", "").strip():
                        continue

                    score   = p.get("score", 0)
                    comments = p.get("num_comments", 0)
                    flair   = p.get("link_flair_text") or ""
                    selftext = (p.get("selftext") or "")[:250].strip()
                    preview = f"r/{sub}  ·  ▲{score:,}  ·  {comments} comments"
                    if flair:
                        preview += f"  ·  [{flair}]"
                    if selftext:
                        preview += f"\n{selftext}"

                    # Determine which sector this subreddit belongs to
                    sub_sector = next(
                        (s for s, sl in SUBREDDIT_SECTORS.items() if sub in sl),
                        "tech"
                    )

                    items.append({
                        "id":      f"reddit-{p['id']}",
                        "source":  "reddit",
                        "title":   p.get("title", ""),
                        "url":     p.get("url") or f"https://reddit.com{p.get('permalink','')}",
                        "score":   score,
                        "preview": preview,
                        "meta":    f"r/{sub}",
                        "tags":    ["community"],
                        "sector":  sub_sector,
                    })
            except Exception:
                continue


    # Safety net: even with finance subs, some posts are off-topic — filter
    try:
        from shared.finance_filter import finance_relevance, extract_tickers
        filtered = []
        for it in items:
            is_rel, score, _ = finance_relevance(it.get("title", ""), it.get("preview", ""))
            # Accept anything from these subs with score ≥ 0.3 (lenient — subreddit
            # itself is already a finance filter)
            if is_rel or score >= 0.3:
                it["finance_score"] = round(max(score, 0.5), 3)
                it["entities"]      = extract_tickers(f"{it.get('title','')} {it.get('preview','')}")
                filtered.append(it)
        return filtered
    except ImportError:
        return items
