"""
Notion sync engine — Bloomberg Terminal edition.

Architecture:
  - Terminal header (status bar, market ticker, AI briefing, top stories)
    is REPLACED on every run via stored block IDs.
  - Article database is APPEND-ONLY — never flushed.
  - Deduplication by URL (notion-client 3.x data_sources.query API).
  - Auto-tagging from 50+ keyword signals.
  - Sector-aware article pages: layered like an information terminal.
"""

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from notion_client import Client
from notion_client.errors import APIResponseError

# ── Source metadata ───────────────────────────────────────────────────────────

SOURCE_META = {
    "hackernews":    {"label": "Hacker News",   "color": "orange",  "emoji": "🔥"},
    "arxiv":         {"label": "arXiv",          "color": "red",     "emoji": "🔬"},
    "reddit":        {"label": "Reddit",         "color": "orange",  "emoji": "💬"},
    "github":        {"label": "GitHub",         "color": "default", "emoji": "💻"},
    "rss":           {"label": "RSS",            "color": "purple",  "emoji": "📰"},
    "finance":       {"label": "Markets",        "color": "green",   "emoji": "📈"},
    "stackoverflow": {"label": "Stack Overflow", "color": "blue",    "emoji": "🧑‍💻"},
}

TAG_COLORS = {
    "ai": "blue", "research": "green", "tech": "gray",
    "code": "brown", "opensource": "yellow", "news": "pink",
    "community": "purple",
}

SECTOR_EMOJI = {
    "ai":      "🤖", "tech":    "💻", "science": "🔬",
    "world":   "🌍", "finance": "📈", "dev":     "🧑‍💻",
    "community": "💬",
}

# State file: stores Notion block IDs for the live terminal header
STATE_FILE = Path(__file__).parent / ".terminal_state.json"


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rich_text(text: str) -> list[dict]:
    chunks = [text[i:i+2000] for i in range(0, min(len(text), 6000), 2000)]
    return [{"type": "text", "text": {"content": c}} for c in chunks] if chunks else \
           [{"type": "text", "text": {"content": ""}}]


def _truncate(text: str, limit: int = 2000) -> str:
    return text[:limit] if text else ""


def _score_badge(score: float) -> str:
    if score >= 50: return "🔴"
    if score >= 30: return "🟠"
    if score >= 15: return "🟡"
    if score >= 8:  return "🟢"
    if score >= 3:  return "🔵"
    return "⚪"


# ── Auto-tagging ──────────────────────────────────────────────────────────────

_TOPIC_KW = {
    "ai":        ["ai", "llm", "gpt", "claude", "gemini", "neural", "transformer",
                  "machine learning", "deep learning", "openai", "anthropic", "mistral",
                  "llama", "diffusion", "embedding", "rag", "agent", "chatgpt", "ollama"],
    "research":  ["paper", "arxiv", "study", "research", "survey", "benchmark",
                  "dataset", "experiment", "findings", "analysis", "published", "journal"],
    "code":      ["python", "javascript", "typescript", "rust", "go", "c++",
                  "api", "library", "framework", "sdk", "cli", "compiler",
                  "algorithm", "refactor", "debugging", "open source"],
    "opensource": ["open source", "open-source", "github", "git", "repo",
                   "fork", "pull request", "mit license", "apache", "community"],
    "tech":      ["cloud", "kubernetes", "docker", "aws", "database", "sql",
                  "microservice", "devops", "infrastructure", "performance", "scaling"],
    "news":      ["launches", "announces", "released", "new version", "funding",
                  "acquisition", "ipo", "startup", "breaking"],
    "community": ["show hn", "ask hn", "discussion", "reddit", "feedback", "hiring"],
}


def _infer_tags(item: dict) -> list[str]:
    existing = set(item.get("tags") or [])
    text = ((item.get("title") or "") + " " + (item.get("preview") or "")).lower()
    inferred = set(existing)
    for tag, kws in _TOPIC_KW.items():
        if any(k in text for k in kws):
            inferred.add(tag)
    return [t for t in inferred if t in TAG_COLORS]


