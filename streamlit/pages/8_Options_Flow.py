"""Options Flow — unusual activity + smart money tracker.

Reads from the existing `signals` table populated by the `options` source.
Surfaces large block trades, unusual P/C ratio, and institutional positioning.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for p in (ROOT, ROOT / "projects" / "daily_digest"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import streamlit as st

st.set_page_config(page_title="Options Flow · INTL", page_icon="⚡", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _theme      import apply_theme, COLORS, status_pill
from _data       import supabase_client
from _components import TICKER_META
apply_theme()


# Plain-English explanations
EXPLAIN = {
    "unusual_volume":
        "Volume meaningfully above the typical daily average for this strike/expiration. "
        "Smart-money traders often leave a footprint here — large positions can't be "
        "hidden in low-volume contracts.",
    "pc_ratio":
        "Put/Call ratio: total put volume ÷ total call volume. >1.2 = bearish positioning. "
        "<0.7 = bullish positioning. ~0.9-1.0 is neutral.",
    "iv_skew":
        "Difference between OTM-put IV and OTM-call IV. Positive skew = puts are more "
        "expensive than calls → market hedging against downside.",
    "whale_trade":
        "Single block trade > $100K notional. Institutions often have to leave this "
        "footprint when entering size. Frequently precedes large moves in the underlying.",
}


@st.cache_data(ttl=120, show_spinner=False)
def load_options_signals(limit: int = 200) -> list[dict]:
    """Pull options-source signals from Supabase."""
    client = supabase_client()
    if not client:
        return []
    try:
        rows = (client.table("signals")
                .select("*")
                .eq("source", "options")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()).data or []
        return [r for r in rows if isinstance(r, dict)]
    except Exception:
        return []


def main():
    col_t, col_r = st.columns([6, 1])
    with col_t:
        st.title("⚡ Options Flow")
        st.caption("Unusual activity · whale block trades · sentiment positioning")
    with col_r:
        st.write("")
        if st.button("🔄 Refresh", use_container_width=True):
            load_options_signals.clear()
            st.rerun()

    signals = load_options_signals(limit=200)

    if not signals:
        st.warning(
            "📭 **No options data yet.** The `options` source in the pipeline pulls "
            "unusual activity from public feeds. Trigger the pipeline to populate.",
            icon="📭",
        )
        st.link_button(
            "🚀 Run pipeline",
            "https://github.com/git0ST/automation/actions/workflows/digest.yml",
            use_container_width=True,
            type="primary",
        )
        return

    # ── Summary KPIs ──────────────────────────────────────────────────────────
    bull = sum(1 for s in signals if s.get("sentiment_label") == "bullish")
    bear = sum(1 for s in signals if s.get("sentiment_label") == "bearish")
    total = max(len(signals), 1)
    pc_ratio_proxy = bear / max(bull, 1) if bull > 0 else float("inf")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total signals", len(signals),
              delta=f"24h: {sum(1 for s in signals if _within_hours(s, 24))}",
              delta_color="off")
    c2.metric("Bullish flow", f"{bull/total*100:.0f}%",
              delta=f"{bull} signals", delta_color="off",
              help="% of recent options signals that lean bullish (call buying, put selling)")
    c3.metric("Bearish flow", f"{bear/total*100:.0f}%",
              delta=f"{bear} signals", delta_color="off",
              help="% bearish (put buying, call selling, downside hedging)")
    pc_label = "Bearish" if pc_ratio_proxy > 1.2 else "Bullish" if pc_ratio_proxy < 0.7 else "Neutral"
    c4.metric("P/C proxy", f"{pc_ratio_proxy:.2f}", delta=pc_label, delta_color="off",
              help=EXPLAIN["pc_ratio"])

    st.divider()

    # ── Per-ticker aggregation ────────────────────────────────────────────────
    st.markdown("#### 📊 Top tickers by options activity")
    st.caption("Tickers appearing most in recent options flow. High count = unusual interest.")

    from collections import Counter
    ticker_counts = Counter()
    ticker_sentiment = {}
    for s in signals:
        # Try to extract ticker from title or entities
        entities = s.get("entities") or []
        ticks = entities if isinstance(entities, list) else []
        if not ticks:
            # Heuristic: first word of title if it's all-caps and ≤5 chars
            title = s.get("title", "")
            first = title.split()[0] if title else ""
            if first.isupper() and 1 <= len(first) <= 5 and first.isalpha():
                ticks = [first]
        for t in ticks[:3]:
            t = t.upper()
            ticker_counts[t] += 1
            if t not in ticker_sentiment:
                ticker_sentiment[t] = {"bull": 0, "bear": 0}
            sent = s.get("sentiment_label", "neutral")
            if sent == "bullish":
                ticker_sentiment[t]["bull"] += 1
            elif sent == "bearish":
                ticker_sentiment[t]["bear"] += 1

    if ticker_counts:
        import pandas as pd
        rows = []
        for t, count in ticker_counts.most_common(20):
            sent = ticker_sentiment.get(t, {"bull": 0, "bear": 0})
            bias = ("BULLISH" if sent["bull"] > sent["bear"]
                    else "BEARISH" if sent["bear"] > sent["bull"]
                    else "MIXED")
            meta = TICKER_META.get(t, {})
            rows.append({
                "Ticker":   t,
                "Name":     meta.get("name", t)[:30],
                "Signals":  count,
                "Bull":     sent["bull"],
                "Bear":     sent["bear"],
                "Bias":     bias,
            })
        st.dataframe(pd.DataFrame(rows).set_index("Ticker"),
                     use_container_width=True,
                     column_config={
                         "Signals": st.column_config.ProgressColumn(
                             format="%d", min_value=0,
                             max_value=max(c for _, c in ticker_counts.most_common(20)),
                         ),
                     })

    st.divider()

    # ── Recent flow ───────────────────────────────────────────────────────────
    st.markdown("#### 🕒 Recent options activity")

    # Filters
    fcol1, fcol2 = st.columns(2)
    with fcol1:
        sentiment_filter = st.selectbox("Sentiment", ["All", "bullish", "bearish", "neutral"])
    with fcol2:
        show_n = st.selectbox("Show", [25, 50, 100], index=0)

    filtered = [s for s in signals
                if sentiment_filter == "All" or s.get("sentiment_label") == sentiment_filter]

    for sig in filtered[:show_n]:
        sent = sig.get("sentiment_label", "neutral")
        icon = "▲" if sent == "bullish" else "▼" if sent == "bearish" else "—"
        color = "#00d68f" if sent == "bullish" else "#ff5773" if sent == "bearish" else "#8b93a7"
        ts = sig.get("created_at", "")[:16].replace("T", " ")
        title = sig.get("title", "—")
        preview = (sig.get("preview") or "")[:200]

        st.markdown(
            f'<div style="background:#131825;border:1px solid #1f2937;border-radius:6px;'
            f'padding:12px 16px;margin-bottom:8px">'
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">'
            f'<span style="color:{color};font-weight:700;font-size:14px">{icon}</span>'
            f'<span style="color:#4c8bf5;font-size:11px;font-weight:600">OPTIONS</span>'
            f'<span style="margin-left:auto;color:#5a6378;font-size:11px;font-family:IBM Plex Mono,monospace">{ts}</span>'
            f'</div>'
            f'<div style="color:#e6e9f0;font-weight:500;font-size:13px;line-height:1.4">{title}</div>'
            f'{("<div style=color:#8b93a7;font-size:11px;margin-top:4px>" + preview + "</div>") if preview else ""}'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.divider()
    with st.expander("ℹ️ How to read options flow"):
        st.markdown(f"""
        - **Put/Call ratio**: {EXPLAIN['pc_ratio']}
        - **Unusual volume**: {EXPLAIN['unusual_volume']}
        - **Whale trades**: {EXPLAIN['whale_trade']}
        - **IV skew**: {EXPLAIN['iv_skew']}

        **Why this matters for HFT/HFI**: Options flow is one of the few real-time
        windows into institutional positioning. Smart money pre-positions in options
        before catalysts (earnings, FOMC, M&A) — retail flow follows price.
        """)


def _within_hours(signal: dict, hours: int) -> bool:
    """True if signal is within last N hours."""
    try:
        from datetime import datetime, timezone, timedelta
        ts = signal.get("created_at")
        if not ts:
            return False
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt) < timedelta(hours=hours)
    except Exception:
        return False


main()
