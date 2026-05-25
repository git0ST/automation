import httpx

HN_TOP = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"


async def fetch_hackernews(limit: int = 15) -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as client:
        ids = (await client.get(HN_TOP)).json()[:limit]
        items = []
        for story_id in ids:
            try:
                s = (await client.get(HN_ITEM.format(story_id))).json()
                if s and s.get("type") == "story" and s.get("url"):
                    items.append({
                        "id":      f"hn-{story_id}",
                        "source":  "hackernews",
                        "title":   s.get("title", ""),
                        "url":     s.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
                        "score":   s.get("score", 0),
                        "preview": f"{s.get('score', 0)} points · {s.get('descendants', 0)} comments",
                        "tags":    ["tech"],
                    })
            except Exception:
                continue
    return items
