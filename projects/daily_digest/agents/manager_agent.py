"""
Manager Agent — Routes user queries to the correct specialist agent.

This is the orchestration layer that makes the system feel intelligent.
A user can ask a natural-language question and get a unified answer
compiled from Data + Math + Research agents.

Query categories handled:
  - "What is the VaR of NVDA?"        → Math Agent
  - "What happened in markets today?" → Research Agent + pipeline cache
  - "Show me risk for [AAPL, TSLA]"   → Math Agent (portfolio)
  - "What's the regime?"              → Intelligence layer (regime.py)
  - "Summarise NVDA news"             → Research Agent
  - "Top signals today"               → Pipeline cache (signals)
  - "Technical analysis of MSFT"      → Math Agent (technical)

Usage:
    from agents.manager_agent import handle_query

    result = await handle_query("What is the current market regime?")
    result = await handle_query("Compute VaR for portfolio NVDA AAPL MSFT")
"""

import re
import asyncio
from typing import Optional


# ── Intent classifier ─────────────────────────────────────────────────────────

INTENT_PATTERNS = {
    "var": [
        r"\bvar\b", r"value.at.risk", r"\brisk\b.*\b(of|for)\b", r"drawdown",
        r"sharpe", r"sortino", r"volatility.*\b(of|for)\b",
    ],
    "portfolio": [
        r"portfolio", r"watchlist", r"holdings", r"positions",
    ],
    "technical": [
        r"technical", r"rsi", r"sma", r"moving.average", r"support", r"resistance",
        r"chart.*\b(of|for)\b", r"trend.*\b(of|for)\b",
    ],
    "regime": [
        r"regime", r"goldilocks", r"stagflation", r"reflation", r"deflation",
        r"market.*cycle", r"macro.*environment",
    ],
    "risk_score": [
        r"srs", r"systemic.risk", r"risk.score", r"overall.risk",
    ],
    "briefing": [
        r"briefing", r"summary", r"what.happened", r"today.*market",
        r"morning.*report", r"afternoon.*report",
    ],
    "signals": [
        r"signal", r"insider", r"options.flow", r"congress.*trade", r"sec.*filing",
        r"unusual.*option",
    ],
    "news": [
        r"news", r"headline", r"article", r"latest.*\b(on|about)\b",
        r"what.*said", r"trending",
    ],
    "sector": [
        r"sector", r"ai.*market", r"tech.*market", r"energy.*market",
        r"financial.*sector", r"crypto.*market",
    ],
}


def classify_intent(query: str) -> tuple[str, list[str]]:
    """
    Classify user intent and extract ticker symbols.

    Returns:
        (intent_name, ticker_list)
    """
    q_lower = query.lower()

    # Extract tickers: $NVDA or all-caps 2-5 chars
    tickers = list(set(
        t.upper()
        for t in re.findall(r'\$([A-Z]{1,5})\b|(?<![A-Za-z])([A-Z]{2,5})(?![a-z])', query)
        if any(t)
    ))
    # Flatten match groups
    tickers = [g1 or g2 for g1, g2 in re.findall(r'\$([A-Z]{1,5})\b|(?<![A-Za-z])([A-Z]{2,5})(?![a-z])', query)]
    tickers = [t for t in tickers if t]

    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, q_lower):
                return intent, tickers

    # Default: news/briefing
    return "news", tickers


# ── Response formatters ───────────────────────────────────────────────────────

def _format_var_result(result: dict) -> str:
    if "error" in result:
        return f"⚠ Could not compute risk metrics for {result.get('ticker', '?')}: {result['error']}"

    lines = [
        f"📊 **{result['ticker']} Risk Metrics** ({result.get('period', '1Y')})",
        f"",
        f"Current Price:    ${result.get('current_price', 0):,.2f}",
        f"1-Day VaR  95%:   {result.get('var_95', 0):.2f}%  (Historical Simulation)",
        f"1-Day VaR  99%:   {result.get('var_99', 0):.2f}%",
        f"CVaR / ES  95%:   {result.get('cvar_95', 0):.2f}%  (Expected Shortfall)",
        f"",
        f"Sharpe Ratio:     {result.get('sharpe', 0):.3f}  (≥1 = good, ≥2 = excellent)",
        f"Sortino Ratio:    {result.get('sortino', 0):.3f}  (downside-risk adjusted)",
        f"Max Drawdown:     {result.get('max_drawdown', 0):.2f}%",
        f"Annual Volatility:{result.get('annualised_vol', 0):.2f}%",
        f"Beta vs S&P 500:  {result.get('beta', 'N/A')}",
        f"Total Return:     {result.get('total_return', 0):.2f}%",
    ]
    return "\n".join(lines)


