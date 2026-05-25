import httpx
import xml.etree.ElementTree as ET

ARXIV_URL = "https://export.arxiv.org/api/query"
NS = "http://www.w3.org/2005/Atom"


async def fetch_arxiv(query: str = "cat:cs.LG+OR+cat:cs.AI", limit: int = 10) -> list[dict]:
    params = {
        "search_query": query,
        "start": 0,
        "max_results": limit,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(ARXIV_URL, params=params)
    root = ET.fromstring(resp.text)
    items = []
    for entry in root.findall(f"{{{NS}}}entry"):
        title   = (entry.findtext(f"{{{NS}}}title") or "").replace("\n", " ").strip()
        summary = (entry.findtext(f"{{{NS}}}summary") or "").replace("\n", " ").strip()
        url     = entry.findtext(f"{{{NS}}}id") or ""
        authors = [a.findtext(f"{{{NS}}}name") for a in entry.findall(f"{{{NS}}}author")][:3]
        items.append({
            "id":      f"arxiv-{url.split('/')[-1]}",
            "source":  "arxiv",
            "title":   title,
            "url":     url,
            "score":   0,
            "preview": summary[:300] + ("…" if len(summary) > 300 else ""),
            "meta":    ", ".join(a for a in authors if a),
            "tags":    ["ai", "research"],
        })
    return items