# ── Notion client ─────────────────────────────────────────────────────────────

def get_client() -> Client:
    token = os.getenv("NOTION_TOKEN")
    if not token:
        raise RuntimeError("NOTION_TOKEN not set in .env")
    return Client(auth=token)


# ── Database setup ────────────────────────────────────────────────────────────

DB_SCHEMA = {
    "Title":      {"title": {}},
    "Source":     {"select": {"options": [
        {"name": m["label"], "color": m["color"]} for m in SOURCE_META.values()
    ]}},
    "URL":        {"url": {}},
    "Score":      {"number": {"format": "number"}},
    "Sector":     {"select": {"options": [
        {"name": f"{e} {s.title()}", "color": "default"}
        for s, e in SECTOR_EMOJI.items()
    ]}},
    "Preview":    {"rich_text": {}},
    "AI Summary": {"rich_text": {}},
    "Meta":       {"rich_text": {}},
    "Tags":       {"multi_select": {"options": [
        {"name": t, "color": c} for t, c in TAG_COLORS.items()
    ]}},
    "Fetched":    {"date": {}},
    "Summarized": {"checkbox": {}},
}


def find_or_create_database(client: Client, parent_page_id: str) -> str:
    pinned = os.getenv("NOTION_DB_ID", "").replace("-", "").strip()
    if pinned:
        return pinned

    children = client.blocks.children.list(block_id=parent_page_id)
    for block in children.get("results", []):
        if block["type"] == "child_database":
            if "Daily Digest" in block["child_database"].get("title", ""):
                return block["id"]

    db = client.databases.create(
        parent={"type": "page_id", "page_id": parent_page_id},
        icon={"type": "emoji", "emoji": "📡"},
        title=[{"type": "text", "text": {"content": "Daily Digest — Feed"}}],
        properties=DB_SCHEMA,
    )
    return db["id"]


# ── Terminal header builder ───────────────────────────────────────────────────

def _build_status_block(meta: dict, total_db: int) -> dict:
    tod   = meta.get("time_of_day", "")
    ts    = datetime.now().strftime("%b %d  %H:%M")
    srcs  = len(meta.get("sources", []))
    clean = meta.get("total_clean", 0)
    return {
        "object": "block", "type": "callout",
        "callout": {
            "icon": {"type": "emoji", "emoji": "📡"},
            "color": "orange_background",
            "rich_text": _rich_text(
                f"INTELLIGENCE TERMINAL   ·   {tod.upper()} EDITION   ·   {ts}"
                f"   ·   {clean} new items across {srcs} sources   ·   {total_db} total in DB"
            ),
        },
    }


def _build_ticker_block(market_data: list[dict]) -> dict:
    """Build a Bloomberg-style market ticker callout."""
    if not market_data:
        return {"object": "block", "type": "callout",
                "callout": {"icon": {"type": "emoji", "emoji": "📈"},
                            "color": "gray_background",
                            "rich_text": _rich_text("Markets: data unavailable")}}

    # Separate indices, stocks, crypto
    indices = [m["market_data"] for m in market_data if m.get("market_data", {}).get("type") == "index"]
    stocks  = [m["market_data"] for m in market_data if m.get("market_data", {}).get("type") == "stock"]
    crypto  = [m["market_data"] for m in market_data if m.get("market_data", {}).get("type") == "crypto"]

    def fmt(d: dict) -> str:
        pct = d.get("change_pct", 0)
        arrow = d.get("arrow", "")
        color = "🟢" if pct >= 0 else "🔴"
        return f"{color} {d['name']}  {arrow}{abs(pct):.1f}%"

    parts = []
    if indices:
        parts.append("INDICES:  " + "   ".join(fmt(d) for d in indices[:3]))
    if stocks:
        parts.append("STOCKS:  " + "   ".join(fmt(d) for d in stocks[:5]))
    if crypto:
        parts.append("CRYPTO:  " + "   ".join(fmt(d) for d in crypto[:3]))

    # Overall market sentiment
    all_pcts = [m.get("market_data", {}).get("change_pct", 0) for m in market_data]
    avg_pct  = sum(all_pcts) / len(all_pcts) if all_pcts else 0
    sentiment = "🟢 RISK ON" if avg_pct > 0.5 else ("🔴 RISK OFF" if avg_pct < -0.5 else "🟡 MIXED")

    ticker_text = f"MARKET PULSE  [{sentiment}]\n" + "\n".join(parts)

    return {
        "object": "block", "type": "callout",
        "callout": {
            "icon": {"type": "emoji", "emoji": "📈"},
            "color": "green_background" if avg_pct >= 0 else "red_background",
            "rich_text": _rich_text(ticker_text),
        },
    }


