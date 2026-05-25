"""
RSS source — 25+ feeds organized into 5 sectors.
Each item carries a `sector` field used by the terminal layout.
"""

import asyncio
import re
import feedparser
from typing import Optional

# ── Sector-organized feed registry ───────────────────────────────────────────
#  Format: (display_name, url, sector, base_score_boost)

FEED_REGISTRY = [
    # ── World News ──────────────────────────────────────────────────────────
    ("Reuters World",    "https://feeds.reuters.com/Reuters/worldNews",              "world",    5),
    ("Reuters Tech",     "https://feeds.reuters.com/reuters/technologyNews",          "world",    4),
    ("BBC World",        "http://feeds.bbci.co.uk/news/world/rss.xml",              "world",    5),
    ("BBC Tech",         "http://feeds.bbci.co.uk/news/technology/rss.xml",         "tech",     4),
    ("Guardian World",   "https://www.theguardian.com/world/rss",                   "world",    3),
    ("NPR News",         "https://feeds.npr.org/1001/rss.xml",                      "world",    3),

    # ── Tech & Developer ────────────────────────────────────────────────────
    ("TechCrunch",       "https://techcrunch.com/feed/",                            "tech",     5),
    ("Ars Technica",     "http://feeds.arstechnica.com/arstechnica/index",          "tech",     4),
    ("The Verge",        "https://www.theverge.com/rss/index.xml",                  "tech",     4),
    ("Wired",            "https://www.wired.com/feed/rss",                          "tech",     3),
    ("VentureBeat",      "https://venturebeat.com/feed/",                           "tech",     3),

    # ── AI & Machine Learning ───────────────────────────────────────────────
    ("MIT Tech Review",  "https://www.technologyreview.com/feed/",                  "ai",       5),
    ("Hugging Face",     "https://huggingface.co/blog/feed.xml",                    "ai",       5),
    ("OpenAI Blog",      "https://openai.com/news/rss/",                            "ai",       5),
    ("DeepMind",         "https://www.deepmind.com/blog/rss.xml",                   "ai",       4),

    # ── Science & Research ──────────────────────────────────────────────────
    ("Nature News",      "https://www.nature.com/news.rss",                         "science",  5),
    ("Science Daily",    "https://www.sciencedaily.com/rss/top/science.xml",        "science",  4),
    ("Phys.org",         "https://phys.org/rss-feed/",                              "science",  3),
    ("New Scientist",    "https://www.newscientist.com/feed/home/",                 "science",  3),

    # ── Finance & Markets ───────────────────────────────────────────────────
    ("CNBC Tech",        "https://www.cnbc.com/id/19854910/device/rss/rss.html",   "finance",  4),
]

SECTOR_TAGS = {
    "world":   ["news"],
    "tech":    ["tech", "news"],
    "ai":      ["ai", "tech"],
    "science": ["research", "news"],
    "finance": ["news"],
    "dev":     ["code", "tech"],
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

    return await asyncio.to_thread(_parse_all)
