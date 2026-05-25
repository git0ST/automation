"""
Intelligence Terminal — Multi-agent pipeline.

Stages:
  1. FETCH       — parallel async ingestion from all sources
  2. FILTER      — deduplicate, remove junk
  3. SCORE       — composite terminal_score
  4. SENTIMENT   — VADER for all items, entity extraction
  5. INTELLIGENCE— Regime detection + Systemic Risk Score (Aladdin-inspired)
  6. ANALYZE     — Ollama cross-source trend analysis  (run_ai=True)
  7. BRIEF       — Ollama editorial briefing           (run_ai=True)
  8. ALERTS      — detect significant market moves
  9. STORE       — persist to Supabase (async, non-blocking)
"""

import asyncio
import math
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

# ── Stage 1: Fetch ────────────────────────────────────────────────────────────

async def fetch_stage(sources: list[str], limits: dict[str, int]) -> tuple[list[dict], dict]:
    from sources import SOURCE_FETCHERS
    tasks = {}
    for src in sources:
        if src not in SOURCE_FETCHERS:
            continue
        tasks[src] = SOURCE_FETCHERS[src](limit=limits.get(src, limits.get("default", 15)))

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    items, stats = [], {}
    for src, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            stats[src] = f"ERROR: {result}"
        else:
            stats[src] = f"{len(result)} items"
            items.extend(result)
    return items, stats


# ── Stage 2: Filter ───────────────────────────────────────────────────────────

def filter_stage(items: list[dict]) -> list[dict]:
    seen_urls, seen_titles, clean = set(), set(), []
    for item in items:
        title = (item.get("title") or "").strip()
        url   = (item.get("url") or "").rstrip("/")
        if not title:
            continue
        if url and url in seen_urls:
            continue
        if not url and title in seen_titles:
            continue
        if url:
            seen_urls.add(url)
        seen_titles.add(title)
        clean.append(item)
    return clean


# ── Stage 3: Score ────────────────────────────────────────────────────────────

SOURCE_WEIGHTS = {
    "hackernews":    1.0,
    "arxiv":         0.9,
    "github":        0.8,
    "reddit":        0.7,
    "stackoverflow": 0.7,
    "rss":           0.6,
    "finance":       1.0,
    "fred":          0.5,
    "fear_greed":    0.5,
    # Premium signal sources
    "edgar":         1.2,
    "options":       1.1,
    "congress":      1.1,
    "finra":         1.0,
    "coingecko":     0.9,
    "gdelt":         0.7,
    "stocktwits":    0.6,
}


def score_stage(items: list[dict]) -> list[dict]:
    for item in items:
        raw    = item.get("score") or 0
        weight = SOURCE_WEIGHTS.get(item["source"], 0.5)
        item["terminal_score"] = round(weight * math.log(max(raw, 1) + 1) * 10, 1)
    return sorted(items, key=lambda x: x.get("terminal_score", 0), reverse=True)


# ── Stage 4: Sentiment + Entities ─────────────────────────────────────────────

def sentiment_stage(items: list[dict]) -> tuple[list[dict], dict]:
    try:
        from agents.sentiment import score_stage_sentiment, enrich_entities, compute_sentiment_summary
        items = score_stage_sentiment(items)
        items = enrich_entities(items)
        return items, compute_sentiment_summary(items)
    except Exception:
        return items, {}


# ── Stage 5: Trend Analysis (Ollama) ──────────────────────────────────────────

def analyze_stage(items: list[dict]) -> dict:
    try:
        from shared.utils import chat
    except ImportError:
        return {}
    top = "\n".join(f"[{i['source'].upper()}] {i['title']}" for i in items[:30])
    system = (
        "You are an intelligence analyst for a Bloomberg-style terminal. "
        "Given headlines from tech, AI, science, finance and world news, "
        "identify the 3 most important CROSS-SOURCE trends right now. "
        "Be specific, concise, data-driven. Output exactly 3 bullet points."
    )
    try:
        return {"cross_source": chat(top, system=system).strip()}
    except Exception:
        return {}


# ── Stage 6: Briefing (Ollama) ────────────────────────────────────────────────

def _time_of_day() -> str:
    h = datetime.now().hour
    if h < 12: return "Morning"
    if h < 17: return "Afternoon"
    if h < 21: return "Evening"
    return "Night"


