"""Global Markets — region-organized terminal view of world indices + forex.

Bloomberg WEI / Bloomberg WM-style: dense multi-region grid showing
live values + intraday + week + month + year change in one screen.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for p in (ROOT, ROOT / "projects" / "daily_digest"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import streamlit as st

st.set_page_config(page_title="Global Markets · INTL", page_icon="🌍", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _theme import apply_theme, COLORS
from _kpi_help    import DXY, EURUSD, USDJPY, MARKET_REGIME
from shared.global_markets import REGIONS, FOREX, lookup
apply_theme()
from _terminal_chrome import render_chrome
render_chrome("Global_Markets")


@st.cache_data(ttl=300, show_spinner=False)
def fetch_market_grid(symbols: tuple) -> dict:
    """Fetch 1D/1W/1M/3M/1Y returns for a batch of tickers."""
    if not symbols:
        return {}
    try:
        import yfinance as yf
        import numpy as np
        result = {}
        for sym in symbols:
            try:
                hist = yf.Ticker(sym).history(period="1y", auto_adjust=True)
                if hist.empty:
                    continue
                closes = hist["Close"].values
                last = float(closes[-1])
                result[sym] = {
                    "last":    round(last, 4),
                    "chg_1d":  round((closes[-1]  / closes[-2]   - 1) * 100, 2) if len(closes) >= 2  else 0,
                    "chg_1w":  round((closes[-1]  / closes[-5]   - 1) * 100, 2) if len(closes) >= 5  else 0,
                    "chg_1m":  round((closes[-1]  / closes[-21]  - 1) * 100, 2) if len(closes) >= 21 else 0,
                    "chg_3m":  round((closes[-1]  / closes[-63]  - 1) * 100, 2) if len(closes) >= 63 else 0,
                    "chg_ytd": round((closes[-1]  / closes[0]    - 1) * 100, 2),
                    "volume":  int(hist["Volume"].iloc[-1]) if "Volume" in hist else 0,
                }
            except Exception:
                continue
        return result
    except ImportError:
        return {}


def main():
    col_t, col_r = st.columns([6, 1])
    with col_t:
        st.title("🌍 Global Markets")
        st.caption("Real-time world indices + forex · 1D / 1W / 1M / 3M / YTD returns")
    with col_r:
        st.write("")
        if st.button("🔄 Refresh", use_container_width=True):
            fetch_market_grid.clear()
            st.rerun()

    # ── Pull data ───────────────────────────────────────────────────────────
    all_index_syms = []
    for region in REGIONS.values():
        all_index_syms.extend(region.keys())
    all_forex_syms = []
    for cat in FOREX.values():
        all_forex_syms.extend(cat.keys())

    with st.spinner("Loading world markets — indices + forex…"):
        data = fetch_market_grid(tuple(all_index_syms + all_forex_syms))

    if not data:
        st.error("Could not load market data. Yahoo Finance may be rate-limited.")
        return

    # ── Quick summary KPIs ──────────────────────────────────────────────────
    _render_summary(data)

    st.divider()

    # ── Tabs: by region / forex / heatmap ───────────────────────────────────
    tab_eq, tab_fx, tab_heat = st.tabs([
        "📊 Equity Indices", "💱 Forex", "🔥 Heatmap"
    ])

    with tab_eq:
        for region_name, region_data in REGIONS.items():
            _render_region(region_name, region_data, data)

    with tab_fx:
        for cat_name, cat_data in FOREX.items():
            _render_forex_category(cat_name, cat_data, data)

    with tab_heat:
        _render_world_heatmap(data)


def _render_summary(data: dict):
    """4 KPIs across the top — DXY, S&P 500, gold proxy, world summary."""
    c1, c2, c3, c4 = st.columns(4)
    dxy = data.get("DX-Y.NYB", {})
    spx = data.get("^GSPC",    {})
    eur = data.get("EURUSD=X", {})
    jpy = data.get("USDJPY=X", {})

    c1.metric("DXY", f"{dxy.get('last', 0):.3f}",
              delta=f"{dxy.get('chg_1d', 0):+.2f}% today",
              delta_color="inverse" if dxy.get('chg_1d', 0) > 0 else "normal",
              help=DXY)
    c2.metric("S&P 500", f"{spx.get('last', 0):,.2f}",
              delta=f"{spx.get('chg_1d', 0):+.2f}% today",
              help=MARKET_REGIME)
    c3.metric("EUR / USD", f"{eur.get('last', 0):.4f}",
              delta=f"{eur.get('chg_1d', 0):+.2f}% today",
              help=EURUSD)
    c4.metric("USD / JPY", f"{jpy.get('last', 0):.2f}",
              delta=f"{jpy.get('chg_1d', 0):+.2f}% today",
              help=USDJPY)


def _render_region(name: str, region: dict, data: dict):
    """Compact table per region."""
    rows = []
    for sym, meta in region.items():
        d = data.get(sym)
        if not d:
            continue
        rows.append({
            "":         meta["flag"],
            "Symbol":   sym,
            "Name":     meta["name"],
            "Country":  meta["country"],
            "Last":     d["last"],
            "1D %":     d["chg_1d"],
            "1W %":     d["chg_1w"],
            "1M %":     d["chg_1m"],
            "3M %":     d["chg_3m"],
            "YTD %":    d["chg_ytd"],
        })
    if not rows:
        return

    st.markdown(f"##### {name} ({len(rows)} markets)")
    import pandas as pd
    df = pd.DataFrame(rows).set_index("Symbol")
    st.dataframe(
        df, use_container_width=True,
        column_config={
            "":      st.column_config.TextColumn(width="small"),
            "Last":  st.column_config.NumberColumn(format="%.3f"),
            "1D %":  st.column_config.NumberColumn(format="%+.2f%%"),
            "1W %":  st.column_config.NumberColumn(format="%+.2f%%"),
            "1M %":  st.column_config.NumberColumn(format="%+.2f%%"),
            "3M %":  st.column_config.NumberColumn(format="%+.2f%%"),
            "YTD %": st.column_config.NumberColumn(format="%+.2f%%"),
        },
        height=min(len(rows) * 36 + 40, 400),
    )


def _render_forex_category(name: str, cat: dict, data: dict):
    """Forex tables organized by major/cross/emerging."""
    label = {"majors": "Major Pairs", "crosses": "Cross Pairs",
             "emerging": "Emerging Market Pairs"}.get(name, name.title())
    rows = []
    for sym, meta in cat.items():
        d = data.get(sym)
        if not d:
            continue
        rows.append({
            "":        meta["flag"],
            "Symbol":  sym,
            "Pair":    meta["name"],
            "Last":    d["last"],
            "1D %":    d["chg_1d"],
            "1W %":    d["chg_1w"],
            "1M %":    d["chg_1m"],
            "YTD %":   d["chg_ytd"],
        })
    if not rows:
        return

    st.markdown(f"##### {label} ({len(rows)})")
    import pandas as pd
    df = pd.DataFrame(rows).set_index("Symbol")
    st.dataframe(
        df, use_container_width=True,
        column_config={
            "":      st.column_config.TextColumn(width="small"),
            "Last":  st.column_config.NumberColumn(format="%.5f"),
            "1D %":  st.column_config.NumberColumn(format="%+.2f%%"),
            "1W %":  st.column_config.NumberColumn(format="%+.2f%%"),
            "1M %":  st.column_config.NumberColumn(format="%+.2f%%"),
            "YTD %": st.column_config.NumberColumn(format="%+.2f%%"),
        },
        height=min(len(rows) * 36 + 40, 400),
    )


def _render_world_heatmap(data: dict):
    """Plotly treemap of all indices colored by 1D return."""
    try:
        import plotly.express as px
        import pandas as pd
        rows = []
        for region_name, region in REGIONS.items():
            for sym, meta in region.items():
                d = data.get(sym)
                if not d:
                    continue
                rows.append({
                    "region": region_name,
                    "name":   meta["name"],
                    "country": meta["country"],
                    "flag":   meta["flag"],
                    "size":   max(abs(d["last"]), 1),
                    "chg_1d": d["chg_1d"],
                })
        if not rows:
            return
        df = pd.DataFrame(rows)
        fig = px.treemap(
            df, path=["region", "name"],
            values="size",
            color="chg_1d",
            color_continuous_scale=[
                (0.0, "#7c1d1d"), (0.35, "#ff5773"),
                (0.5, "#1a2034"),
                (0.65, "#00d68f"), (1.0, "#0d5e2a"),
            ],
            color_continuous_midpoint=0,
            range_color=[-3, 3],
            custom_data=["country", "chg_1d", "flag"],
        )
        fig.update_traces(
            textinfo="label+text",
            text=df.apply(lambda r: f"{r['flag']}<br><b>{r['chg_1d']:+.2f}%</b>", axis=1),
            textfont=dict(size=12, color="white", family="IBM Plex Mono"),
            marker=dict(line=dict(color=COLORS["bg"], width=2)),
            hovertemplate="<b>%{label}</b><br>%{customdata[0]}<br>"
                          "1D: %{customdata[1]:+.2f}%<extra></extra>",
        )
        fig.update_layout(
            margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor=COLORS["bg"], plot_bgcolor=COLORS["bg"],
            font=dict(color=COLORS["text"], family="Inter"),
            height=520,
            coloraxis_colorbar=dict(title="1D %", thickness=12, len=0.7,
                                     tickfont=dict(color=COLORS["text"])),
        )
        st.plotly_chart(fig, use_container_width=True, theme=None)
        st.caption("**Use:** Strong region-wide moves (multiple flags same color) = "
                   "systemic event, check news. Single outlier = country-specific catalyst.")
    except Exception as e:
        st.caption(f"Heatmap unavailable: {e}")


main()
