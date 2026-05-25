"""
Stack Overflow — hot questions via the Stack Exchange API (free, no key needed).
Gives developer-pulse signal: what problems engineers are solving right now.
"""

import httpx

SO_API = "https://api.stackexchange.com/2.3/questions"


async def fetch_stackoverflow(limit: int = 15) -> list[dict]:
    params = {
        "order":    "desc",
        "sort":     "hot",
        "site":     "stackoverflow",
        "pagesize": limit,
        "filter":   "!nNPvSNdWme",   # include body_markdown + tags
    }
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(SO_API, params=params,
                                 headers={"Accept-Encoding": "gzip"})
            if r.status_code != 200:
                return []
            data = r.json()

        items = []
        for q in data.get("items", [])[:limit]:
            tags    = q.get("tags", [])[:4]
            score   = q.get("score", 0)
            answers = q.get("answer_count", 0)
            views   = q.get("view_count", 0)
            title   = q.get("title", "")
            link    = q.get("link", "")

            items.append({
                "id":      f"so-{q.get('question_id', abs(hash(title)))}",
                "source":  "stackoverflow",
                "title":   title,
                "url":     link,
                "score":   score,
                "preview": (
                    f"{score} votes  ·  {answers} answers  ·  {views:,} views\n"
                    + (q.get("body_markdown") or "")[:200].replace("\n", " ").strip()
                ),
                "meta":    " · ".join(tags),
                "tags":    ["code", "tech"],
            })
        return items
    except Exception:
        return []
