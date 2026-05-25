"""Portfolio tracker — save positions, track P&L, run risk reports."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import os
from datetime import datetime

st.set_page_config(page_title="Portfolio · INTL", page_icon="💼", layout="wide")


def get_client():
    url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        return None
    from supabase import create_client
    return create_client(url, key)


@st.cache_data(ttl=60)
def load_positions():
    """Load saved portfolio positions from Supabase."""
    client = get_client()
    if not client:
        return []
    try:
        return (client.table("portfolio_positions")
                .select("*")
                .order("created_at", desc=True)
                .execute()).data or []
    except Exception:
        return []


def save_position(ticker, shares, avg_cost, notes=""):
    """Save a new portfolio position."""
    client = get_client()
    if not client:
        st.error("Connect Supabase to save positions.")
        return False
    try:
        client.table("portfolio_positions").upsert({
            "ticker":   ticker.upper(),
            "shares":   float(shares),
            "avg_cost": float(avg_cost),
            "notes":    notes,
            "updated_at": datetime.utcnow().isoformat(),
        }, on_conflict="ticker").execute()
        return True
    except Exception as e:
        st.error(f"Save error: {e}")
        return False


def delete_position(ticker):
    client = get_client()
    if not client:
        return False
    try:
        client.table("portfolio_positions").delete().eq("ticker", ticker).execute()
        return True
    except Exception:
        return False


def main():
    st.title("💼 Portfolio Tracker")
    st.caption("Save positions · Track P&L · Run risk reports · Powered by Supabase + Yahoo Finance")

    if not get_client():
        st.error("⚠ Supabase not connected. Add SUPABASE_URL and SUPABASE_ANON_KEY to Streamlit secrets.")
        return

    tab_positions, tab_add, tab_risk = st.tabs(["📋 My Positions", "➕ Add Position", "🎯 Risk Report"])

    # ── Positions tab ──────────────────────────────────────────────────────
    with tab_positions:
        positions = load_positions()
        if not positions:
            st.info("No positions saved yet. Add positions in the '➕ Add Position' tab.")
            return

        # Fetch current prices
        tickers = tuple(p["ticker"] for p in positions)
        with st.spinner("Fetching live prices…"):
            try:
                import yfinance as yf
                prices = {}
                for ticker in tickers:
                    try:
                        t = yf.Ticker(ticker)
                        h = t.history(period="2d", interval="1d", auto_adjust=True)
                        if not h.empty:
                            prices[ticker] = round(h["Close"].iloc[-1], 2)
                    except Exception:
                        pass
            except Exception:
                prices = {}

        # Build P&L table
        import pandas as pd
        rows = []
        total_cost  = 0
        total_value = 0
        for p in positions:
            ticker    = p["ticker"]
            shares    = p.get("shares", 0)
            avg_cost  = p.get("avg_cost", 0)
            curr_px   = prices.get(ticker, avg_cost)
            cost_basis = shares * avg_cost
            mkt_value  = shares * curr_px
            pnl        = mkt_value - cost_basis
            pnl_pct    = (pnl / cost_basis * 100) if cost_basis else 0
            total_cost  += cost_basis
            total_value += mkt_value
            rows.append({
                "Ticker":    ticker,
                "Shares":    shares,
                "Avg Cost":  f"${avg_cost:,.2f}",
                "Curr Price":f"${curr_px:,.2f}",
                "Cost Basis":f"${cost_basis:,.0f}",
                "Mkt Value": f"${mkt_value:,.0f}",
                "P&L":       f"${pnl:+,.0f}",
                "P&L %":     f"{pnl_pct:+.2f}%",
                "Notes":     p.get("notes", ""),
            })

        df = pd.DataFrame(rows).set_index("Ticker")
        def color_pnl(val):
            if isinstance(val, str) and "+" in val: return "color: #22d472"
            if isinstance(val, str) and "-" in val: return "color: #f75050"
            return ""
        st.dataframe(df.style.applymap(color_pnl, subset=["P&L", "P&L %"]), use_container_width=True)

        total_pnl = total_value - total_cost
        total_pct = (total_pnl / total_cost * 100) if total_cost else 0
        c1, c2, c3 = st.columns(3)
        with c1: st.metric("Total Cost Basis", f"${total_cost:,.0f}")
        with c2: st.metric("Total Market Value", f"${total_value:,.0f}")
        with c3:
            delta_c = "normal" if total_pnl >= 0 else "inverse"
            st.metric("Total P&L", f"${total_pnl:+,.0f}", delta=f"{total_pct:+.2f}%", delta_color=delta_c)

        # Delete position
        del_ticker = st.selectbox("Remove position", ["—"] + [p["ticker"] for p in positions])
        if st.button("Delete selected position", type="secondary") and del_ticker != "—":
            if delete_position(del_ticker):
                st.success(f"Removed {del_ticker}")
                load_positions.clear()
                st.rerun()

    # ── Add position tab ───────────────────────────────────────────────────
    with tab_add:
        st.subheader("Add / Update Position")
        with st.form("add_position"):
            col1, col2, col3 = st.columns(3)
            with col1: new_ticker = st.text_input("Ticker", placeholder="NVDA").upper()
            with col2: new_shares = st.number_input("Shares", min_value=0.0001, value=10.0, step=0.001, format="%.4f")
            with col3: new_cost   = st.number_input("Average Cost ($)", min_value=0.01, value=100.0, step=0.01)
            new_notes = st.text_input("Notes (optional)", placeholder="Long-term AI play")
            submitted = st.form_submit_button("Save Position", use_container_width=True)
            if submitted and new_ticker:
                if save_position(new_ticker, new_shares, new_cost, new_notes):
                    st.success(f"Saved {new_ticker}: {new_shares} shares @ ${new_cost:.2f}")
                    load_positions.clear()

    # ── Risk report tab ────────────────────────────────────────────────────
    with tab_risk:
        positions = load_positions()
        if not positions:
            st.info("Add positions first.")
            return

        tickers = [p["ticker"] for p in positions]
        shares_map = {p["ticker"]: p.get("shares", 0) for p in positions}

        # Equal weight vs actual position weight
        weight_mode = st.radio("Portfolio weights", ["By position size (shares × cost)", "Equal weight"])

        if st.button("Run Risk Report", use_container_width=True):
            weights = None
            if weight_mode == "By position size (shares × cost)":
                import yfinance as yf
                prices = {}
                for t in tickers:
                    try:
                        obj = yf.Ticker(t)
                        h = obj.history(period="2d", auto_adjust=True)
                        prices[t] = h["Close"].iloc[-1] if not h.empty else 0
                    except Exception:
                        prices[t] = 0
                values = [shares_map[t] * prices.get(t, 0) for t in tickers]
                total  = sum(values)
                weights = [v / total for v in values] if total > 0 else None

            with st.spinner("Computing portfolio risk (Yahoo Finance)…"):
                import asyncio
                from agents.math_agent import compute_portfolio_risk
                loop = asyncio.new_event_loop()
                result = loop.run_until_complete(compute_portfolio_risk(tickers, weights=weights))
                loop.close()

            if "error" in result:
                st.error(result["error"])
                return

            p = result.get("portfolio", {})
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("Portfolio VaR 95%", f"{p.get('var_95',0):.2f}%", delta="1-day historical")
            with c2: st.metric("Portfolio CVaR 95%", f"{p.get('cvar_95',0):.2f}%", delta="Expected Shortfall")
            with c3: st.metric("Portfolio Sharpe",  f"{p.get('sharpe',0):.3f}", delta=f"Vol: {p.get('annualised_vol',0):.1f}% ann.")

            import pandas as pd
            ind = result.get("individual", [])
            if ind:
                df = pd.DataFrame([r for r in ind if "error" not in r])
                df["weight"] = df["weight"].apply(lambda x: f"{x:.1%}")
                st.dataframe(df.set_index("ticker"), use_container_width=True)

            corr = result.get("correlation")
            if corr and len(corr) > 1:
                st.subheader("Correlation Matrix")
                st.dataframe(
                    pd.DataFrame(corr).round(3).style.background_gradient(cmap="RdYlGn", vmin=-1, vmax=1),
                    use_container_width=True,
                )


main()
