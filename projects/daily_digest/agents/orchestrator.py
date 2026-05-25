"""Multi-agent orchestrator — TradingAgents/LangGraph-inspired pipeline.

Routes a user query through specialized agents, each owning a narrow domain:

  ┌─ Analyst ────────┐
  │  classify intent │
  │  extract tickers │
  └────────┬─────────┘
           ▼
  ┌─ Data Agent ─────┐
  │  fetch prices    │
  │  fetch news      │
  │  fetch macro     │
  └────────┬─────────┘
           ▼
  ┌─ Risk Manager ───┐  ← parallel
  │  VaR · vol · DD  │
  │  GARCH forecast  │
  └──────────────────┘
  ┌─ Researcher ─────┐  ← parallel
  │  AI summarization│
  │  trend detection │
  └──────────────────┘
           ▼
  ┌─ Portfolio Mgr ──┐
  │  synthesize      │
  │  recommendation  │
  └────────┬─────────┘
           ▼
       Decision Log

State is passed through each node as a dict; checkpoints persist for audit.

Reference: TradingAgents (arXiv 2412.20138), LangGraph orchestration patterns.
"""
from __future__ import annotations
import asyncio
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class AgentState:
    """Shared state passed through the orchestration graph."""
    query: str
    intent: str = "general"
    tickers: list[str] = field(default_factory=list)
    period: str = "1y"
    # Data fetched
    price_data: dict = field(default_factory=dict)
    news_data: list = field(default_factory=list)
    macro_data: dict = field(default_factory=dict)
    # Analysis outputs
    risk_metrics: dict = field(default_factory=dict)
    research_summary: str = ""
    # Final
    recommendation: str = ""
    decision_log: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    started_at: float = field(default_factory=time.time)

    def log(self, agent: str, message: str, data: Optional[dict] = None) -> None:
        self.decision_log.append({
            "agent":     agent,
            "message":   message,
            "data":      data or {},
            "timestamp": round(time.time() - self.started_at, 3),
        })

    def to_dict(self) -> dict:
        return asdict(self)


# ── Agent: Analyst (intent + entity extraction) ─────────────────────────────

async def analyst_node(state: AgentState) -> AgentState:
    """Classify intent + extract entities."""
    from agents.manager_agent import classify_intent
    intent, tickers = classify_intent(state.query)
    state.intent = intent
    state.tickers = tickers
    state.log("analyst", f"Classified intent={intent}, tickers={tickers}")
    return state


# ── Agent: Data (fetch prices + news + macro in parallel) ───────────────────

async def data_node(state: AgentState) -> AgentState:
    """Fetch price + news + macro in parallel."""
    tasks = []
    if state.tickers:
        tasks.append(_fetch_prices_async(state.tickers, state.period))
    tasks.append(_fetch_news_async(state.tickers))
    tasks.append(_fetch_macro_async())

    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        state.errors.append(f"data_node: {e}")
        return state

    idx = 0
    if state.tickers:
        prices_result = results[idx]
        if not isinstance(prices_result, Exception):
            state.price_data = prices_result
        idx += 1
    news_result = results[idx]
    if not isinstance(news_result, Exception):
        state.news_data = news_result
    idx += 1
    macro_result = results[idx]
    if not isinstance(macro_result, Exception):
        state.macro_data = macro_result

    state.log("data", f"Fetched: {len(state.price_data)} prices, "
                      f"{len(state.news_data)} articles, "
                      f"{len(state.macro_data)} macro")
    return state


async def _fetch_prices_async(tickers: list[str], period: str) -> dict:
    """Batched yfinance via thread pool."""
    loop = asyncio.get_event_loop()
    def _fetch():
        try:
            import yfinance as yf
            data = {}
            for t in tickers[:10]:
                hist = yf.Ticker(t).history(period=period, interval="1d", auto_adjust=True)
                if not hist.empty:
                    data[t] = {
                        "price":   round(float(hist["Close"].iloc[-1]), 2),
                        "returns": hist["Close"].pct_change().dropna().tolist(),
                    }
            return data
        except Exception:
            return {}
    return await loop.run_in_executor(None, _fetch)


async def _fetch_news_async(tickers: list[str]) -> list:
    """Fetch top news (Supabase if available, else empty)."""
    loop = asyncio.get_event_loop()
    def _fetch():
        try:
            import os
            from supabase import create_client
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_ANON_KEY")
            if not url or not key:
                return []
            client = create_client(url, key)
            query = client.table("articles").select("*").order("terminal_score", desc=True).limit(20)
            if tickers:
                # Filter by tickers in title or preview
                pattern = "|".join(tickers)
                # Supabase doesn't have rich text search free-tier — return all + client-side filter
            data = query.execute().data or []
            if tickers:
                data = [
                    d for d in data
                    if any(t.lower() in (d.get("title") or "").lower() or
                           t.lower() in (d.get("preview") or "").lower()
                           for t in tickers)
                ][:10]
            return data
        except Exception:
            return []
    return await loop.run_in_executor(None, _fetch)


async def _fetch_macro_async() -> dict:
    """Fetch latest macro from FRED CSV."""
    loop = asyncio.get_event_loop()
    def _fetch():
        try:
            import httpx
            macro = {}
            with httpx.Client(timeout=8) as client:
                for sid in ["T10Y2Y", "VIXCLS", "DGS10", "FEDFUNDS"]:
                    try:
                        r = client.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}")
                        if r.status_code == 200:
                            for row in reversed(r.text.splitlines()[1:]):
                                parts = row.strip().split(",")
                                if len(parts) >= 2 and parts[1] not in (".", ""):
                                    macro[sid] = float(parts[1])
                                    break
                    except Exception:
                        continue
            return macro
        except Exception:
            return {}
    return await loop.run_in_executor(None, _fetch)