def _build_briefing_block(briefing: str, trends: dict) -> list[dict]:
    blocks = []
    blocks.append({
        "object": "block", "type": "heading_2",
        "heading_2": {"rich_text": _rich_text("📰  BRIEFING")},
    })
    blocks.append({
        "object": "block", "type": "callout",
        "callout": {
            "icon": {"type": "emoji", "emoji": "🤖"},
            "color": "blue_background",
            "rich_text": _rich_text(_truncate(briefing, 1800) if briefing else "Briefing unavailable"),
        },
    })
    if trends.get("cross_source"):
        blocks.append({
            "object": "block", "type": "callout",
            "callout": {
                "icon": {"type": "emoji", "emoji": "📊"},
                "color": "purple_background",
                "rich_text": _rich_text("KEY TRENDS\n" + _truncate(trends["cross_source"], 800)),
            },
        })
    return blocks


def _build_top_stories(items: list[dict], n: int = 10) -> list[dict]:
    blocks = [{"object": "block", "type": "heading_2",
               "heading_2": {"rich_text": _rich_text("🔥  TOP STORIES NOW")}}]

    for i, item in enumerate(items[:n], 1):
        src    = SOURCE_META.get(item["source"], {})
        badge  = _score_badge(item.get("terminal_score", 0))
        score  = item.get("terminal_score", 0)
        title  = _truncate(item.get("title", "Untitled"), 100)
        url    = item.get("url", "")
        meta   = item.get("meta", src.get("label", ""))

        rich = [
            {"type": "text", "text": {"content": f"{badge} #{i}  "},
             "annotations": {"color": "gray"}},
        ]
        if url:
            rich.append({"type": "text",
                         "text": {"content": title, "link": {"url": url}},
                         "annotations": {"bold": True}})
        else:
            rich.append({"type": "text", "text": {"content": title},
                         "annotations": {"bold": True}})

        rich.append({"type": "text",
                     "text": {"content": f"  ·  {src.get('emoji','')} {meta}  ·  score {score}"},
                     "annotations": {"color": "gray"}})

        blocks.append({
            "object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": rich},
        })

    return blocks


def _build_sector_nav() -> list[dict]:
    """Build a sector navigation callout (links to filtered DB views)."""
    sectors = [
        ("🤖 AI & ML",      "ai"),
        ("💻 Tech & Dev",   "tech"),
        ("🔬 Science",      "science"),
        ("🌍 World News",   "world"),
        ("📈 Markets",      "finance"),
        ("💬 Community",    "community"),
    ]
    nav_text = "SECTOR FEEDS — filter the database below by tag:\n"
    nav_text += "  ·  ".join(f"{label}" for label, _ in sectors)
    return [{
        "object": "block", "type": "callout",
        "callout": {
            "icon": {"type": "emoji", "emoji": "🗂️"},
            "color": "gray_background",
            "rich_text": _rich_text(nav_text),
        },
    }]


# ── Terminal header refresh (replaces header on every run) ────────────────────

