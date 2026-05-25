"""
AI Research — Groq-powered news analysis, signal interpretation, custom queries.

Inspired by:
  - LSEG Workspace AI-powered search
  - Bloomberg Intelligence research summaries
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for p in (ROOT, ROOT / "projects" / "daily_digest"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import streamlit as st

st.set_page_config(page_title="AI Research · INTL", page_icon="🔬", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _theme      import apply_theme, status_pill
from _data       import load_articles, load_signals
from _components import news_item_card, source_badge
apply_theme()


def main():
    col_t, col_r = st.columns([6, 1])
    with col_t:
        st.title("🔬 AI Research")
        st.caption("Groq Llama 3 · News analysis · Signal interpretation · Manager Agent")
    with col_r:
        st.write("")
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # AI status banner
    try:
        from shared.groq_client import is_ai_available, ai_provider_name
        if is_ai_available():
            st.markdown(f"AI Provider: {status_pill('● ' + ai_provider_name(), 'live')}",
                        unsafe_allow_html=True)
        else:
            st.markdown(status_pill("○ AI offline", "error"), unsafe_allow_html=True)
            st.warning(
                "**No AI provider configured.** Add `GROQ_API_KEY` to Streamlit secrets "
                "(free at https://console.groq.com — takes 30 sec, no credit card).",
            )
    except Exception:
        pass

    st.divider()

    tab_news, tab_signals, tab_custom = st.tabs([
        "📰 News Analysis", "⚡ Signal Interpreter", "💬 Manager Agent"
    ])

    with tab_news:
        _render_news_tab()

    with tab_signals:
        _render_signals_tab()

    with tab_custom:
        _render_custom_query_tab()


def _render_news_tab():
    """News analysis with sentiment + AI summarization."""
    articles, status = load_articles(limit=100)

    if status == "missing":
        st.error(
            "⚠ `articles` table missing. Run [migration 001/002]"
            "(https://github.com/git0ST/automation/tree/main/supabase/migrations) in Supabase."
        )
        return

    if not articles:
        st.warning(
            "📭 **No news yet.** The pipeline cron hasn't run to populate the news feed.\n\n"
            "Trigger it manually: "
            "https://github.com/git0ST/automation/actions/workflows/digest.yml → **Run workflow**",
            icon="⚠️",
        )
        return

    # Filters
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        sources = sorted(set((it.get("source") or "?") for it in articles))
        source_filter = st.selectbox("Source", ["All"] + sources)
    with col2:
        sentiment_filter = st.selectbox("Sentiment", ["All", "bullish", "bearish", "neutral"])
    with col3:
        max_show = st.selectbox("Show", [10, 20, 50, 100], index=1)

    filtered = [
        it for it in articles
        if (source_filter == "All" or it.get("source") == source_filter)
        and (sentiment_filter == "All" or it.get("sentiment_label") == sentiment_filter)
    ]

    st.markdown(f"**{len(filtered)} items** matching filters · click any to expand")

    if st.button("🤖 Detect Cross-Source Trends", use_container_width=True):
        with st.spinner("Analysing trends via Groq…"):
            try:
                import asyncio
                from agents.research_agent import detect_trends
                loop = asyncio.new_event_loop()
                try:
                    trends = loop.run_until_complete(detect_trends(filtered[:30]))
                finally:
                    loop.close()
                with st.expander("📊 Detected Trends", expanded=True):
                    st.markdown(trends)
            except Exception as e:
                st.error(f"Trend detection failed: {e}")

    st.divider()

    for it in filtered[:max_show]:
        sent = it.get("sentiment_label") or "neutral"
        icon = "▲" if sent == "bullish" else "▼" if sent == "bearish" else "·"
        color = "#00d68f" if sent == "bullish" else "#ff5773" if sent == "bearish" else "#8b93a7"
        src = (it.get("source") or "?").upper()

        with st.expander(f"{icon} [{src}] {(it.get('title') or '—')[:80]}"):
            col_a, col_b = st.columns([3, 1])
            with col_a:
                if it.get("preview"):
                    st.caption(it["preview"][:500])
                if it.get("url"):
                    st.markdown(f"[Read full article →]({it['url']})")
            with col_b:
                st.metric("Sentiment", f"{icon} {sent.title()}")
                st.metric("Score", f"{it.get('terminal_score', 0):.0f}")
                if st.button("AI Summary", key=f"sum_{it.get('id', id(it))}"):
                    with st.spinner("Summarising…"):
                        try:
                            import asyncio
                            from agents.research_agent import summarise_item
                            loop = asyncio.new_event_loop()
                            try:
                                s = loop.run_until_complete(summarise_item(it))
                            finally:
                                loop.close()
                            st.success(s)
                        except Exception as e:
                            st.error(f"Summary failed: {e}")


def _render_signals_tab():
    """Signal Interpreter — insider/options/congress/FINRA."""
    signals, status = load_signals(limit=30)

    if status == "missing":
        st.error(
            "⚠ `signals` table missing. Run [migration 002]"
            "(https://github.com/git0ST/automation/blob/main/supabase/migrations/002_signals_table.sql)."
        )
        return

    if not signals:
        st.warning(
            "📭 **No alpha signals yet.** The pipeline hasn't pulled insider/options/congress data.",
            icon="⚠️",
        )
        with st.expander("ℹ️ What are alpha signals?", expanded=True):
            st.markdown("""
            **Signals** are non-public-yet-alpha-generating events the pipeline collects:

            - 🏛️ **SEC EDGAR Form 4** — executive insider buys/sells (within 2 days of trade)
            - 📈 **Unusual options flow** — large block trades hinting at smart-money positioning
            - 🏛️ **Congressional trades** — disclosed US Senator/Rep transactions
            - 📉 **FINRA short interest** — short positions building up
            - 💳 **ICE BofA credit spreads** — HY OAS, IG OAS, TED spread

            Once populated, this tab will show each signal with AI commentary explaining what it means.
            """)
        st.link_button(
            "🚀 Trigger pipeline now",
            "https://github.com/git0ST/automation/actions/workflows/digest.yml",
            use_container_width=True,
            type="primary",
        )
        return

    source_map = {
        "edgar":    "SEC Insider",
        "options":  "Options Flow",
        "congress": "Congress",
        "finra":    "FINRA Short",
        "credit":   "Credit Spread",
    }
    for sig in signals[:20]:
        src_label = source_map.get(sig.get("source"), (sig.get("source") or "?").upper())
        sent = sig.get("sentiment_label") or "neutral"
        icon = "▲" if sent == "bullish" else "▼" if sent == "bearish" else "—"
        color = "#00d68f" if sent == "bullish" else "#ff5773" if sent == "bearish" else "#8b93a7"

        with st.expander(f"{icon} [{src_label}] {(sig.get('title') or '—')[:75]}"):
            if sig.get("preview"):
                st.write(sig["preview"][:400])
            if st.button("🧠 Interpret Signal", key=f"sig_{sig.get('id', id(sig))}"):
                with st.spinner("Interpreting via Groq Llama 3…"):
                    try:
                        import asyncio
                        from agents.research_agent import interpret_signal
                        loop = asyncio.new_event_loop()
                        try:
                            interp = loop.run_until_complete(interpret_signal(sig))
                        finally:
                            loop.close()
                        st.info(interp)
                    except Exception as e:
                        st.error(f"Interpretation failed: {e}")


def _render_custom_query_tab():
    """Multi-agent orchestrator — Analyst → Data → Risk + Researcher → Portfolio Mgr."""
    st.markdown("#### 🤖 Multi-Agent Orchestrator")
    st.caption(
        "TradingAgents-inspired pipeline. Your query runs through 5 specialized agents in "
        "parallel where possible, with a decision log you can audit."
    )

    # Pipeline visualization
    with st.expander("🔍 Pipeline architecture", expanded=False):
        st.markdown("""
        ```
        ┌─ Analyst ─────┐
        │ classify intent + extract tickers
        └───────┬───────┘
                ▼
        ┌─ Data Agent ──┐
        │ fetch prices · news · macro (parallel)
        └───────┬───────┘
                ▼
        ┌─ Risk Manager ┐    ┌─ Researcher ──┐
        │ VaR · GARCH   │ || │ AI trends     │
        │ Cornish-Fisher│    │ summary       │
        └───────┬───────┘    └───────┬───────┘
                └────────┬───────────┘
                         ▼
                ┌─ Portfolio Manager ─┐
                │ synthesize → action │
                └─────────────────────┘
        ```
        """)

    st.markdown("**Quick prompts:**")
    cols = st.columns(4)
    examples = [
        "Analyze NVDA risk profile",
        "Portfolio outlook: AAPL MSFT GOOGL",
        "Should I buy TSLA?",
        "Market regime + top movers",
    ]
    for col, ex in zip(cols, examples):
        with col:
            if st.button(ex, use_container_width=True, key=f"ex_{hash(ex)}"):
                st.session_state["mgr_query"] = ex

    query = st.text_input(
        "Your question",
        value=st.session_state.get("mgr_query", ""),
        placeholder="e.g. Compare AAPL vs MSFT risk-adjusted return",
        key="mgr_query_input",
    )

    if st.button("🚀 Run Orchestrator", use_container_width=True, type="primary") and query:
        with st.spinner("Running multi-agent pipeline…"):
            try:
                import asyncio
                from agents.orchestrator import run_orchestrator
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(run_orchestrator(query))
                finally:
                    loop.close()
            except Exception as e:
                st.error(f"Orchestrator error: {e}")
                return

        if not result:
            st.error("No response from orchestrator. Try rephrasing.")
            return

        # Top summary
        c1, c2, c3 = st.columns([1, 2, 1])
        with c1:
            st.metric("Intent", (result.get("intent") or "?").upper())
        with c2:
            tickers = result.get("tickers") or []
            if tickers:
                st.metric("Tickers", ", ".join(tickers))
        with c3:
            n_logs = len(result.get("decision_log") or [])
            st.metric("Agent steps", n_logs)

        st.divider()
        st.markdown("##### 📋 Recommendation")
        st.info(result.get("recommendation") or "*No recommendation generated.*")

        # Risk metrics (per ticker)
        risk_metrics = result.get("risk_metrics") or {}
        if risk_metrics:
            with st.expander("🎯 Risk Metrics (per ticker)", expanded=True):
                import pandas as pd
                rows = []
                for tk, m in risk_metrics.items():
                    if "error" in m:
                        continue
                    garch = m.get("garch_forecast") or {}
                    rows.append({
                        "Ticker":  tk,
                        "VaR 95%": m.get("var_95"),
                        "CVaR 95%": m.get("cvar_95"),
                        "Sharpe":  m.get("sharpe"),
                        "CF-VaR":  m.get("cornish_fisher_var"),
                        "GARCH α": garch.get("alpha"),
                        "GARCH β": garch.get("beta"),
                        "5d Vol forecast": garch.get("forecast_vol"),
                    })
                if rows:
                    st.dataframe(pd.DataFrame(rows).set_index("Ticker"), use_container_width=True)

        # Research summary
        if result.get("research_summary"):
            with st.expander("📰 Research Summary"):
                st.markdown(result["research_summary"])

        # Decision log (audit trail)
        with st.expander("🔍 Decision log (audit trail)"):
            import pandas as pd
            log = result.get("decision_log") or []
            if log:
                df = pd.DataFrame(log)
                cols_to_show = [c for c in ["timestamp", "agent", "message"] if c in df.columns]
                st.dataframe(df[cols_to_show], use_container_width=True)

        # Errors (if any)
        errors = result.get("errors") or []
        if errors:
            with st.expander(f"⚠ Errors ({len(errors)})"):
                for err in errors:
                    st.code(err)


main()
