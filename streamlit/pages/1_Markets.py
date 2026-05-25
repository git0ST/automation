"""Markets deep-dive page — live prices, charts, sector breakdown."""

import sys
from pathlib import Path

# ── Path setup ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent
for p in (ROOT, ROOT / "projects" / "daily_digest"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import streamlit as st
import os

st.set_page_config(page_title="Markets · INTL", page_icon="📈", layout="wide")

# ── Polish CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
.block-container { padding-top: 2rem; padding-bottom: 3rem; }
hr { margin: 1.5rem 0 !important; border-color: #1a1b2e !important; }
.stExpander { background: #0c0c18 !important; border: 1px solid #1a1b2e !important;
              border-radius: 8px !important; margin-bottom: 0.8rem !important; }
div[data-testid="stMetric"] { margin-bottom: 0.8rem; }
.stDataFrame { margin: 0.8rem 0; }
section.main h3 { margin-top: 1.5rem !important; }
</style>
""", unsafe_allow_html=True)

# ── Watchlists — expanded with more tickers per sector for richer coverage ──
TICKERS_BY_SECTOR = {
    "Indices":      ["^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX", "^FTSE", "^N225"],
    "Mega Cap":     ["NVDA", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "TSLA", "AVGO", "ORCL"],
    "AI/Semis":     ["AMD", "INTC", "QCOM", "ARM", "SMCI", "TSM", "MU", "MRVL", "ASML"],
    "Financials":   ["JPM", "GS", "MS", "BAC", "BRK-B", "WFC", "C", "BLK", "V", "MA"],
    "Energy":       ["XOM", "CVX", "COP", "SLB", "EOG", "OXY"],
    "Healthcare":   ["UNH", "LLY", "JNJ", "MRK", "PFE", "ABBV"],
    "Consumer":    ["WMT", "COST", "HD", "MCD", "NKE", "SBUX"],
    "Crypto":       ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"],
    "ETFs":         ["SPY", "QQQ", "IWM", "DIA", "VTI", "GLD", "TLT"],
}

@st.cache_data(ttl=600, show_spinner=False)  # 10-min cache (Yahoo delay = 15min anyway)
def fetch_prices(tickers: tuple, period: str = "3mo"):
    """Fetch OHLCV data for charting. Cached 10 min. Wider history for deeper charts."""
    try:
        import yfinance as yf
        data = {}
        # Batch download is much faster than individual calls
        tickers_str = " ".join(t for t in tickers if not t.startswith("^"))
        indices     = [t for t in tickers if t.startswith("^")]

        for ticker in tickers:
            try:
                t    = yf.Ticker(ticker)
                hist = t.history(period=period, interval="1d", auto_adjust=True)
                if hist.empty:
                    continue
                data[ticker] = {
                    "close":   [round(x, 2) for x in hist["Close"].tolist()],
                    "dates":   [d.strftime("%m/%d") for d in hist.index],
                    "price":   round(hist["Close"].iloc[-1], 2),
                    "open":    round(hist["Open"].iloc[-1], 2),
                    "high":    round(hist["High"].iloc[-1], 2),
                    "low":     round(hist["Low"].iloc[-1], 2),
                    "volume":  int(hist["Volume"].iloc[-1]),
                    "chg_1d":  round((hist["Close"].iloc[-1] / hist["Close"].iloc[-2] - 1) * 100, 2)
                                if len(hist) >= 2 else 0,
                    "chg_1mo": round((hist["Close"].iloc[-1] / hist["Close"].iloc[0]  - 1) * 100, 2)
                                if len(hist) >= 2 else 0,
                }
            except Exception:
                continue
        return data
    except Exception:
        return {}


def main():
    col_title, col_refresh = st.columns([6, 1])
    with col_title:
        st.title("📈 Markets")
        st.caption("Yahoo Finance · 15-minute delayed · free tier · max-coverage watchlists")
    with col_refresh:
        st.write("")
        if st.button("🔄 Refresh", use_container_width=True):
            fetch_prices.clear()
            st.rerun()

    st.divider()

    # Sector + period selectors
    csec, cper = st.columns([2, 1])
    with csec:
        sector = st.selectbox("Sector", list(TICKERS_BY_SECTOR.keys()), index=0)
    with cper:
        period = st.selectbox("History", ["1mo", "3mo", "6mo", "1y", "2y"], index=1)
    tickers = tuple(TICKERS_BY_SECTOR[sector])

    with st.spinner(f"Fetching {len(tickers)} tickers from Yahoo Finance…"):
        data = fetch_prices(tickers, period=period)

    if not data:
        st.error("Failed to load market data. Check yfinance installation.")
        return

    # ── Price table ────────────────────────────────────────────────────────
    st.subheader(f"{sector} Prices")
    rows = []
    for ticker, d in data.items():
        rows.append({
            "Ticker":    ticker,
            "Price":     f"${d['price']:,.2f}",
            "1D Chg":    f"{d['chg_1d']:+.2f}%",
            "1Mo Chg":   f"{d['chg_1mo']:+.2f}%",
            "Open":      f"${d['open']:,.2f}",
            "High":      f"${d['high']:,.2f}",
            "Low":       f"${d['low']:,.2f}",
            "Volume":    f"{d['volume']:,}" if d.get("volume") else "—",
        })
    if rows:
        import pandas as pd
        df = pd.DataFrame(rows).set_index("Ticker")
        # Style positive/negative changes
        def color_pct(val):
            if "+" in str(val): return "color: #22d472"
            if "-" in str(val): return "color: #f75050"
            return ""
        st.dataframe(df.style.applymap(color_pct, subset=["1D Chg", "1Mo Chg"]), use_container_width=True)

    st.divider()

    # ── Price chart (expandable, can compare multiple tickers) ─────────────
    with st.expander(f"📊 Price Chart — {period} history", expanded=True):
        chart_tickers = st.multiselect(
            "Compare tickers",
            list(data.keys()),
            default=[list(data.keys())[0]] if data else [],
            help="Select 1+ tickers to overlay on the chart",
        )
        if chart_tickers:
            import pandas as pd
            # Build a wide df: one column per ticker (normalised to 100 at start for comparison)
            frames = {}
            for tk in chart_tickers:
                if tk in data and data[tk].get("close"):
                    closes = data[tk]["close"]
                    base = closes[0] if closes else 1
                    frames[tk] = [round(c / base * 100, 2) for c in closes]
            if frames:
                # All tickers in one sector share the same date axis
                dates = data[chart_tickers[0]]["dates"]
                chart_df = pd.DataFrame(frames, index=dates)
                st.line_chart(chart_df, use_container_width=True, height=400)
                st.caption("Normalised to 100 at start of window for comparison.")

    # ── Market commentary ──────────────────────────────────────────────────
    if st.button("🤖 Generate AI Market Commentary", use_container_width=True):
        from shared.groq_client import chat, is_ai_available
        if not is_ai_available():
            st.warning("Add GROQ_API_KEY or GOOGLE_API_KEY to Streamlit secrets for AI commentary.")
        else:
            movers = sorted(data.items(), key=lambda x: abs(x[1]["chg_1d"]), reverse=True)[:5]
            prompt = "\n".join(f"{t}: ${d['price']:,.2f} ({d['chg_1d']:+.2f}% today, {d['chg_1mo']:+.2f}% 1mo)" for t, d in movers)
            with st.spinner("Generating commentary via Groq…"):
                commentary = chat(
                    prompt,
                    system="You are a Bloomberg market analyst. Write 3 sentences on today's top movers, why they moved, and what to watch.",
                    model="smart", max_tokens=200,
                )
            st.info(commentary)


main()
