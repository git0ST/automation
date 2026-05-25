"""HackerNews — top/best stories filtered for finance/markets relevance.

Without filtering, HN's top stories drift to general tech/world content
(e.g. religion, hobbies). We over-fetch then apply a strict finance
relevance filter so only markets-relevant content reaches the feed.
"""
import asyncio
import httpx

HN_TOP  = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_BEST = "https://hacker-news.firebaseio.com/v0/beststories.json"
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"

# Over-fetch then filter; HN's signal-to-finance ratio is ~1:8 on average
OVERFETCH_MULTIPLIER = 8


async def fetch_hackernews(limit: int = 15) -> list[dict]:
    fetch_count = limit * OVERFETCH_MULTIPLIER
    try:
        from shared.finance_filter import finance_relevance, extract_tickers
    except ImportError:
        finance_relevance = None

    async with httpx.AsyncClient(timeout=15) as client:
        # Best stories prioritized over top — higher quality signal
        try:
            best_ids = (await client.get(HN_BEST)).json()[:fetch_count]
        except Exception:
            best_ids = []
        try:
            top_ids = (await client.get(HN_TOP)).json()[:fetch_count]
        except Exception:
            top_ids = []

        seen, ids = set(), []
        for sid in best_ids + top_ids:
            if sid not in seen:
                seen.add(sid)
                ids.append(sid)
            if len(ids) >= fetch_count:
                break

        results = await asyncio.gather(
            *[_fetch_story(client, sid) for sid in ids],
            return_exceptions=True,
        )

    items = []
    for r in results:
        if isinstance(r, Exception) or not r:
            continue
        if finance_relevance:
            is_rel, score, evidence = finance_relevance(r.get("title", ""), r.get("preview", ""))
            if not is_rel:
                continue
            r["finance_score"] = round(score, 3)
            r["entities"]      = extract_tickers(f"{r.get('title','')} {r.get('preview','')}")
        items.append(r)
        if len(items) >= limit:
            break

    return items


async def _fetch_story(client: httpx.AsyncClient, story_id: int) -> dict | None:
    try:
        s = (await client.get(HN_ITEM.format(story_id))).json()
        if not s or s.get("type") != "story" or not s.get("url"):
            return None
        return {
            "id":      f"hn-{story_id}",
            "source":  "hackernews",
            "title":   s.get("title", ""),
            "url":     s.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
            "score":   s.get("score", 0),
            "preview": f"{s.get('score', 0)} points · {s.get('descendants', 0)} comments",
            "tags":    ["tech"],
        }
    except Exception:
        return None
