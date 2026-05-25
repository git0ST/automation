"""AI Research page — Groq-powered news analysis and market summaries."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import os

st.set_page_config(page_title="AI Research · INTL", page_icon="🔬", layout="wide")


@st.cache_data(ttl=300)
def load_news_from_supabase(limit=50):
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


@st.cache_data(ttl=300)
def load_signals_from_supabase(limit=20):
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
    st.title("🔬 AI Research")
    st.caption("Powered by Groq (Llama 3) · Free tier · <200ms response time")

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
            st.info("No signals in Supabase yet.")
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
        st.markdown("Ask the **Manager Agent** any financial question:")
        st.markdown("_Examples: 'What is the VaR of NVDA?'  ·  'What is the market regime?'  ·  'Compute portfolio risk for AAPL MSFT AMZN'_")

        query = st.text_input("Your question", placeholder="e.g. What is the systemic risk level?")
        if st.button("Ask Agent", use_container_width=True) and query:
            with st.spinner("Routing query…"):
                import asyncio
                from agents.manager_agent import handle_query
                loop = asyncio.new_event_loop()
                result = loop.run_until_complete(handle_query(query))
                loop.close()

            st.subheader(f"Intent: {result.get('intent','?').upper()}")
            if result.get("tickers"):
                st.write("Tickers:", ", ".join(result["tickers"]))
            st.markdown(result.get("answer", "No answer generated."))


main()