def briefing_stage(items: list[dict], trends: dict, market_items: list[dict],
                   sentiment: dict) -> str:
    try:
        from shared.utils import chat
    except ImportError:
        return _fallback_briefing(items, market_items)

    tod    = _time_of_day()
    top_10 = "\n".join(
        f"- [{i['source']}] {i['title']} (score:{i.get('terminal_score',0):.0f}, "
        f"sentiment:{i.get('sentiment_label','?')})"
        for i in items[:10]
    )
    mkt_snap = ", ".join(m["title"] for m in market_items[:5]) if market_items else "unavailable"
    sent_txt = (f"Sentiment: {sentiment.get('bullish_pct',0)}% bullish, "
                f"{sentiment.get('bearish_pct',0)}% bearish")

    system = (
        f"You are the lead editor of a Bloomberg/Reuters intelligence terminal. "
        f"Write a crisp {tod} Briefing of 3-4 sentences covering: "
        f"(1) biggest tech/AI development, (2) market sentiment + key movers, "
        f"(3) notable research or world news. Authoritative, specific, forward-looking."
    )
    prompt = (f"TOP STORIES:\n{top_10}\n\nMARKETS: {mkt_snap}\n\n{sent_txt}\n\n"
              f"TRENDS:\n{trends.get('cross_source','')}")
    try:
        return chat(prompt, system=system).strip()
    except Exception:
        return _fallback_briefing(items, market_items)


def _fallback_briefing(items: list[dict], market_items: list[dict]) -> str:
    tod    = _time_of_day()
    by_src = defaultdict(list)
    for item in items:
        by_src[item["source"]].append(item)
    parts = [f"{tod} Intelligence Briefing — {datetime.now().strftime('%B %d, %Y %H:%M')}"]
    for src in ["hackernews", "reddit", "rss", "arxiv"]:
        if by_src[src]:
            parts.append(f"Top {src}: \"{by_src[src][0]['title'][:65]}\"")
    if market_items:
        parts.append("Markets: " + "  ·  ".join(m["title"] for m in market_items[:4]))
    return "\n".join(parts)


# ── Stage 7: Alerts ───────────────────────────────────────────────────────────

def alerts_stage(market_flat: list[dict], sentiment: dict) -> list[dict]:
    try:
        from agents.sentiment import detect_market_alerts
        alerts = detect_market_alerts(market_flat, threshold_pct=2.5)
    except Exception:
        alerts = []

    br = sentiment.get("bearish_pct", 0)
    bl = sentiment.get("bullish_pct", 0)
    if br >= 60:
        alerts.append({"type":"sentiment","title":f"High Bearish Sentiment {br}%",
                        "body":f"{br}% of today's news is bearish — broad negative signal",
                        "priority":1,"ticker":None})
    elif bl >= 70:
        alerts.append({"type":"sentiment","title":f"High Bullish Sentiment {bl}%",
                        "body":f"{bl}% of today's news is bullish — broad positive signal",
                        "priority":0,"ticker":None})
    return alerts


# ── Stage 8: Supabase Store ───────────────────────────────────────────────────

def store_stage(items, market_flat, briefing, tod, alerts, macro_items, fg_items, signal_items=None) -> dict:
    try:
        from db.supabase_sync import (
            is_available, upsert_articles, save_market_snapshot,
            save_briefing, create_alert, save_macro_indicators, save_fear_greed,
            save_signals,
        )
    except ImportError:
        return {"supabase": False}

    if not is_available():
        return {"supabase": False}

    stats = upsert_articles(items)
    save_market_snapshot(market_flat)
    if briefing:
        save_briefing(briefing, len(items), tod)
    for a in alerts:
        create_alert(a["type"], a["title"], a["body"], a["priority"], a.get("ticker"))
    macro_rows = [it["macro_data"] for it in macro_items if it.get("macro_data")]
    if macro_rows:
        save_macro_indicators(macro_rows)
    for it in fg_items:
        fg = it.get("fear_greed", {})
        if fg:
            save_fear_greed(fg["value"], fg["label"], fg.get("source","crypto"))
    if signal_items:
        try:
            save_signals(signal_items)
        except Exception:
            pass
    return {"supabase": True, **stats}


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_market_data(items):
    # Include both equity (finance) and crypto (coingecko) market data
    return [i for i in items if i.get("source") in ("finance", "coingecko") and i.get("market_data")]

def extract_macro_data(items):
    return [i for i in items if i.get("source") in ("fred", "macro", "credit")]