def refresh_terminal_header(
    client: Client,
    parent_page_id: str,
    meta: dict,
    market_data: list[dict],
    briefing: str,
    trends: dict,
    items: list[dict],
    total_db: int,
):
    """
    Replace all non-database, non-subpage blocks at the top of the page.
    Stores no state — safe to call multiple times per day.
    """
    # 1. Remove existing header blocks (preserve database + sub-pages)
    existing = client.blocks.children.list(block_id=parent_page_id)
    for block in existing.get("results", []):
        if block["type"] in ("child_database", "child_page"):
            continue
        try:
            client.blocks.delete(block_id=block["id"])
        except Exception:
            pass

    # 2. Build new terminal header
    header_blocks = [
        _build_status_block(meta, total_db),
        _build_ticker_block(market_data),
        {"object": "block", "type": "divider", "divider": {}},
    ]
    header_blocks.extend(_build_briefing_block(briefing, trends))
    header_blocks.append({"object": "block", "type": "divider", "divider": {}})
    header_blocks.extend(_build_top_stories(items, n=10))
    header_blocks.append({"object": "block", "type": "divider", "divider": {}})
    header_blocks.extend(_build_sector_nav())
    header_blocks.append({"object": "block", "type": "divider", "divider": {}})
    header_blocks.append({"object": "block", "type": "heading_2",
                          "heading_2": {"rich_text": _rich_text("📋  FULL FEED")}})

    # 3. Append in batches (Notion API limit: 100 blocks per call)
    for i in range(0, len(header_blocks), 100):
        client.blocks.children.append(
            block_id=parent_page_id,
            children=header_blocks[i:i+100],
        )


# ── Article page builder ──────────────────────────────────────────────────────

def _build_page_content(item: dict) -> list[dict]:
    src   = SOURCE_META.get(item["source"], {})
    score = item.get("terminal_score") or item.get("score") or 0
    badge = _score_badge(score)
    blocks = []

    # Header: source + link
    link_parts = []
    if item.get("url"):
        link_parts = [
            {"type": "text", "text": {"content": f"{src.get('emoji','📄')}  {src.get('label','Source')}   ·   "}},
            {"type": "text", "text": {"content": "Open article →", "link": {"url": item["url"]}},
             "annotations": {"bold": True, "color": "blue"}},
        ]
    else:
        link_parts = [{"type": "text", "text": {"content": f"{src.get('emoji','📄')}  {src.get('label','Source')}"}}]

    blocks.append({"object": "block", "type": "callout",
                   "callout": {"icon": {"type": "emoji", "emoji": src.get("emoji", "📄")},
                               "color": "gray_background", "rich_text": link_parts}})

    # Score + meta row
    meta_line = f"{badge} Terminal Score: {score}   ·   {item.get('meta', '')}"
    blocks.append({"object": "block", "type": "paragraph",
                   "paragraph": {"rich_text": [{"type": "text",
                                                "text": {"content": meta_line},
                                                "annotations": {"color": "gray"}}]}})

    blocks.append({"object": "block", "type": "divider", "divider": {}})

    # Preview content
    if item.get("preview"):
        blocks.append({"object": "block", "type": "heading_3",
                       "heading_3": {"rich_text": _rich_text("📝  Preview")}})
        for chunk in [_truncate(item["preview"], 1800)[i:i+400]
                      for i in range(0, min(len(item.get("preview","") or ""), 1800), 400)]:
            blocks.append({"object": "block", "type": "paragraph",
                           "paragraph": {"rich_text": _rich_text(chunk)}})
        blocks.append({"object": "block", "type": "divider", "divider": {}})

    # AI Summary
    blocks.append({"object": "block", "type": "heading_3",
                   "heading_3": {"rich_text": _rich_text("🤖  AI Analysis")}})
    if item.get("ai_summary"):
        blocks.append({"object": "block", "type": "callout",
                       "callout": {"icon": {"type": "emoji", "emoji": "🤖"},
                                   "color": "blue_background",
                                   "rich_text": _rich_text(_truncate(item["ai_summary"], 1800))}})
    else:
        blocks.append({"object": "block", "type": "paragraph",
                       "paragraph": {"rich_text": [{"type": "text",
                                                    "text": {"content": "Run with --summarize to generate AI analysis"},
                                                    "annotations": {"italic": True, "color": "gray"}}]}})

    return blocks


# ── Deduplication query ───────────────────────────────────────────────────────