def _format_portfolio_result(result: dict) -> str:
    if "error" in result:
        return f"⚠ Portfolio error: {result['error']}"

    p = result.get("portfolio", {})
    lines = [
        f"📊 **Portfolio Risk Report**",
        f"",
        f"Tickers: {', '.join(p.get('tickers', []))}",
        f"Period:  {p.get('period', '1Y')} | {p.get('observations', 0)} observations",
        f"",
        f"Portfolio VaR  95%:   {p.get('var_95', 0):.2f}%  daily",
        f"Portfolio VaR  99%:   {p.get('var_99', 0):.2f}%  daily",
        f"Portfolio CVaR 95%:   {p.get('cvar_95', 0):.2f}%  (Expected Shortfall)",
        f"Portfolio Sharpe:     {p.get('sharpe', 0):.3f}",
        f"Portfolio Volatility: {p.get('annualised_vol', 0):.2f}% annualised",
        f"",
        f"Individual Holdings:",
    ]
    for ind in result.get("individual", []):
        if "error" in ind:
            lines.append(f"  {ind['ticker']}: {ind['error']}")
        else:
            lines.append(
                f"  {ind['ticker']:6s} | w:{ind.get('weight',0):.0%} | "
                f"VaR95:{ind.get('var_95',0):.2f}% | "
                f"Sharpe:{ind.get('sharpe',0):.2f} | "
                f"Vol:{ind.get('annualised_vol',0):.1f}%"
            )
    return "\n".join(lines)


def _format_technical_result(result: dict) -> str:
    if "error" in result:
        return f"⚠ {result['ticker']}: {result['error']}"

    lines = [
        f"📈 **{result['ticker']} Technical Analysis**",
        f"",
        f"Current Price: ${result.get('current_price', 0):,.2f}",
        f"",
        f"SMA 20:  ${result.get('sma20', 0) or 0:,.2f}  ({result.get('pct_vs_sma20', 0) or 0:+.2f}%)",
        f"SMA 50:  ${result.get('sma50', 0) or 0:,.2f}  ({result.get('pct_vs_sma50', 0) or 0:+.2f}%)",
        f"SMA 200: ${result.get('sma200', 0) or 0:,.2f}  ({result.get('pct_vs_sma200', 0) or 0:+.2f}%)",
        f"RSI 14:  {result.get('rsi14', 0) or 0:.1f}  [{result.get('rsi_signal', '?')}]",
        f"",
        f"Trend: {result.get('trend_signal', '?').upper()}",
    ]
    return "\n".join(lines)


# ── Main query handler ─────────────────────────────────────────────────────────