def extract_fear_greed(items):
    return [i for i in items if i.get("source") == "fear_greed"]

def extract_signals(items):
    """Extract high-value trade signals: insider trades, options flow, congress."""
    from sources import SIGNAL_SOURCES
    return [i for i in items if i.get("source") in SIGNAL_SOURCES]


# ── Stage 5: Intelligence (Regime + Risk) ─────────────────────────────────────

def intelligence_stage(macro_items: list[dict], fg_items: list[dict], sentiment: dict) -> dict:
    """
    Run BlackRock Aladdin-inspired regime detection and systemic risk scoring.

    Returns:
        {
          "regime": RegimeReading serialized dict,
          "risk":   RiskSnapshot serialized dict,
        }
    """
    result = {"regime": None, "risk": None}
    try:
        from intelligence.regime import detect_regime, regime_to_dict, macro_list_to_dict
        from intelligence.risk import compute_risk, risk_to_dict

        # Build {series_id: value} dict from FRED + credit spread items
        macro_dict = macro_list_to_dict([
            it["macro_data"] for it in macro_items if it.get("macro_data")
        ])

        # Fear/Greed value (use equity F&G if available, else crypto)
        fg_value = None
        for item in fg_items:
            fg = item.get("fear_greed", {})
            if fg and fg.get("source") == "stocks":
                fg_value = fg.get("value")
                break
        if fg_value is None:
            for item in fg_items:
                fg = item.get("fear_greed", {})
                if fg:
                    fg_value = fg.get("value")
                    break

        sentiment_avg = sentiment.get("avg") if sentiment else None

        regime  = detect_regime(macro_dict, sentiment_score=sentiment_avg)
        risk    = compute_risk(macro_dict, fear_greed_value=fg_value, sentiment_avg=sentiment_avg)

        result["regime"] = regime_to_dict(regime)
        result["risk"]   = risk_to_dict(risk)

    except Exception as e:
        print(f"  [intelligence] error: {e}")

    return result


# ── Main Entrypoint ───────────────────────────────────────────────────────────

async def run_pipeline(
    sources: list[str],
    limits: Optional[dict] = None,
    run_ai: bool = False,
    store: bool = True,
) -> dict:
    if limits is None:
        limits = {"default": 15}

    print(f"\n  [1/8] Fetching from {len(sources)} sources…")
    raw_items, fetch_stats = await fetch_stage(sources, limits)

    print(f"  [2/8] Filtering {len(raw_items)} raw items…")
    filtered = filter_stage(raw_items)

    print(f"  [3/8] Scoring {len(filtered)} items…")
    scored = score_stage(filtered)

    print(f"  [4/9] Sentiment + entity analysis…")
    scored, sentiment = sentiment_stage(scored)

    market_data  = extract_market_data(scored)
    macro_data   = extract_macro_data(scored)
    fg_data      = extract_fear_greed(scored)
    signal_data  = extract_signals(scored)
    market_flat  = [i["market_data"] for i in market_data if i.get("market_data")]

    print(f"  [5/9] Intelligence layer (regime + risk)…")
    intelligence = intelligence_stage(macro_data, fg_data, sentiment)

    trends = {}
    briefing = ""
    if run_ai:
        print(f"  [6/9] Trend analysis (Ollama)…")
        trends = analyze_stage(scored)
        print(f"  [7/9] Briefing generation (Ollama)…")
        briefing = briefing_stage(scored, trends, market_data, sentiment)
    else:
        briefing = _fallback_briefing(scored, market_data)

    print(f"  [8/9] Alert detection…")
    alerts = alerts_stage(market_flat, sentiment)

    store_stats = {}
    if store:
        print(f"  [9/9] Persisting to Supabase…")
        store_stats = store_stage(
            scored, market_flat, briefing, _time_of_day(),
            alerts, macro_data, fg_data, signal_data,
        )

    return {
        "items":        scored,
        "market_data":  market_data,
        "macro_data":   macro_data,
        "fear_greed":   fg_data,
        "signal_data":  signal_data,
        "alerts":       alerts,
        "briefing":     briefing,
        "trends":       trends,
        "sentiment":    sentiment,
        "intelligence": intelligence,
        "fetch_stats":  fetch_stats,
        "store_stats":  store_stats,
        "run_meta": {
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "time_of_day": _time_of_day(),
            "total_raw":   len(raw_items),
            "total_clean": len(filtered),
            "sources":     sources,
        },
    }