def _get_existing_today(client: Client, db_id: str) -> tuple[set, set]:
    """Return (existing_urls, existing_titles) fetched today."""
    existing_urls: set[str]   = set()
    existing_titles: set[str] = set()
    try:
        ds_id = os.getenv("NOTION_DS_ID", "").replace("-", "").strip()
        if not ds_id:
            db_meta = client.databases.retrieve(database_id=db_id)
            ds_id = db_meta["data_sources"][0]["id"].replace("-", "")

        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        results = client.data_sources.query(
            data_source_id=ds_id,
            filter={"property": "Fetched", "date": {"on_or_after": today_start.isoformat()}},
        )
        for page in results.get("results", []):
            props = page.get("properties", {})
            url_val = props.get("URL", {}).get("url") or ""
            if url_val:
                existing_urls.add(url_val.rstrip("/"))
            title_arr = props.get("Title", {}).get("title", [])
            if title_arr:
                existing_titles.add(title_arr[0]["plain_text"])
    except Exception:
        pass
    return existing_urls, existing_titles


def _count_db(client: Client, db_id: str) -> int:
    """Approximate total item count in the database."""
    try:
        ds_id = os.getenv("NOTION_DS_ID", "").replace("-", "").strip()
        if not ds_id:
            db_meta = client.databases.retrieve(database_id=db_id)
            ds_id = db_meta["data_sources"][0]["id"].replace("-", "")
        results = client.data_sources.query(data_source_id=ds_id, page_size=1)
        # Notion doesn't give total count directly — use has_more as proxy
        return -1  # unknown
    except Exception:
        return -1


# ── Main push function ────────────────────────────────────────────────────────

def push_items_to_notion(
    client: Client,
    db_id: str,
    items: list[dict],
    skip_existing: bool = True,
) -> dict:
    """Push pipeline items to Notion. Returns {created, skipped, errors}."""
    stats = {"created": 0, "skipped": 0, "errors": 0}

    existing_urls, existing_titles = _get_existing_today(client, db_id) if skip_existing else (set(), set())

    for item in items:
        # Skip finance ticker items — they go in the header, not the DB
        if item.get("source") == "finance":
            continue

        title   = _truncate(item.get("title", "Untitled"), 250)
        item_url = (item.get("url") or "").rstrip("/")

        if not title:
            continue
        if item_url and item_url in existing_urls:
            stats["skipped"] += 1
            continue
        if not item_url and title in existing_titles:
            stats["skipped"] += 1
            continue

        src      = SOURCE_META.get(item["source"], {})
        tags     = [{"name": t} for t in _infer_tags(item)]
        sector   = item.get("sector", "")
        sec_label = f"{SECTOR_EMOJI.get(sector, '')} {sector.title()}" if sector else ""

        properties = {
            "Title":   {"title": _rich_text(title)},
            "Source":  {"select": {"name": src.get("label", item["source"])}},
            "URL":     {"url": item_url or None},
            "Score":   {"number": item.get("terminal_score") or item.get("score") or 0},
            "Preview": {"rich_text": _rich_text(_truncate(item.get("preview", ""), 1800))},
            "Meta":    {"rich_text": _rich_text(_truncate(item.get("meta", ""), 500))},
            "Tags":    {"multi_select": tags},
            "Fetched": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
            "Summarized": {"checkbox": bool(item.get("ai_summary"))},
        }
        if sec_label:
            properties["Sector"] = {"select": {"name": sec_label}}
        if item.get("ai_summary"):
            properties["AI Summary"] = {"rich_text": _rich_text(_truncate(item["ai_summary"], 1800))}

        try:
            client.pages.create(
                parent={"database_id": db_id},
                icon={"type": "emoji", "emoji": src.get("emoji", "📄")},
                properties=properties,
                children=_build_page_content(item),
            )
            if item_url:
                existing_urls.add(item_url)
            existing_titles.add(title)
            stats["created"] += 1
        except APIResponseError as e:
            print(f"  ✗ Notion error on '{title[:40]}': {e.code}")
            stats["errors"] += 1
        except Exception as e:
            print(f"  ✗ Error: {e}")
            stats["errors"] += 1

    return stats


