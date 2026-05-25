"""
Research Agent — AI-powered market analysis using Groq (Llama 3) or Gemini Flash.

Both are completely free with no credit card required:
  - Groq:   console.groq.com → create account → API Keys → GROQ_API_KEY
  - Gemini: aistudio.google.com → Get API key → GOOGLE_API_KEY

Falls back to rule-based templates when no API key is set.

Capabilities:
  - Summarise news items (2 sentences, actionable)
  - Cross-source trend detection (top 3 themes across all sources)
  - Morning / afternoon briefing generation
  - Market regime commentary
  - Sector sentiment narrative
  - Earnings / signal interpretation

Usage:
    from agents.research_agent import summarise_item, generate_briefing

    s = await summarise_item({"title": "NVDA beats earnings...", "preview": "..."})
    brief = await generate_briefing(items, market_data, regime, risk)
"""

import asyncio
from datetime import datetime
from typing import Optional


# ── AI client import ──────────────────────────────────────────────────────────

def _ai():
    """Lazy import of groq_client to avoid circular deps."""
    import sys
    from pathlib import Path
    root = Path(__file__).parent.parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from shared.groq_client import chat_async, is_ai_available, ai_provider_name
    return chat_async, is_ai_available, ai_provider_name


# ── Rule-based fallbacks (when no API key is available) ───────────────────────

def _time_of_day() -> str:
    h = datetime.now().hour
    if h < 12: return "Morning"
    if h < 17: return "Afternoon"
    return "Evening"


def _fallback_briefing(items: list[dict], market_data: list[dict]) -> str:
    from collections import defaultdict
    by_src = defaultdict(list)
    for item in items:
        by_src[item.get("source", "unknown")].append(item)
    tod = _time_of_day()
    parts = [f"{tod} Intelligence Briefing — {datetime.now().strftime('%B %d, %Y %H:%M')}"]
    for src in ["hackernews", "reddit", "rss", "arxiv"]:
        if by_src[src]:
            title = by_src[src][0]["title"][:65]
            parts.append(f"Top {src}: \"{title}\"")
    if market_data:
        movers = sorted(market_data, key=lambda m: abs(m.get("change_pct", 0)), reverse=True)[:3]
        mkt_str = "  ·  ".join(
            f"{m['ticker']} {'+' if m['change_pct']>0 else ''}{m['change_pct']:.1f}%"
            for m in movers
        )
        parts.append(f"Markets: {mkt_str}")
    return "  ".join(parts)


def _fallback_trend(items: list[dict]) -> str:
    """Extract top 3 most common title words as a simple trend signal."""
    from collections import Counter
    import re
    words = Counter()
    stop  = {"the","a","an","to","of","in","for","is","are","on","at","and","or","with","by"}
    for item in items[:50]:
        for w in re.findall(r'\b[a-zA-Z]{4,}\b', item.get("title", "").lower()):
            if w not in stop:
                words[w] += 1
    top_words = [w for w, _ in words.most_common(6)]
    if not top_words:
        return "No clear trend signals from current news volume."
    return (
        f"Most discussed themes: {', '.join(top_words[:3])}. "
        f"Secondary signals: {', '.join(top_words[3:6])}. "
        f"Based on {min(len(items), 50)} articles across all sources."
    )


# ── AI-powered analysis ───────────────────────────────────────────────────────

async def summarise_item(item: dict, style: str = "analyst") -> str:
    """
    Summarise a single news item in 2 sentences.

    Args:
        item:  Pipeline item dict with title + preview.
        style: "analyst" (default) | "brief" | "risk"

    Returns:
        2-sentence summary string.
    """
    chat_async, is_ai_available, _ = _ai()
    title   = (item.get("title") or "")[:200]
    preview = (item.get("preview") or "")[:400]

    if not is_ai_available() or not title:
        return preview[:200] if preview else title

    systems = {
        "analyst": (
            "You are a Bloomberg intelligence analyst. Given a headline and excerpt, "
            "write exactly 2 sentences: (1) what happened, (2) why it matters for markets. "
            "Be specific, data-driven, and forward-looking. No fluff."
        ),
        "brief": (
            "Summarise this news in one crisp sentence for a professional investor. "
            "Focus on market impact."
        ),
        "risk": (
            "You are a risk analyst. In 2 sentences, identify the risk implications "
            "of this news for institutional portfolios. Be specific about asset classes affected."
        ),
    }
    prompt = f"HEADLINE: {title}\n\nEXCERPT: {preview}"
    return await chat_async(prompt, system=systems.get(style, systems["analyst"]), max_tokens=120)


async def detect_trends(items: list[dict]) -> str:
    """
    Identify top 3 cross-source themes from a batch of news items.
    Uses Groq Llama 3 for semantic clustering.
    """
    chat_async, is_ai_available, _ = _ai()

    if not is_ai_available():
        return _fallback_trend(items)

    # Take top 30 items by score for context window efficiency
    top30 = items[:30]
    headlines = "\n".join(
        f"[{it.get('source','?').upper()}] {it.get('title','')}"
        for it in top30
    )
    system = (
        "You are a cross-asset intelligence analyst for a Bloomberg-style terminal. "
        "Given headlines from tech, AI, science, finance and world news, identify the "
        "3 most important CROSS-SOURCE themes or trends right now. "
        "Be specific, data-driven, actionable. Output exactly 3 bullet points."
    )
    return await chat_async(headlines, system=system, max_tokens=200)


