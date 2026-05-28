"""
Portfolio tracker — positions, live P&L, risk report.

Inspired by Aladdin Wealth: whole-portfolio risk view, factor breakdown.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for p in (ROOT, ROOT / "projects" / "daily_digest"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import streamlit as st
import os
from datetime import datetime

st.set_page_config(page_title="Portfolio · INTL", page_icon="💼", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _theme import apply_theme, COLORS
from _data  import supabase_client
apply_theme()
from _terminal_chrome import render_chrome
render_chrome("Portfolio")


@st.cache_data(ttl=60)
def load_positions():
    """Load saved portfolio positions from Supabase."""
    client = supabase_client()
    if not client:
        return [], "no_client"
    try:
        rows = (client.table("portfolio_positions")
                .select("*")
                .order("created_at", desc=True)
                .execute()).data or []
        return rows, "ok"
    except Exception as e:
        msg = str(e)
        if "portfolio_positions" in msg and "schema cache" in msg:
            return [], "missing"
        return [], "error"


def save_position(ticker, shares, avg_cost, notes=""):
    client = supabase_client()
    if not client:
        st.error("Connect Supabase to save positions.")
        return False
    try:
        client.table("portfolio_positions").upsert({
            "ticker":     ticker.upper(),
            "shares":     float(shares),
            "avg_cost":   float(avg_cost),
            "notes":      notes,
            "updated_at": datetime.utcnow().isoformat(),
        }, on_conflict="ticker").execute()
        return True
    except Exception as e:
        msg = str(e)
        if "portfolio_positions" in msg and "schema cache" in msg:
            st.error(
                "⚠ The `portfolio_positions` table doesn't exist. Run "
                "[migration 004](https://github.com/git0ST/automation/blob/main/supabase/migrations/004_portfolio_cache_tables.sql) "
                "in [Supabase SQL Editor](https://supabase.com/dashboard/project/jptwbvigtgiffjqnctic/sql/new)."
            )
        else:
            st.error(f"Save error: {e}")
        return False


def delete_position(ticker):
    client = supabase_client()
    if not client:
        return False
    try:
        client.table("portfolio_positions").delete().eq("ticker", ticker).execute()
        return True
    except Exception:
        return False


@st.cache_data(ttl=300, show_spinner=False)
def fetch_prices(tickers: tuple) -> dict:
    """Batched yfinance fetch."""
    if not tickers:
        return {}
    try:
        import yfinance as yf
        prices = {}
        try:
            batch = yf.download(
                list(tickers), period="2d", interval="1d",
                auto_adjust=True, progress=False, group_by="ticker", threads=True,
            )
            for ticker in tickers:
                try:
                    if len(tickers) > 1 and ticker in batch.columns.get_level_values(0):
                        sub = batch[ticker].dropna()
                    else:
                        sub = batch.dropna()
                    if not sub.empty:
                        prices[ticker] = round(float(sub["Close"].iloc[-1]), 2)
                except Exception:
                    pass
        except Exception:
            for ticker in tickers:
                try:
                    h = yf.Ticker(ticker).history(period="2d", auto_adjust=True)
                    if not h.empty:
                        prices[ticker] = round(float(h["Close"].iloc[-1]), 2)
                except Exception:
                    pass
        return prices
    except Exception:
        return {}


def main():
    st.title("💼 Portfolio Tracker")
    st.caption("Track positions · Live P&L · Aladdin-style risk decomposition")

    if not supabase_client():
        st.error("⚠ Supabase not connected. Add `SUPABASE_URL` and `SUPABASE_ANON_KEY` to Streamlit secrets.")
        return

    tabs = st.tabs(["📋 Positions", "➕ Add Position", "🎯 Risk Report", "📊 Factor View"])
    _render_positions_tab(tabs[0])
    _render_add_tab(tabs[1])
    _render_risk_tab(tabs[2])
    _render_factor_tab(tabs[3])


def _render_positions_tab(tab):
    with tab:
        positions, status = load_positions()

        if status == "missing":
            st.error(
                "⚠ The `portfolio_positions` table doesn't exist. Run "
                "[migration 004](https://github.com/git0ST/automation/blob/main/supabase/migrations/004_portfolio_cache_tables.sql) "
                "in [Supabase SQL Editor](https://supabase.com/dashboard/project/jptwbvigtgiffjqnctic/sql/new)."
            )
            return
        if status == "error":
            st.error("Could not load positions. Check Supabase credentials.")
            return

        if not positions:
            st.info(
                "📭 **No positions yet.** Click the **➕ Add Position** tab to start tracking your holdings.",
                icon="📭",
            )
            with st.expander("ℹ️ Quick start", expanded=True):
                st.markdown("""
                1. Click **➕ Add Position** tab
                2. Enter ticker (e.g. `NVDA`, `BTC-USD`, `SPY`)
                3. Enter shares + average cost
                4. Click **💾 Save Position**
                5. Return here for live P&L tracking
                """)
            return

        # Fetch live prices
        tickers = tuple(p["ticker"] for p in positions)
        prices = fetch_prices(tickers)

        # P&L summary at the top
        total_cost, total_value = 0.0, 0.0
        rows = []
        for p in positions:
            ticker     = p["ticker"]
            shares     = float(p.get("shares") or 0)
            avg_cost   = float(p.get("avg_cost") or 0)
            curr_px    = prices.get(ticker, avg_cost)
            cost_basis = shares * avg_cost
            mkt_value  = shares * curr_px
            pnl        = mkt_value - cost_basis
            pnl_pct    = (pnl / cost_basis * 100) if cost_basis else 0
            total_cost  += cost_basis
            total_value += mkt_value
            rows.append({
                "Ticker":     ticker,
                "Shares":     shares,
                "Avg Cost":   avg_cost,
                "Curr Price": curr_px,
                "Cost Basis": cost_basis,
                "Mkt Value":  mkt_value,
                "P&L":        pnl,
                "P&L %":      pnl_pct,
                "Notes":      p.get("notes") or "",
            })

        total_pnl = total_value - total_cost
        total_pct = (total_pnl / total_cost * 100) if total_cost else 0

        # KPI summary
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Positions",          len(positions))
        c2.metric("Total Cost Basis",   f"${total_cost:,.0f}")
        c3.metric("Total Mkt Value",    f"${total_value:,.0f}")
        c4.metric("Total P&L",          f"${total_pnl:+,.0f}",
                  delta=f"{total_pct:+.2f}%",
                  delta_color="normal" if total_pnl >= 0 else "inverse")

        st.divider()

        # Table with column_config for clean formatting
        import pandas as pd
        df = pd.DataFrame(rows).set_index("Ticker")
        st.dataframe(
            df,
            use_container_width=True,
            column_config={
                "Shares":     st.column_config.NumberColumn(format="%.4f"),
                "Avg Cost":   st.column_config.NumberColumn(format="$%.2f"),
                "Curr Price": st.column_config.NumberColumn(format="$%.2f"),
                "Cost Basis": st.column_config.NumberColumn(format="$%.0f"),
                "Mkt Value":  st.column_config.NumberColumn(format="$%.0f"),
                "P&L":        st.column_config.NumberColumn(format="$%+.0f"),
                "P&L %":      st.column_config.NumberColumn(format="%+.2f%%"),
            },
        )

        # Allocation chart
        if rows:
            with st.expander("🥧 Allocation", expanded=True):
                try:
                    import plotly.express as px
                    alloc_df = pd.DataFrame(rows)
                    alloc_df["allocation_pct"] = alloc_df["Mkt Value"] / alloc_df["Mkt Value"].sum() * 100
                    fig = px.pie(
                        alloc_df, values="Mkt Value", names="Ticker",
                        hole=0.55,
                        color_discrete_sequence=["#4c8bf5", "#00d68f", "#ffaa00", "#ff5773",
                                                  "#b16ee8", "#4dd1ce", "#ff8800", "#5a6378"],
                    )
                    fig.update_traces(textinfo="label+percent",
                                      textfont=dict(size=12, family="Inter", color="white"),
                                      marker=dict(line=dict(color=COLORS["bg"], width=2)))
                    fig.update_layout(
                        paper_bgcolor=COLORS["bg"], plot_bgcolor=COLORS["bg"],
                        font=dict(color=COLORS["text"]), height=400,
                        margin=dict(l=10, r=10, t=10, b=10),
                        showlegend=True,
                    )
                    st.plotly_chart(fig, use_container_width=True, theme=None)
                except Exception as e:
                    st.caption(f"Allocation chart unavailable: {e}")

        # Delete position
        with st.expander("🗑️ Remove a position"):
            del_ticker = st.selectbox("Position to remove",
                                      ["—"] + [p["ticker"] for p in positions])
            if st.button("Delete", type="secondary") and del_ticker != "—":
                if delete_position(del_ticker):
                    load_positions.clear()
                    st.success(f"Removed {del_ticker}")
                    st.rerun()


def _render_add_tab(tab):
    with tab:
        st.markdown("#### ➕ Add or update position")
        st.caption("Ticker uses Yahoo Finance symbols — `NVDA`, `BTC-USD`, `SPY`, etc.")

        with st.form("add_position", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                new_ticker = st.text_input("Ticker", placeholder="NVDA").upper()
            with col2:
                new_shares = st.number_input("Shares", min_value=0.0001, value=10.0,
                                             step=0.001, format="%.4f")
            with col3:
                new_cost = st.number_input("Avg Cost ($)", min_value=0.01,
                                           value=100.0, step=0.01)
            new_notes = st.text_input("Notes (optional)", placeholder="e.g. Long-term AI play")
            submitted = st.form_submit_button("💾 Save Position", use_container_width=True,
                                              type="primary")

            if submitted and new_ticker:
                if save_position(new_ticker, new_shares, new_cost, new_notes):
                    load_positions.clear()
                    st.success(f"✓ Saved {new_ticker}: {new_shares} shares @ ${new_cost:.2f}")
                    st.balloons()
                    import time
                    time.sleep(0.6)
                    st.rerun()


def _render_risk_tab(tab):
    with tab:
        positions, status = load_positions()
        if status == "missing" or not positions:
            st.info("Add at least one position first (➕ Add Position tab).")
            return

        tickers = [p["ticker"] for p in positions]
        shares_map = {p["ticker"]: p.get("shares", 0) for p in positions}

        st.markdown(f"**Portfolio:** `{' '.join(tickers)}` ({len(tickers)} positions)")

        weight_mode = st.radio(
            "Weighting",
            ["By position size (live)", "Equal weight"],
            horizontal=True,
        )

        if st.button("📊 Run Risk Report", use_container_width=True, type="primary"):
            weights = None
            if weight_mode == "By position size (live)":
                prices = fetch_prices(tuple(tickers))
                values = [shares_map[t] * prices.get(t, 0) for t in tickers]
                total  = sum(values)
                weights = [v / total for v in values] if total > 0 else None

            with st.spinner("Computing portfolio risk via yfinance + math agent…"):
                try:
                    import asyncio
                    from agents.math_agent import compute_portfolio_risk
                    loop = asyncio.new_event_loop()
                    try:
                        result = loop.run_until_complete(
                            compute_portfolio_risk(tickers, weights=weights)
                        )
                    finally:
                        loop.close()
                except Exception as e:
                    st.error(f"Risk computation failed: {e}")
                    return

            if "error" in result:
                st.error(result["error"])
                return

            p = result.get("portfolio", {})
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("VaR 95%",  f"{p.get('var_95', 0):.2f}%",  delta="1-day historical")
            c2.metric("CVaR 95%", f"{p.get('cvar_95', 0):.2f}%", delta="Expected Shortfall")
            c3.metric("Sharpe",   f"{p.get('sharpe', 0):.3f}")
            c4.metric("Vol (Ann.)", f"{p.get('annualised_vol', 0):.1f}%")

            ind = result.get("individual", [])
            if ind:
                with st.expander("📋 Individual Holdings Risk", expanded=True):
                    import pandas as pd
                    df = pd.DataFrame([r for r in ind if "error" not in r])
                    if "weight" in df.columns:
                        df["weight"] = df["weight"].apply(lambda x: f"{x:.1%}")
                    st.dataframe(df.set_index("ticker"), use_container_width=True)

            corr = result.get("correlation")
            if corr and len(corr) > 1:
                with st.expander("🔥 Correlation Matrix", expanded=True):
                    try:
                        import plotly.graph_objects as go
                        import pandas as pd
                        corr_df = pd.DataFrame(corr).round(3)
                        fig = go.Figure(data=go.Heatmap(
                            z=corr_df.values, x=list(corr_df.columns), y=list(corr_df.index),
                            colorscale=[[0.0, "#ff5773"], [0.5, "#1a2034"], [1.0, "#00d68f"]],
                            zmin=-1, zmax=1,
                            text=corr_df.round(2).values,
                            texttemplate="%{text:.2f}",
                            textfont=dict(size=12, color="white", family="IBM Plex Mono"),
                        ))
                        fig.update_layout(
                            height=max(300, 45 * len(corr_df)),
                            margin=dict(l=8, r=10, t=10, b=8),
                            paper_bgcolor=COLORS["bg"], plot_bgcolor=COLORS["bg"],
                            font=dict(color=COLORS["text"]),
                            xaxis=dict(automargin=True),
                            yaxis=dict(automargin=True),
                        )
                        st.plotly_chart(fig, use_container_width=True, theme=None)
                    except Exception as e:
                        st.caption(f"Heatmap unavailable: {e}")


def _render_factor_tab(tab):
    """Aladdin-style factor exposure breakdown."""
    with tab:
        positions, status = load_positions()
        if not positions:
            st.info("Add positions to see factor breakdown.")
            return

        st.markdown("#### Asset-class exposure")
        st.caption(
            "Classifies holdings into broad asset classes — equity, bond, commodity, crypto, FX. "
            "Inspired by Aladdin Wealth's whole-portfolio risk view."
        )

        # Classify each ticker
        def classify(t):
            t = t.upper()
            if t in ("TLT", "IEF", "AGG", "BND", "LQD", "HYG", "SHY", "TIP"):
                return "Bonds"
            if t in ("GLD", "SLV", "GDX", "DBC", "USO", "UNG"):
                return "Commodities"
            if "BTC" in t or "ETH" in t or "SOL" in t or "-USD" in t:
                return "Crypto"
            if t in ("UUP", "FXY", "FXE"):
                return "FX"
            if t in ("SPY", "QQQ", "DIA", "IWM", "VTI", "VXUS", "VOO", "VEA", "VWO"):
                return "Equity ETF"
            return "Equity (single name)"

        # Fetch prices for live value
        tickers = tuple(p["ticker"] for p in positions)
        prices = fetch_prices(tickers)

        from collections import defaultdict
        exposure = defaultdict(float)
        for p in positions:
            t = p["ticker"]
            value = float(p.get("shares") or 0) * prices.get(t, float(p.get("avg_cost") or 0))
            exposure[classify(t)] += value

        total = sum(exposure.values())
        if total <= 0:
            st.warning("Cannot compute exposure — no live prices available.")
            return

        # Render as horizontal bar chart + table
        import pandas as pd
        rows = [
            {"Asset Class": k, "Market Value": v, "Allocation %": v / total * 100}
            for k, v in exposure.items()
        ]
        df = pd.DataFrame(rows).sort_values("Market Value", ascending=False)

        try:
            import plotly.express as px
            fig = px.bar(
                df, x="Allocation %", y="Asset Class", orientation="h",
                color="Asset Class",
                color_discrete_sequence=["#4c8bf5", "#00d68f", "#ffaa00", "#ff5773",
                                          "#b16ee8", "#4dd1ce"],
                text=df["Allocation %"].apply(lambda x: f"{x:.1f}%"),
            )
            fig.update_traces(textposition="outside",
                              textfont=dict(family="IBM Plex Mono", color="white"))
            fig.update_layout(
                height=300 + 30 * len(df),
                paper_bgcolor=COLORS["bg"], plot_bgcolor=COLORS["bg"],
                font=dict(color=COLORS["text"]),
                margin=dict(l=8, r=16, t=20, b=8),
                showlegend=False,
                xaxis=dict(gridcolor=COLORS["border"], automargin=True,
                           title=dict(text="% of portfolio", standoff=8)),
                yaxis=dict(title="", automargin=True),
            )
            st.plotly_chart(fig, use_container_width=True, theme=None)
        except Exception:
            pass

        st.dataframe(
            df.set_index("Asset Class"),
            use_container_width=True,
            column_config={
                "Market Value": st.column_config.NumberColumn(format="$%.0f"),
                "Allocation %": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )

        # Concentration warning
        max_alloc = df["Allocation %"].max()
        if max_alloc > 60:
            st.warning(
                f"⚠ **Concentration risk:** {df.iloc[0]['Asset Class']} = "
                f"{max_alloc:.1f}% of portfolio. Aladdin typical guidance: rebalance "
                "any single asset class above 40-50% unless intentional."
            )


main()