async def handle_query(
    query:          str,
    pipeline_cache: Optional[dict] = None,   # current /api/pipeline payload
) -> dict:
    """
    Route a user query to the appropriate agent and return a unified response.

    Args:
        query:          Natural-language query string.
        pipeline_cache: Latest pipeline payload (from /api/pipeline cache).

    Returns:
        {
            "intent":  str,
            "tickers": list,
            "answer":  str,          # human-readable formatted response
            "data":    dict | None,  # raw data for programmatic use
        }
    """
    intent, tickers = classify_intent(query)
    cache = pipeline_cache or {}

    # ── VAR / single stock risk ───────────────────────────────────────────────
    if intent == "var":
        if not tickers:
            return {"intent": intent, "tickers": [], "answer": "Please specify a ticker (e.g. VaR of NVDA)", "data": None}
        from agents.math_agent import compute_var
        ticker  = tickers[0]
        result  = await compute_var(ticker)
        return {"intent": intent, "tickers": [ticker], "answer": _format_var_result(result), "data": result}

    # ── Portfolio risk ────────────────────────────────────────────────────────
    if intent == "portfolio":
        if not tickers:
            tickers = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN"]   # default watchlist
        from agents.math_agent import compute_portfolio_risk
        result  = await compute_portfolio_risk(tickers[:20])
        return {"intent": intent, "tickers": tickers, "answer": _format_portfolio_result(result), "data": result}

    # ── Technical analysis ────────────────────────────────────────────────────
    if intent == "technical":
        if not tickers:
            return {"intent": intent, "tickers": [], "answer": "Please specify a ticker (e.g. technical analysis of MSFT)", "data": None}
        from agents.math_agent import compute_technical
        ticker = tickers[0]
        result = await compute_technical(ticker)
        return {"intent": intent, "tickers": [ticker], "answer": _format_technical_result(result), "data": result}

    # ── Regime ────────────────────────────────────────────────────────────────
    if intent == "regime":
        regime = cache.get("regime", {})
        if not regime:
            return {"intent": intent, "tickers": [], "answer": "No regime data available — run pipeline first.", "data": None}
        answer = (
            f"📊 **Market Regime: {regime.get('label', '?')}**\n\n"
            f"Confidence: {regime.get('confidence_pct', 0):.0f}%\n"
            f"Growth:     {regime.get('growth_score', 0):+.3f}  |  "
            f"Inflation: {regime.get('inflation_score', 0):+.3f}\n"
            f"Transition risk: {regime.get('transition_risk', '?')}\n\n"
            f"{regime.get('description', '')}\n\n"
            f"Favors: {', '.join(regime.get('favors', []))}\n"
            f"Avoids: {', '.join(regime.get('avoids', []))}"
        )
        return {"intent": intent, "tickers": [], "answer": answer, "data": regime}

    # ── SRS / Systemic Risk Score ─────────────────────────────────────────────
    if intent == "risk_score":
        risk = cache.get("risk", {})
        if not risk:
            return {"intent": intent, "tickers": [], "answer": "No risk data available — run pipeline first.", "data": None}
        factors_str = "\n".join(
            f"  {f.get('name', '?')}: {f.get('score', 0):.0f}/100  (w:{f.get('weight', 0):.0%})"
            for f in risk.get("factors", [])
        )
        answer = (
            f"🎯 **Systemic Risk Score: {risk.get('srs', 0)}/100 [{risk.get('level', '?')}]**\n\n"
            f"Factor Breakdown:\n{factors_str}\n\n"
            f"Top Risks:\n" + "\n".join(f"  • {r}" for r in risk.get("top_risks", []))
        )
        return {"intent": intent, "tickers": [], "answer": answer, "data": risk}

    # ── Briefing ──────────────────────────────────────────────────────────────
    if intent == "briefing":
        cached_brief = cache.get("briefing", "")
        if cached_brief:
            return {"intent": intent, "tickers": [], "answer": f"📰 **Intelligence Briefing**\n\n{cached_brief}", "data": None}
        # Generate fresh via research agent
        from agents.research_agent import generate_briefing
        brief = await generate_briefing(
            items       = cache.get("items", [])[:30],
            market_data = cache.get("market", []),
            regime      = cache.get("regime", {}),
            risk        = cache.get("risk", {}),
            sentiment   = cache.get("sentiment", {}),
        )
        return {"intent": intent, "tickers": [], "answer": f"📰 **Intelligence Briefing**\n\n{brief}", "data": None}

    # ── Signals ───────────────────────────────────────────────────────────────
    if intent == "signals":
        signals = cache.get("signals", [])
        if not signals:
            return {"intent": intent, "tickers": [], "answer": "No signals in cache — pipeline may be refreshing.", "data": None}
        lines = [f"⚡ **Top {min(len(signals), 10)} Trade Signals**\n"]
        for s in signals[:10]:
            dir_sym = "▲" if s.get("sentiment_label") == "bullish" else "▼" if s.get("sentiment_label") == "bearish" else "—"
            lines.append(f"{dir_sym} [{s.get('source', '?').upper()}] {s.get('title', '')[:80]}")
        return {"intent": intent, "tickers": [], "answer": "\n".join(lines), "data": signals[:10]}

    # ── News / default ────────────────────────────────────────────────────────
    items = cache.get("items", [])
    if tickers:
        # Filter to items mentioning the ticker
        ticker_up = {t.upper() for t in tickers}
        items = [it for it in items if ticker_up.intersection(set(e.upper() for e in (it.get("entities") or [])))]

    if not items:
        return {"intent": "news", "tickers": tickers, "answer": "No matching news in cache.", "data": None}

    from agents.research_agent import detect_trends
    trends = await detect_trends(items[:30])
    top5   = "\n".join(f"• {it['title'][:80]}" for it in items[:5])
    answer = f"📰 **Latest Intelligence** ({len(items)} items)\n\n{top5}\n\nTrends:\n{trends}"
    return {"intent": "news", "tickers": tickers, "answer": answer, "data": items[:5]}