async def generate_briefing(
    items:       list[dict],
    market_data: list[dict],
    regime:      dict,
    risk:        dict,
    sentiment:   dict,
) -> str:
    """
    Generate the daily intelligence briefing — the hero content piece.

    Incorporates macro regime, systemic risk, market movers, and news trends
    into a 3–4 sentence authoritative narrative.
    """
    chat_async, is_ai_available, prov = _ai()

    if not is_ai_available():
        return _fallback_briefing(items, market_data)

    tod    = _time_of_day()
    date_s = datetime.now().strftime("%B %d, %Y")

    # Build context block
    top10 = "\n".join(
        f"- [{it.get('source','?')}] {it.get('title','')} "
        f"({it.get('sentiment_label','neutral')})"
        for it in items[:10]
    )
    movers_str = ""
    if market_data:
        movers = sorted(market_data, key=lambda m: abs(m.get("change_pct", 0)), reverse=True)[:5]
        movers_str = ", ".join(
            f"{m['ticker']} {'+' if m['change_pct']>0 else ''}{m['change_pct']:.1f}%"
            for m in movers if m.get("change_pct") is not None
        )

    regime_str = ""
    if regime:
        regime_str = (
            f"Market Regime: {regime.get('label','unknown')} "
            f"(conf:{regime.get('confidence_pct',0):.0f}%) — "
            f"{regime.get('description','')}"
        )

    risk_str = ""
    if risk:
        risk_str = (
            f"Systemic Risk Score: {risk.get('srs',0)}/100 [{risk.get('level','?')}]. "
            f"Top risk: {risk.get('top_risks',['—'])[0]}"
        )

    sent_str = (
        f"Sentiment: {sentiment.get('bullish_pct',0)}% bullish, "
        f"{sentiment.get('bearish_pct',0)}% bearish across {sentiment.get('total',0)} items."
    )

    system = (
        f"You are the lead editor of a Bloomberg/Reuters intelligence terminal. "
        f"Today is {date_s}. Write a crisp {tod} Briefing of EXACTLY 3 sentences: "
        f"(1) Biggest macro or market development with specific data points. "
        f"(2) Technology or AI story + market sentiment context. "
        f"(3) Forward-looking risk or opportunity for institutional investors. "
        f"Authoritative, specific, no filler. Output only the 3 sentences."
    )
    prompt = (
        f"TOP STORIES:\n{top10}\n\n"
        f"MARKET MOVERS: {movers_str}\n\n"
        f"{regime_str}\n{risk_str}\n{sent_str}"
    )
    return await chat_async(prompt, system=system, model="smart", max_tokens=280)


async def interpret_signal(signal: dict) -> str:
    """
    Interpret a trade signal (insider trade, options flow, congress STOCK Act).
    Returns a 1-2 sentence professional interpretation.
    """
    chat_async, is_ai_available, _ = _ai()

    if not is_ai_available():
        return signal.get("preview", signal.get("title", ""))[:200]

    src = signal.get("source", "unknown")
    title = signal.get("title", "")
    preview = (signal.get("preview") or "")[:300]
    sentiment = signal.get("sentiment_label", "neutral")

    source_context = {
        "edgar":    "SEC EDGAR insider trade filing",
        "options":  "unusual options flow / dark pool activity",
        "congress": "Congressional STOCK Act disclosure",
        "finra":    "FINRA RegSHO short-sale volume report",
    }.get(src, "institutional signal")

    system = (
        "You are a quantitative analyst at a hedge fund. "
        "Given a trade signal, write 1-2 sentences interpreting: "
        "(1) what this signal means, (2) how a fund manager should act on it. "
        "Be specific about conviction level, asset affected, and time horizon."
    )
    prompt = (
        f"SOURCE: {source_context} ({sentiment})\n"
        f"SIGNAL: {title}\n"
        f"DETAIL: {preview}"
    )
    return await chat_async(prompt, system=system, max_tokens=100)


async def generate_sector_narrative(items: list[dict], sector: str) -> str:
    """
    Generate a 2-sentence narrative for a specific sector (AI, Energy, Financials, etc.)
    based on filtered news.
    """
    chat_async, is_ai_available, _ = _ai()

    sector_items = [
        it for it in items
        if sector.lower() in (it.get("title", "") + " " + " ".join(it.get("tags", []))).lower()
    ][:15]

    if not sector_items:
        return f"No significant {sector} developments detected in current news flow."

    if not is_ai_available():
        return sector_items[0]["title"][:200] if sector_items else ""

    headlines = "\n".join(f"- {it['title']}" for it in sector_items[:10])
    system = (
        f"You are a sell-side research analyst covering {sector}. "
        f"Based on these headlines, write 2 sentences: (1) current theme in {sector}, "
        f"(2) investment implication. Factual and specific."
    )
    return await chat_async(headlines, system=system, max_tokens=100)
