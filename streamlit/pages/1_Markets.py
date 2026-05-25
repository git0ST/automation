"""Markets deep-dive page — live prices, charts, sector breakdown."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import os

st.set_page_config(page_title="Markets · INTL", page_icon="📈", layout="wide")

TICKERS_BY_SECTOR = {
    "Indices":    ["^GSPC", "^IXIC", "^DJI", "^RUT"],
    "Mega Cap":   ["NVDA", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "TSLA"],
    "AI/Semis":   ["AMD", "INTC", "QCOM", "ARM", "SMCI"],
    "Financials": ["JPM", "GS", "MS", "BAC", "BRK-B"],
    "Crypto":     ["BTC-USD", "ETH-USD", "SOL-USD"],
}

@st.cache_data(ttl=900, show_spinner=False)  # 15-min cache (matches free API delay)
def fetch_prices(tickers: tuple):
    """Fetch OHLCV data for charting. Cached 15 min to match data delay."""
    try:
        import yfinance as yf
        data = {}
        # Batch download is much faster than individual calls
        tickers_str = " ".join(t for t in tickers if not t.startswith("^"))
        indices     = [t for t in tickers if t.startswith("^")]

        for ticker in tickers:
            try:
                t    = yf.Ticker(ticker)
                hist = t.history(period="1mo", interval="1d", auto_adjust=True)
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
    st.title("📈 Markets")
    st.caption("Yahoo Finance · 15-minute delayed · free tier")

    # Sector selector
    sector = st.selectbox("Sector", list(TICKERS_BY_SECTOR.keys()), index=0)
    tickers = tuple(TICKERS_BY_SECTOR[sector])

    with st.spinner("Fetching market data…"):
        data = fetch_prices(tickers)

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

    # ── Price chart ────────────────────────────────────────────────────────
    st.subheader("Price Chart (1 Month)")
    chart_ticker = st.selectbox("Select ticker to chart", list(data.keys()))
    if chart_ticker and chart_ticker in data:
        d = data[chart_ticker]
        import pandas as pd
        chart_df = pd.DataFrame({"Date": d["dates"], "Price": d["close"]}).set_index("Date")
        st.line_chart(chart_df, use_container_width=True)

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
