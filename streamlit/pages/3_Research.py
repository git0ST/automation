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
    """Manager Agent — natural language query routing."""
    st.markdown("#### 🤖 Manager Agent")
    st.caption("Ask any market question — routes to math/research/regime agents automatically.")

    # Quick example chips
    st.markdown("**Quick prompts** (click to fill):")
    cols = st.columns(4)
    examples = [
        "VaR of NVDA",
        "Current market regime",
        "Portfolio risk: AAPL MSFT GOOGL",
        "RSI and SMA for TSLA",
    ]
    for col, ex in zip(cols, examples):
        with col:
            if st.button(ex, use_container_width=True, key=f"ex_{hash(ex)}"):
                st.session_state["mgr_query"] = ex

    query = st.text_input(
        "Your question",
        value=st.session_state.get("mgr_query", ""),
        placeholder="e.g. What is the systemic risk level right now?",
        key="mgr_query_input",
    )

    if st.button("🚀 Ask Agent", use_container_width=True, type="primary") and query:
        with st.spinner("Routing query through Manager Agent…"):
            try:
                import asyncio
                from agents.manager_agent import handle_query
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(handle_query(query))
                finally:
                    loop.close()
            except Exception as e:
                st.error(f"Agent error: {e}")
                return

        if not result:
            st.error("No response from agent. Try rephrasing.")
            return

        # Intent + tickers detection
        c1, c2 = st.columns([1, 2])
        with c1:
            st.metric("Intent", (result.get("intent") or "?").upper())
        with c2:
            tickers = result.get("tickers") or []
            if tickers:
                st.metric("Tickers", ", ".join(tickers))

        st.divider()
        st.markdown("##### Answer")
        answer = result.get("answer") or (
            "*No answer generated. Either GROQ_API_KEY is missing or the query couldn't be routed.*"
        )
        st.markdown(answer)

        # Show structured data if present
        if result.get("data"):
            with st.expander("📊 Raw data"):
                st.json(result["data"])


main()
