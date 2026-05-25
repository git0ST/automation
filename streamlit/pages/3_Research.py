"""AI Research page — Groq-powered news analysis and market summaries."""

import sys
from pathlib import Path

# ── Path setup — make both repo-root and projects/daily_digest importable ───
ROOT = Path(__file__).resolve().parent.parent.parent
for p in (ROOT, ROOT / "projects" / "daily_digest"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import streamlit as st
import os

st.set_page_config(page_title="AI Research · INTL", page_icon="🔬", layout="wide")

# ── Polish CSS: section gaps, expandable cards, smooth dividers ─────────────
st.markdown("""
<style>
.block-container { padding-top: 2rem; padding-bottom: 3rem; }
section.main > div.block-container { gap: 1.2rem; }
hr { margin: 1.5rem 0 !important; border-color: #1a1b2e !important; }
.stExpander { background: #0c0c18 !important; border: 1px solid #1a1b2e !important;
              border-radius: 8px !important; margin-bottom: 0.8rem !important; }
.stExpander > details > summary { font-weight: 600; padding: 0.6rem 1rem !important; }
div[data-testid="stMetric"] { margin-bottom: 0.8rem; }
div[data-testid="stVerticalBlock"] > div { margin-bottom: 0.6rem; }
.stTabs [data-baseweb="tab-list"] { gap: 8px; }
.stTabs [data-baseweb="tab"] { padding: 0.5rem 1rem; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=180)   # 3 min — keep feed fresh
def load_news_from_supabase(limit=100):  # max out the news feed
    try:
        url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_ANON_KEY")
        if not url or not key:
            return []
        from supabase import create_client
        client = create_client(url, key)
        return (client.table("articles")
                .select("*")
                .order("terminal_score", desc=True)
                .limit(limit)
                .execute()).data or []
    except Exception:
        return []


@st.cache_data(ttl=180)
def load_signals_from_supabase(limit=40):  # more signals per refresh
    try:
        url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_ANON_KEY")
        if not url or not key:
            return []
        from supabase import create_client
        client = create_client(url, key)
        return (client.table("signals")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()).data or []
    except Exception:
        return []


def main():
    col_title, col_refresh = st.columns([6, 1])
    with col_title:
        st.title("🔬 AI Research")
        st.caption("Powered by Groq (Llama 3) · Free tier · <200ms response time")
    with col_refresh:
        st.write("")
        if st.button("🔄 Refresh", use_container_width=True):
            load_news_from_supabase.clear()
            load_signals_from_supabase.clear()
            st.rerun()
    st.divider()

    from shared.groq_client import is_ai_available, ai_provider_name
    if is_ai_available():
        st.success(f"✓ AI Active: {ai_provider_name()}", icon="🤖")
    else:
        st.warning(
            "No AI provider configured. Add **GROQ_API_KEY** to Streamlit secrets "
            "for free AI analysis (groq.com — no credit card needed).",
            icon="⚠️",
        )

    tab_news, tab_signals, tab_custom = st.tabs(["📰 News Analysis", "⚡ Signal Interpreter", "💬 Custom Query"])

    # ── News Analysis tab ──────────────────────────────────────────────────
    with tab_news:
        items = load_news_from_supabase()
        if not items:
            st.info("No news in Supabase yet. Run the pipeline to populate data.")
            return

        col1, col2 = st.columns([1, 1])
        with col1:
            source_filter = st.selectbox(
                "Filter by source",
                ["All"] + sorted(set(it.get("source","?") for it in items)),
            )
        with col2:
            sentiment_filter = st.selectbox("Sentiment", ["All", "bullish", "bearish", "neutral"])

        filtered = [
            it for it in items
            if (source_filter == "All" or it.get("source") == source_filter)
            and (sentiment_filter == "All" or it.get("sentiment_label") == sentiment_filter)
        ]

        if st.button("🤖 Detect Cross-Source Trends", use_container_width=True):
            with st.spinner("Analysing trends via Groq…"):
                import asyncio
                from agents.research_agent import detect_trends
                loop = asyncio.new_event_loop()
                trends = loop.run_until_complete(detect_trends(filtered[:30]))
                loop.close()
            st.subheader("Top Trends")
            st.write(trends)
            st.divider()

        st.write(f"**{len(filtered)} items** — click any to get AI summary")
        for it in filtered[:20]:
            with st.expander(f"[{it.get('source','?').upper()}] {it.get('title','—')[:80]}"):
                col_a, col_b = st.columns([2, 1])
                with col_a:
                    if it.get("preview"):
                        st.caption(it["preview"][:400])
                    if it.get("url"):
                        st.markdown(f"[Read full article →]({it['url']})")
                with col_b:
                    sent = it.get("sentiment_label", "neutral")
                    icon = "▲" if sent == "bullish" else "▼" if sent == "bearish" else "·"
                    st.metric("Sentiment", f"{icon} {sent.title()}")
                    st.metric("Score", f"{it.get('terminal_score',0):.0f}")
                    if st.button("AI Summary", key=f"sum_{it.get('id','')}"):
                        with st.spinner("Summarising…"):
                            import asyncio
                            from agents.research_agent import summarise_item
                            loop = asyncio.new_event_loop()
                            s = loop.run_until_complete(summarise_item(it))
                            loop.close()
                        st.success(s)

    # ── Signal Interpreter tab ─────────────────────────────────────────────
    with tab_signals:
        signals = load_signals_from_supabase()
        if not signals:
            st.warning(
                "⚠ **No signals in Supabase yet.** The pipeline cron hasn't populated insider/options/congress/FINRA data.\n\n"
                "**To fix:** Trigger the pipeline at "
                "https://github.com/git0ST/automation/actions/workflows/digest.yml — "
                "click 'Run workflow' → wait ~3-5 min → refresh this page.",
                icon="⚠️",
            )
            with st.expander("ℹ️ What are signals?"):
                st.markdown("""
                Signals are **non-public-yet alpha-generating events** the pipeline pulls daily:
                - 🏛️ **SEC EDGAR insider trading** (Form 4) — executives buying/selling stock
                - 📈 **Unusual options flow** — large block trades hinting at smart-money positioning
                - 🏛️ **Congressional trades** — disclosed transactions by US Senators/Reps
                - 📉 **FINRA short interest** — short positions building up

                Once populated, this tab will show interpreted signals with AI commentary.
                """)
            return

        source_map = {"edgar": "SEC Insider", "options": "Options Flow", "congress": "Congress", "finra": "FINRA Short"}
        for sig in signals[:15]:
            src_label = source_map.get(sig.get("source"), sig.get("source","?").upper())
            sent = sig.get("sentiment_label", "neutral")
            icon = "▲" if sent == "bullish" else "▼" if sent == "bearish" else "—"
            with st.expander(f"{icon} [{src_label}] {sig.get('title','—')[:75]}"):
                if sig.get("preview"):
                    st.write(sig["preview"][:300])
                if st.button("Interpret Signal", key=f"sig_{sig.get('id','')}"):
                    with st.spinner("Interpreting via Groq…"):
                        import asyncio
                        from agents.research_agent import interpret_signal
                        loop = asyncio.new_event_loop()
                        interp = loop.run_until_complete(interpret_signal(sig))
                        loop.close()
                    st.info(interp)

    # ── Custom Query tab ───────────────────────────────────────────────────
    with tab_custom:
        st.markdown("### 🤖 Manager Agent — Natural Language Query")
        st.caption("Ask anything about markets, risk, regime, or specific tickers. Routes to the right agent automatically.")

        # Pre-built example chips
        st.markdown("**Quick examples** (click to fill):")
        cols = st.columns(4)
        examples = [
            "What is the VaR of NVDA?",
            "What is the current market regime?",
            "Compute portfolio risk for AAPL MSFT AMZN GOOGL",
            "Show RSI and SMA for TSLA",
        ]
        for col, ex in zip(cols, examples):
            with col:
                if st.button(ex, use_container_width=True, key=f"ex_{ex[:20]}"):
                    st.session_state["manager_query"] = ex

        query = st.text_input(
            "Your question",
            value=st.session_state.get("manager_query", ""),
            placeholder="e.g. What is the systemic risk level?",
            key="manager_query_input",
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
                    result = None

            if result:
                # Show intent classification
                col_intent, col_tickers = st.columns([1, 2])
                with col_intent:
                    st.metric("Intent", result.get("intent", "?").upper())
                with col_tickers:
                    if result.get("tickers"):
                        st.metric("Tickers detected", ", ".join(result["tickers"]))

                st.divider()

                # Show answer
                answer = result.get("answer") or "No answer generated. Try rephrasing your query or check GROQ_API_KEY in secrets."
                st.markdown("### Answer")
                st.markdown(answer)

                # Show structured data if present (for VaR, portfolio queries etc)
                if result.get("data"):
                    with st.expander("📊 Raw data"):
                        st.json(result["data"])


main()