# ── Daily brief sub-page ──────────────────────────────────────────────────────

def update_daily_brief(
    client: Client,
    parent_page_id: str,
    items: list[dict],
    stats: dict,
    briefing: str = "",
):
    """Create or update today's brief sub-page under the dashboard."""
    today = datetime.now().strftime("%B %d, %Y")
    brief_title = f"📅 Brief — {today}"
    tod = datetime.now().strftime("%H:%M")

    # Find existing brief for today
    children = client.blocks.children.list(block_id=parent_page_id)
    existing_brief_id = None
    for block in children.get("results", []):
        if block["type"] == "child_page":
            if block["child_page"].get("title", "") == brief_title:
                existing_brief_id = block["id"]
                break

    # Group by source, sort by terminal_score
    by_source: dict = defaultdict(list)
    for item in items:
        if item.get("source") != "finance":
            by_source[item["source"]].append(item)
    for src in by_source:
        by_source[src].sort(key=lambda x: x.get("terminal_score", 0), reverse=True)

    blocks: list[dict] = []

    # Stats
    blocks.append({"object": "block", "type": "callout",
                   "callout": {"icon": {"type": "emoji", "emoji": "📊"},
                               "color": "green_background",
                               "rich_text": _rich_text(
                                   f"Updated {tod}  ·  {stats['created']} new  ·  "
                                   f"{stats['skipped']} skipped  ·  {stats['errors']} errors  ·  "
                                   f"{sum(len(v) for v in by_source.values())} articles total"
                               )}})

    if briefing:
        blocks.append({"object": "block", "type": "callout",
                       "callout": {"icon": {"type": "emoji", "emoji": "🤖"},
                                   "color": "blue_background",
                                   "rich_text": _rich_text(_truncate(briefing, 1500))}})

    blocks.append({"object": "block", "type": "divider", "divider": {}})

    # Top 5 per source
    SOURCE_ORDER = ["hackernews", "github", "arxiv", "reddit", "rss", "stackoverflow"]
    for src_key in SOURCE_ORDER:
        src_items = by_source.get(src_key, [])[:5]
        if not src_items:
            continue
        src = SOURCE_META[src_key]
        blocks.append({"object": "block", "type": "heading_2",
                       "heading_2": {"rich_text": _rich_text(
                           f"{src['emoji']} {src['label']} — Top {len(src_items)}"
                       )}})
        for item in src_items:
            score  = item.get("terminal_score", 0)
            badge  = _score_badge(score)
            title  = _truncate(item.get("title", ""), 80)
            url    = item.get("url", "")
            rich   = [{"type": "text", "text": {"content": f"{badge} "},
                       "annotations": {"color": "gray"}}]
            if url:
                rich.append({"type": "text",
                             "text": {"content": title, "link": {"url": url}},
                             "annotations": {"bold": True}})
            else:
                rich.append({"type": "text", "text": {"content": title},
                             "annotations": {"bold": True}})

            blocks.append({"object": "block", "type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": rich}})
            if item.get("preview"):
                snippet = _truncate(item["preview"].replace("\n", " "), 100)
                blocks.append({"object": "block", "type": "paragraph",
                               "paragraph": {"rich_text": [
                                   {"type": "text", "text": {"content": f"   {snippet}…"},
                                    "annotations": {"italic": True, "color": "gray"}}
                               ]}})

    # Write to Notion
    if existing_brief_id:
        old = client.blocks.children.list(block_id=existing_brief_id)
        for b in old.get("results", []):
            try:
                client.blocks.delete(block_id=b["id"])
            except Exception:
                pass
        for i in range(0, len(blocks), 100):
            client.blocks.children.append(block_id=existing_brief_id, children=blocks[i:i+100])
    else:
        page = client.pages.create(
            parent={"page_id": parent_page_id},
            icon={"type": "emoji", "emoji": "📅"},
            properties={"title": [{"type": "text", "text": {"content": brief_title}}]},
            children=blocks[:100],
        )
        for i in range(100, len(blocks), 100):
            client.blocks.children.append(block_id=page["id"], children=blocks[i:i+100])
