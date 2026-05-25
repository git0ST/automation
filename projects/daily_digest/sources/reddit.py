"""
Reddit source — sector-organized subreddits.
Fetches top posts of the day from high-signal communities.
"""

import httpx
from typing import Optional

HEADERS = {"User-Agent": "DailyDigest/2.0 (personal automation; contact via github)"}

# Subreddits organized by sector
SUBREDDIT_SECTORS = {
    "ai":       ["MachineLearning", "LocalLLaMA", "artificial", "AINews", "singularity"],
    "tech":     ["technology", "programming", "softwareengineering", "compsci"],
    "science":  ["science", "datascience", "Physics", "biology"],
    "world":    ["worldnews", "geopolitics"],
    "finance":  ["investing", "StockMarket", "CryptoCurrency"],
    "dev":      ["learnprogramming", "webdev", "devops"],
}

DEFAULT_SUBREDDITS = (
    SUBREDDIT_SECTORS["ai"][:3] +
    SUBREDDIT_SECTORS["tech"][:2] +
    SUBREDDIT_SECTORS["science"][:1] +
    SUBREDDIT_SECTORS["world"][:1]
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

    return items
