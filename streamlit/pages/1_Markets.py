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
        # pandas >= 2.1: Styler.applymap removed → use Styler.map
        styled = df.style.map(color_pct, subset=["1D Chg", "1Mo Chg"]) \
                 if hasattr(df.style, "map") \
                 else df.style.applymap(color_pct, subset=["1D Chg", "1Mo Chg"])
        st.dataframe(styled, use_container_width=True)

    st.divider()

    # ── Sector Heatmap (treemap — Reddit-style sector view) ──────────────────
    with st.expander("🔥 Sector Heatmap — sized by market cap, colored by 1-day change", expanded=True):
        try:
            import plotly.express as px
            import pandas as pd
            tm_rows = []
            for tk, d in data.items():
                # Use 1Mo change for richer color signal; fallback to 1D
                color_val = d.get("chg_1d", 0)
                # Size = absolute price as a proxy for "market significance"
                # (we don't have free market cap data — price magnitude is a reasonable visual proxy)
                size_val = max(abs(d.get("price", 1)), 1)
                tm_rows.append({
                    "ticker":   tk,
                    "label":    f"{tk}<br>{color_val:+.2f}%",
                    "size":     size_val,
                    "change":   color_val,
                    "price":    d.get("price", 0),
                    "volume":   d.get("volume", 0),
                })
            tm_df = pd.DataFrame(tm_rows)
            if not tm_df.empty:
                fig = px.treemap(
                    tm_df,
                    path=[px.Constant(sector), "ticker"],
                    values="size",
                    color="change",
                    color_continuous_scale=[
                        (0.0, "#7c1d1d"),   # deep red
                        (0.35, "#f75050"),  # red
                        (0.5, "#1a1b2e"),   # neutral dark
                        (0.65, "#22d472"),  # green
                        (1.0, "#0d5e2a"),   # deep green
                    ],
                    color_continuous_midpoint=0,
                    range_color=[-5, 5],
                    custom_data=["price", "change", "volume"],
                    hover_data={"size": False, "change": ":.2f", "price": ":.2f"},
                )
                fig.update_traces(
                    textinfo="label+text",
                    text=tm_df.apply(
                        lambda r: f"${r['price']:,.2f}<br><b>{r['change']:+.2f}%</b>", axis=1),
                    textfont=dict(size=14, color="white"),
                    marker=dict(line=dict(color="#0a0a14", width=2)),
                    hovertemplate="<b>%{label}</b><br>Price: $%{customdata[0]:,.2f}<br>1D: %{customdata[1]:+.2f}%<extra></extra>",
                )
                fig.update_layout(
                    margin=dict(l=0, r=0, t=10, b=0),
                    paper_bgcolor="#0a0a14",
                    plot_bgcolor="#0a0a14",
                    font=dict(color="#c8cce0", family="Inter, sans-serif"),
                    height=500,
                    coloraxis_colorbar=dict(
                        title="1D %", thickness=12, len=0.7,
                        tickfont=dict(color="#c8cce0"),
                    ),
                )
                st.plotly_chart(fig, use_container_width=True, theme=None)
                st.caption("Treemap: tile size = price magnitude · color = 1-day % change · green=up, red=down.")
            else:
                st.info("No ticker data to render heatmap.")
        except ImportError:
            st.warning("Install plotly for the sector heatmap: `pip install plotly`")

    st.divider()

    # ── Price chart — multi-ticker comparison with per-ticker date alignment ─
    with st.expander(f"📊 Price Chart — {period} history (normalised to 100)", expanded=True):
        chart_tickers = st.multiselect(
            "Compare tickers",
            list(data.keys()),
            default=[list(data.keys())[0]] if data else [],
            help="Select 1+ tickers to overlay on the chart",
        )
        if chart_tickers:
            import pandas as pd
            # FIX: build per-ticker Series with their OWN dates index, then concat on
            # the outer join. Different tickers (esp crypto vs stocks) have different
            # trading days — assuming a shared date index causes ValueError when
            # lengths differ.
            series = []
            for tk in chart_tickers:
                if tk in data and data[tk].get("close") and data[tk].get("dates"):
                    closes = data[tk]["close"]
                    dates  = data[tk]["dates"]
                    if not closes or not dates or len(closes) != len(dates):
                        continue
                    base = closes[0] if closes[0] else 1
                    normalised = [round(c / base * 100, 2) for c in closes]
                    s = pd.Series(normalised, index=pd.to_datetime(dates, format="%m/%d", errors="coerce"),
                                  name=tk)
                    series.append(s)
            if series:
                chart_df = pd.concat(series, axis=1).sort_index()
                # Forward-fill so crypto-stock comparisons don't have weekend gaps
                chart_df = chart_df.ffill()
                try:
                    import plotly.graph_objects as go
                    fig = go.Figure()
                    palette = ["#22d472", "#4da6ff", "#e3b341", "#f07030",
                               "#f75050", "#b16ee8", "#48d1cc", "#ffa07a"]
                    for i, col in enumerate(chart_df.columns):
                        fig.add_trace(go.Scatter(
                            x=chart_df.index, y=chart_df[col],
                            mode="lines", name=col,
                            line=dict(color=palette[i % len(palette)], width=2),
                        ))
                    fig.add_hline(y=100, line_dash="dot", line_color="#5a5e7a",
                                  annotation_text="Start (100)", annotation_position="right")
                    fig.update_layout(
                        height=450,
                        margin=dict(l=10, r=10, t=20, b=10),
                        paper_bgcolor="#0a0a14",
                        plot_bgcolor="#0a0a14",
                        font=dict(color="#c8cce0"),
                        xaxis=dict(gridcolor="#1a1b2e", showgrid=True),
                        yaxis=dict(gridcolor="#1a1b2e", showgrid=True, title="Index (100 = start)"),
                        legend=dict(bgcolor="#0c0c18", bordercolor="#1a1b2e", borderwidth=1),
                        hovermode="x unified",
                    )
                    st.plotly_chart(fig, use_container_width=True, theme=None)
                except ImportError:
                    st.line_chart(chart_df, use_container_width=True, height=400)
                st.caption("All tickers normalised to 100 at start of window for relative comparison.")

    st.divider()

    # ── Top Movers + AI commentary ────────────────────────────────────────────
    with st.expander("🚀 Top Movers (1D)", expanded=False):
        movers = sorted(data.items(), key=lambda x: abs(x[1].get("chg_1d", 0)), reverse=True)[:10]
        import pandas as pd
        mv_df = pd.DataFrame([
            {"Ticker": t, "Price": f"${d['price']:,.2f}",
             "1D %": f"{d.get('chg_1d', 0):+.2f}%",
             "1Mo %": f"{d.get('chg_1mo', 0):+.2f}%",
             "Volume": f"{d.get('volume', 0):,}" if d.get('volume') else "—"}
            for t, d in movers
        ]).set_index("Ticker")
        st.dataframe(mv_df, use_container_width=True)

    # ── Market commentary ─────────────────────────────────────────────────────
    if st.button("🤖 Generate AI Market Commentary", use_container_width=True):
        from shared.groq_client import chat, is_ai_available
        if not is_ai_available():
            st.warning("Add GROQ_API_KEY or GOOGLE_API_KEY to Streamlit secrets for AI commentary.")
        else:
            movers = sorted(data.items(), key=lambda x: abs(x[1].get("chg_1d", 0)), reverse=True)[:5]
            prompt = "\n".join(
                f"{t}: ${d['price']:,.2f} ({d.get('chg_1d', 0):+.2f}% today, {d.get('chg_1mo', 0):+.2f}% 1mo)"
                for t, d in movers
            )
            with st.spinner("Generating commentary via Groq…"):
                commentary = chat(
                    prompt,
                    system="You are a Bloomberg market analyst. Write 3 sentences on today's top movers, why they moved, and what to watch.",
                    model="smart", max_tokens=200,
                )
            st.info(commentary)


main()
