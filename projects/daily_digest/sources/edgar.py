"""
SEC EDGAR — Real-time regulatory intelligence (no API key required).

Sources:
  Form 4   — Insider trades (officers, directors, 10%+ shareholders)
             Filed within 2 business days of transaction. Pure alpha.
  8-K      — Material corporate events: M&A, CEO changes, earnings,
             bankruptcy, FDA approvals, contract wins.

EDGAR rate limit: 10 req/sec. User-Agent header required by SEC policy.
"""

import feedparser
import httpx
import re
from datetime import datetime, timezone, timedelta

HEADERS = {"User-Agent": "IntelligenceTerminal/2.0 contact@intl.local"}

FORM4_FEED  = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&dateb=&owner=include&count=40&search_text=&output=atom"
EIGHTK_FEED = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&dateb=&owner=include&count=40&search_text=&output=atom"

# 8-K item codes that signal the most market-moving events
HIGH_PRIORITY_8K = {
    "1.01": "Material Agreement",
    "1.03": "Bankruptcy",
    "2.01": "Acquisition/Disposal",
    "2.02": "Earnings Results",
    "2.05": "Departure/Appointment",
    "3.01": "Delisting",
    "4.01": "Auditor Change",
    "5.02": "Director/Officer Change",
    "7.01": "Regulation FD",
    "8.01": "Other Material Event",
}


def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())[:280]


async def _fetch_feed(url: str, label: str, limit: int) -> list[dict]:
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=12) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return []
        feed = feedparser.parse(r.text)
        items = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=36)

        for entry in feed.entries[:limit]:
            title   = _clean_text(entry.get("title", ""))
            link    = entry.get("link", "")
            summary = _clean_text(entry.get("summary", ""))
            if not title:
                continue

            # Parse published date
            pub = None
            try:
                pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                if pub < cutoff:
                    continue
            except Exception:
                pass

            items.append({
                "id":      f"edgar-{label}-{hash(link) & 0xFFFFFF}",
                "source":  "edgar",
                "subtype": label,
                "title":   title,
                "url":     link,
                "score":   0,
                "preview": summary,
                "meta":    f"SEC EDGAR · {label.upper()}",
                "tags":    ["regulatory", "sec", label.lower()],
                "sector":  "finance",
                "published_at": pub.isoformat() if pub else None,
            })
        return items
    except Exception:
        return []


async def fetch_edgar(limit: int = 30) -> list[dict]:
    import asyncio

    form4_task  = _fetch_feed(FORM4_FEED,  "Form4",  limit // 2)
    eightk_task = _fetch_feed(EIGHTK_FEED, "8-K",    limit // 2)

    form4_items, eightk_items = await asyncio.gather(form4_task, eightk_task)

    # Tag 8-K priority from known item codes
    for item in eightk_items:
        for code, label in HIGH_PRIORITY_8K.items():
            if code in item["title"] or label.lower() in item["title"].lower():
                item["tags"].append("high-priority")
                item["score"] = 5
                break

    return form4_items + eightk_items