# ── Agent: Risk Manager (parallel branch) ───────────────────────────────────

async def risk_node(state: AgentState) -> AgentState:
    """Compute VaR + GARCH forecast for each ticker."""
    if not state.tickers or not state.price_data:
        return state
    try:
        from agents.math_agent     import compute_var
        from agents.math_advanced  import garch_11_forecast, cornish_fisher_var
    except Exception as e:
        state.errors.append(f"risk_node imports: {e}")
        return state

    metrics = {}
    for t in state.tickers[:5]:
        try:
            var_result = await compute_var(t, period=state.period)
            ticker_returns = state.price_data.get(t, {}).get("returns", [])
            if ticker_returns and len(ticker_returns) >= 60:
                garch = garch_11_forecast(ticker_returns, horizon=5)
                cf_var = cornish_fisher_var(ticker_returns, 0.95)
                metrics[t] = {
                    "var_95":         var_result.get("var_95"),
                    "cvar_95":        var_result.get("cvar_95"),
                    "sharpe":         var_result.get("sharpe"),
                    "garch_forecast": garch,
                    "cornish_fisher_var": cf_var,
                }
            else:
                metrics[t] = {
                    "var_95":  var_result.get("var_95"),
                    "cvar_95": var_result.get("cvar_95"),
                    "sharpe":  var_result.get("sharpe"),
                }
        except Exception as e:
            metrics[t] = {"error": str(e)}

    state.risk_metrics = metrics
    state.log("risk_manager", f"Computed risk for {len(metrics)} tickers")
    return state


# ── Agent: Researcher (parallel branch) ─────────────────────────────────────

async def researcher_node(state: AgentState) -> AgentState:
    """Summarize news + detect trends via Groq."""
    if not state.news_data:
        return state
    try:
        from agents.research_agent import detect_trends
        state.research_summary = await detect_trends(state.news_data[:15])
        state.log("researcher", f"Summarized {len(state.news_data)} articles")
    except Exception as e:
        state.errors.append(f"researcher_node: {e}")
    return state


# ── Agent: Portfolio Manager (synthesis) ────────────────────────────────────

async def portfolio_manager_node(state: AgentState) -> AgentState:
    """Synthesize all signals into a recommendation via Groq."""
    try:
        from shared.groq_client import chat
    except Exception:
        state.recommendation = _rule_based_synthesis(state)
        return state

    context = _build_synthesis_context(state)
    system = (
        "You are a portfolio manager at a Bloomberg/Aladdin-style platform. "
        "Synthesize: (1) what the data says, (2) key risks, (3) action recommendation "
        "for a retail trader. Max 4 sentences. Be specific and direct."
    )
    try:
        state.recommendation = chat(context, system=system, model="smart", max_tokens=320)
        state.log("portfolio_mgr", f"Generated recommendation ({len(state.recommendation)} chars)")
    except Exception as e:
        state.errors.append(f"portfolio_mgr LLM: {e}")
        state.recommendation = _rule_based_synthesis(state)
    return state


def _build_synthesis_context(state: AgentState) -> str:
    parts = [f"Query: {state.query}"]
    if state.tickers:
        parts.append(f"Tickers: {', '.join(state.tickers)}")
    if state.macro_data:
        macro_str = ", ".join(f"{k}={v:.2f}" for k, v in state.macro_data.items())
        parts.append(f"Macro: {macro_str}")
    if state.risk_metrics:
        for t, m in state.risk_metrics.items():
            if "error" not in m:
                parts.append(
                    f"{t}: VaR95={m.get('var_95','?')}%, "
                    f"Sharpe={m.get('sharpe','?')}, "
                    f"GARCH forecast vol={m.get('garch_forecast', {}).get('forecast_vol', '?')}"
                )
    if state.research_summary:
        parts.append(f"News summary: {state.research_summary[:300]}")
    return "\n".join(parts)


def _rule_based_synthesis(state: AgentState) -> str:
    """Fallback when LLM unavailable."""
    parts = []
    if state.risk_metrics:
        for t, m in state.risk_metrics.items():
            if "error" in m:
                continue
            var = m.get("var_95", 0)
            sharpe = m.get("sharpe", 0)
            parts.append(
                f"{t}: 1-day VaR(95%) {var:.2f}%, Sharpe {sharpe:.2f}. "
                f"{'Strong risk-adjusted return.' if sharpe > 1 else 'Weak risk-adjusted return.'}"
            )
    if not parts:
        parts.append("Insufficient data to generate recommendation.")
    return " ".join(parts)


# ── Public orchestrator entry point ─────────────────────────────────────────

async def run_orchestrator(query: str, period: str = "1y") -> dict:
    """Run the full multi-agent pipeline on a query.

    Returns AgentState as dict with final recommendation + decision log.
    """
    state = AgentState(query=query, period=period)

    await analyst_node(state)
    await data_node(state)
    # Risk + Research run in parallel
    await asyncio.gather(risk_node(state), researcher_node(state))
    await portfolio_manager_node(state)

    state.log("orchestrator", f"Completed in {round(time.time() - state.started_at, 2)}s")
    return state.to_dict()
