"""
Markets page — sector navigator, sector heatmap, multi-ticker comparison, AI commentary.

Inspired by:
  - TradingView sector heatmap (treemap with color-coded performance)
  - Bloomberg sector navigator (tabbed asset class drilldown)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for p in (ROOT, ROOT / "projects" / "daily_digest"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import streamlit as st

st.set_page_config(page_title="Markets · INTL", page_icon="📈", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _theme      import apply_theme, COLORS
from _components import render_ticker_grid, ticker_card, TICKER_META
apply_theme()
from _terminal_chrome import render_chrome
render_chrome("Markets")


# ── Sector watchlists (curated for depth + speed) ─────────────────────────────
TICKERS_BY_SECTOR = {
    "Indices":      ["^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX", "^FTSE", "^N225"],
    "Mega Cap":     ["NVDA", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "TSLA", "AVGO", "ORCL"],
    "AI / Semis":   ["AMD", "INTC", "QCOM", "ARM", "SMCI", "TSM", "MU", "MRVL", "ASML"],
    "Financials":   ["JPM", "GS", "MS", "BAC", "BRK-B", "WFC", "C", "BLK", "V", "MA"],
    "Energy":       ["XOM", "CVX", "COP", "SLB", "EOG", "OXY"],
    "Healthcare":   ["UNH", "LLY", "JNJ", "MRK", "PFE", "ABBV"],
    "Consumer":     ["WMT", "COST", "HD", "MCD", "NKE", "SBUX"],
    "Crypto":       ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"],
    "ETFs":         ["SPY", "QQQ", "IWM", "DIA", "VTI", "GLD", "TLT"],
}


@st.cache_data(ttl=600, show_spinner=False)
def fetch_prices(tickers: tuple, period: str = "3mo") -> dict:
    """Batched fetch — single yfinance call for N tickers."""
    try:
        import yfinance as yf
        data = {}
        for ticker in tickers:
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period=period, interval="1d", auto_adjust=True)
                if hist.empty:
                    continue
                data[ticker] = {
                    "close":   [round(x, 2) for x in hist["Close"].tolist()],
                    "dates":   [d.strftime("%Y-%m-%d") for d in hist.index],
                    "price":   round(hist["Close"].iloc[-1], 2),
                    "open":    round(hist["Open"].iloc[-1], 2),
                    "high":    round(hist["High"].iloc[-1], 2),
                    "low":     round(hist["Low"].iloc[-1], 2),
                    "volume":  int(hist["Volume"].iloc[-1]),
                    "chg_1d":  round((hist["Close"].iloc[-1] / hist["Close"].iloc[-2] - 1) * 100, 2)
                                if len(hist) >= 2 else 0,
                    "chg_1mo": round((hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100, 2)
                                if len(hist) >= 2 else 0,
                }
            except Exception:
                continue
        return data
    except Exception:
        return {}


def main():
    col_t, col_r = st.columns([6, 1])
    with col_t:
        st.title("📈 Markets")
        st.caption("Sector navigator · Heatmaps · Multi-asset comparison · Yahoo Finance free tier")
    with col_r:
        st.write("")
        if st.button("🔄 Refresh", use_container_width=True):
            fetch_prices.clear()
            st.rerun()

    st.divider()

    # ── Sector + period selectors ─────────────────────────────────────────────
    csec, cper = st.columns([3, 1])
    with csec:
        sector = st.selectbox("Sector", list(TICKERS_BY_SECTOR.keys()), index=0)
    with cper:
        period = st.selectbox("History window", ["1mo", "3mo", "6mo", "1y", "2y"], index=1)
    tickers = tuple(TICKERS_BY_SECTOR[sector])

    with st.spinner(f"Loading {len(tickers)} tickers from Yahoo Finance…"):
        data = fetch_prices(tickers, period=period)

    if not data:
        st.error("Market data unavailable — Yahoo Finance may be rate-limited. Click Refresh to retry.")
        return

    # ── Tabs: Cards | Heatmap | Table | Compare | Movers ─────────────────────
    tab_cards, tab_heat, tab_table, tab_compare, tab_movers = st.tabs([
        "🃏 Cards", "🔥 Heatmap", "📋 Table", "📊 Compare", "🚀 Top Movers"
    ])

    with tab_cards:
        card_data = {
            ticker: {
                "price":      d["price"],
                "change_pct": d.get("chg_1d", 0),
                "volume":     d.get("volume"),
            }
            for ticker, d in data.items()
        }
        # Pass full close-price series for hover sparklines
        spark_data = {ticker: d.get("close", []) for ticker, d in data.items()}
        render_ticker_grid(card_data, cols=4, sparkline_data=spark_data)

    with tab_heat:
        _render_heatmap(data, sector)

    with tab_table:
        _render_price_table(data)

    with tab_compare:
        _render_compare_chart(data, period)

    with tab_movers:
        _render_top_movers(data)

    st.divider()

    # ── AI Commentary ─────────────────────────────────────────────────────────
    with st.expander("🤖 AI Market Commentary", expanded=False):
        if st.button("Generate Commentary", use_container_width=True, type="primary"):
            try:
                from shared.groq_client import chat, is_ai_available
                if not is_ai_available():
                    st.warning("Add GROQ_API_KEY to Streamlit secrets to enable AI commentary.")
                else:
                    movers = sorted(data.items(),
                                    key=lambda x: abs(x[1].get("chg_1d", 0)),
                                    reverse=True)[:5]
                    prompt = "\n".join(
                        f"{t}: ${d['price']:,.2f} ({d.get('chg_1d', 0):+.2f}% today, "
                        f"{d.get('chg_1mo', 0):+.2f}% 1mo)"
                        for t, d in movers
                    )
                    with st.spinner("Generating via Groq Llama 3…"):
                        commentary = chat(
                            prompt,
                            system="You are a Bloomberg market analyst. In 3 sentences: what moved today, why, and what to watch tomorrow. Be direct.",
                            model="smart",
                            max_tokens=200,
                        )
                    st.info(commentary)
            except Exception as e:
                st.error(f"AI commentary failed: {e}")


def _render_heatmap(data: dict, sector: str):
    """Sector heatmap treemap — TradingView-style."""
    try:
        import plotly.express as px
        import pandas as pd

        rows = []
        for tk, d in data.items():
            change = d.get("chg_1d", 0)
            rows.append({
                "ticker": tk,
                "size":   max(abs(d.get("price", 1)), 1),
                "change": change,
                "price":  d.get("price", 0),
                "volume": d.get("volume", 0),
            })
        df = pd.DataFrame(rows)
        if df.empty:
            st.info("No ticker data to render heatmap.")
            return

        fig = px.treemap(
            df,
            path=[px.Constant(sector), "ticker"],
            values="size",
            color="change",
            color_continuous_scale=[
                (0.0, "#7c1d1d"),
                (0.35, "#ff5773"),
                (0.5, "#1a2034"),
                (0.65, "#00d68f"),
                (1.0, "#0d5e2a"),
            ],
            color_continuous_midpoint=0,
            range_color=[-5, 5],
            custom_data=["price", "change", "volume"],
        )
        fig.update_traces(
            textinfo="label+text",
            text=df.apply(lambda r: f"${r['price']:,.2f}<br><b>{r['change']:+.2f}%</b>", axis=1),
            textfont=dict(size=14, color="white", family="IBM Plex Mono"),
            marker=dict(line=dict(color=COLORS["bg"], width=2)),
            hovertemplate="<b>%{label}</b><br>Price: $%{customdata[0]:,.2f}<br>1D: %{customdata[1]:+.2f}%<br>Volume: %{customdata[2]:,}<extra></extra>",
        )
        fig.update_layout(
            margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor=COLORS["bg"],
            plot_bgcolor=COLORS["bg"],
            font=dict(color=COLORS["text"], family="Inter"),
            height=560,
            coloraxis_colorbar=dict(
                title="1D %", thickness=12, len=0.7,
                tickfont=dict(color=COLORS["text"], family="IBM Plex Mono"),
            ),
        )
        st.plotly_chart(fig, use_container_width=True, theme=None)
        st.caption("Treemap: tile size ∝ price magnitude · color = 1-day % change.")
    except ImportError:
        st.warning("Install plotly: `pip install plotly>=5.20`")
    except Exception as e:
        st.error(f"Heatmap failed: {e}")


def _render_price_table(data: dict):
    """Bloomberg-style sortable price table."""
    import pandas as pd
    rows = []
    for ticker, d in data.items():
        rows.append({
            "Ticker": ticker,
            "Price":  d['price'],
            "1D %":   d.get('chg_1d', 0),
            "1Mo %":  d.get('chg_1mo', 0),
            "Open":   d['open'],
            "High":   d['high'],
            "Low":    d['low'],
            "Volume": d.get('volume', 0),
        })
    if not rows:
        st.info("No data to display.")
        return

    df = pd.DataFrame(rows).set_index("Ticker")

    # Use column_config for clean rendering
    st.dataframe(
        df,
        use_container_width=True,
        column_config={
            "Price":  st.column_config.NumberColumn(format="$%.2f"),
            "1D %":   st.column_config.NumberColumn(format="%+.2f%%"),
            "1Mo %":  st.column_config.NumberColumn(format="%+.2f%%"),
            "Open":   st.column_config.NumberColumn(format="$%.2f"),
            "High":   st.column_config.NumberColumn(format="$%.2f"),
            "Low":    st.column_config.NumberColumn(format="$%.2f"),
            "Volume": st.column_config.NumberColumn(format="%d"),
        },
        height=min(len(df) * 36 + 40, 600),
    )


def _render_compare_chart(data: dict, period: str):
    """Multi-ticker comparison chart — robust to different trading day counts."""
    chart_tickers = st.multiselect(
        "Select tickers to compare",
        list(data.keys()),
        default=[list(data.keys())[0]] if data else [],
    )
    if not chart_tickers:
        st.caption("Select 1+ tickers above to overlay the chart.")
        return

    try:
        import pandas as pd
        import plotly.graph_objects as go

        # Build per-ticker Series with their OWN dates (handles crypto-vs-stock cleanly)
        series = []
        for tk in chart_tickers:
            d = data.get(tk, {})
            closes = d.get("close") or []
            dates  = d.get("dates") or []
            if not closes or len(closes) != len(dates):
                continue
            base = closes[0] if closes[0] else 1
            normalised = [round(c / base * 100, 2) for c in closes]
            s = pd.Series(normalised,
                          index=pd.to_datetime(dates, errors="coerce"),
                          name=tk)
            series.append(s)

        if not series:
            st.warning("No valid ticker data to chart.")
            return

        chart_df = pd.concat(series, axis=1).sort_index().ffill()

        palette = ["#00d68f", "#4da6ff", "#ffaa00", "#ff8800",
                   "#ff5773", "#b16ee8", "#4dd1ce", "#ffa07a"]
        fig = go.Figure()
        for i, col in enumerate(chart_df.columns):
            fig.add_trace(go.Scatter(
                x=chart_df.index, y=chart_df[col],
                mode="lines", name=col,
                line=dict(color=palette[i % len(palette)], width=2),
            ))
        fig.add_hline(y=100, line_dash="dot", line_color="#5a6378",
                      annotation_text="Start (100)", annotation_position="right")
        fig.update_layout(
            height=450,
            margin=dict(l=8, r=12, t=20, b=8),
            paper_bgcolor=COLORS["bg"],
            plot_bgcolor=COLORS["bg"],
            font=dict(color=COLORS["text"], family="Inter"),
            xaxis=dict(gridcolor=COLORS["border"], showgrid=True, automargin=True),
            yaxis=dict(gridcolor=COLORS["border"], automargin=True,
                       title=dict(text="Index (100 = start)", standoff=8)),
            legend=dict(bgcolor=COLORS["surface"], bordercolor=COLORS["border"], borderwidth=1),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True, theme=None)
        st.caption(f"All tickers normalised to 100 at start of {period} window.")
    except Exception as e:
        st.error(f"Chart failed: {e}")


def _render_top_movers(data: dict):
    """Top winners + losers as interactive cards (logo · name · hover chart · analyze)."""
    movers = sorted(data.items(), key=lambda x: x[1].get("chg_1d", 0), reverse=True)
    gainers = movers[:5]
    losers  = movers[-5:][::-1]

    # Full close-price series for hover sparklines (same source as Cards tab)
    spark = {tk: d.get("close", []) for tk, d in data.items()}

    def _to_card_data(pairs):
        return {
            tk: {"price": d.get("price", 0),
                 "change_pct": d.get("chg_1d", 0),
                 "volume": d.get("volume")}
            for tk, d in pairs
        }

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### 🚀 Top Gainers (1D)")
        # cols=1 → one card per row; key_prefix avoids collision with Cards tab
        render_ticker_grid(_to_card_data(gainers), cols=1,
                           sparkline_data=spark, key_prefix="mv_gain")
    with c2:
        st.markdown("##### 📉 Top Decliners (1D)")
        render_ticker_grid(_to_card_data(losers), cols=1,
                           sparkline_data=spark, key_prefix="mv_lose")


main()
