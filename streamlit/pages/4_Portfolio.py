"""Portfolio tracker — save positions, track P&L, run risk reports."""

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
from datetime import datetime

st.set_page_config(page_title="Portfolio · INTL", page_icon="💼", layout="wide")

# ── Polish CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
.block-container { padding-top: 2rem; padding-bottom: 3rem; }
hr { margin: 1.5rem 0 !important; border-color: #1a1b2e !important; }
.stExpander { background: #0c0c18 !important; border: 1px solid #1a1b2e !important;
              border-radius: 8px !important; margin-bottom: 0.8rem !important; }
div[data-testid="stMetric"] { margin-bottom: 0.8rem; }
.stTabs [data-baseweb="tab-list"] { gap: 8px; }
.stTabs [data-baseweb="tab"] { padding: 0.5rem 1rem; }
.stDataFrame { margin: 0.8rem 0; }
</style>
""", unsafe_allow_html=True)


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
    except Exception as e:
        msg = str(e)
        if "portfolio_positions" in msg and "schema cache" in msg:
            # Surface a clear, actionable error — not silent failure
            st.session_state["__portfolio_table_missing"] = True
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
        msg = str(e)
        if "portfolio_positions" in msg and "schema cache" in msg:
            st.error("⚠ The `portfolio_positions` table does not exist in your Supabase project. "
                     "Run migration **`supabase/migrations/004_portfolio_cache_tables.sql`** in the "
                     "Supabase SQL editor first.")
        else:
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
    _render_positions_tab(tab_positions)
    _render_add_tab(tab_add)
    _render_risk_tab(tab_risk)


def _render_positions_tab(tab):
    """Positions tab — empty state shows clear onboarding, populated shows P&L table."""
    with tab:
        positions = load_positions()

        # Show schema-missing banner if applicable (set by load_positions on failure)
        if st.session_state.pop("__portfolio_table_missing", False):
            st.error(
                "⚠ The `portfolio_positions` table does not exist in your Supabase project. "
                "Run **`supabase/migrations/004_portfolio_cache_tables.sql`** in the Supabase SQL editor first.\n\n"
                "Direct link: https://supabase.com/dashboard/project/jptwbvigtgiffjqnctic/sql/new"
            )
            return

        if not positions:
            st.info("📭 **No positions saved yet.** Click the **➕ Add Position** tab above to add your first holding.")
            with st.expander("ℹ️ Quick start guide", expanded=True):
                st.markdown("""
                1. Click the **➕ Add Position** tab
                2. Enter a ticker (e.g. `NVDA`, `BTC-USD`, `SPY`)
                3. Enter shares and average cost
                4. Click **Save Position**
                5. Return here to see live P&L tracking
                """)
            return

        # Fetch current prices — batched
        tickers = tuple(p["ticker"] for p in positions)
        prices = _fetch_prices(tickers)

        # Build P&L table
        import pandas as pd
        rows = []
        total_cost  = 0.0
        total_value = 0.0
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
                "Avg Cost":   f"${avg_cost:,.2f}",
                "Curr Price": f"${curr_px:,.2f}",
                "Cost Basis": f"${cost_basis:,.0f}",
                "Mkt Value":  f"${mkt_value:,.0f}",
                "P&L":        f"${pnl:+,.0f}",
                "P&L %":      f"{pnl_pct:+.2f}%",
                "Notes":      p.get("notes", "") or "",
            })

        df = pd.DataFrame(rows).set_index("Ticker")

        def color_pnl(val):
            if isinstance(val, str) and "+" in val: return "color: #22d472"
            if isinstance(val, str) and "-" in val: return "color: #f75050"
            return ""

        # pandas >= 2.1: Styler.applymap removed → use Styler.map
        styled = df.style.map(color_pnl, subset=["P&L", "P&L %"]) \
                 if hasattr(df.style, "map") \
                 else df.style.applymap(color_pnl, subset=["P&L", "P&L %"])
        st.dataframe(styled, use_container_width=True)

        # Totals row
        total_pnl = total_value - total_cost
        total_pct = (total_pnl / total_cost * 100) if total_cost else 0
        c1, c2, c3 = st.columns(3)
        with c1: st.metric("Total Cost Basis",  f"${total_cost:,.0f}")
        with c2: st.metric("Total Market Value", f"${total_value:,.0f}")
        with c3:
            delta_c = "normal" if total_pnl >= 0 else "inverse"
            st.metric("Total P&L", f"${total_pnl:+,.0f}",
                      delta=f"{total_pct:+.2f}%", delta_color=delta_c)

        st.divider()

        # Delete position
        with st.expander("🗑️ Remove a position"):
            del_ticker = st.selectbox("Position to remove", ["—"] + [p["ticker"] for p in positions])
            if st.button("Delete selected position", type="secondary") and del_ticker != "—":
                if delete_position(del_ticker):
                    st.success(f"Removed {del_ticker}")
                    load_positions.clear()
                    st.rerun()


def _render_add_tab(tab):
    """Add Position tab — form to save a new position."""
    with tab:
        st.subheader("➕ Add / Update Position")
        st.caption("Enter ticker (Yahoo Finance symbol — `NVDA`, `BTC-USD`, `SPY`), shares, and average cost.")

        with st.form("add_position", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                new_ticker = st.text_input("Ticker", placeholder="NVDA").upper()
            with col2:
                new_shares = st.number_input("Shares", min_value=0.0001, value=10.0,
                                             step=0.001, format="%.4f")
            with col3:
                new_cost = st.number_input("Average Cost ($)", min_value=0.01,
                                           value=100.0, step=0.01)
            new_notes = st.text_input("Notes (optional)", placeholder="Long-term AI play")
            submitted = st.form_submit_button("💾 Save Position", use_container_width=True, type="primary")

            if submitted and new_ticker:
                if save_position(new_ticker, new_shares, new_cost, new_notes):
                    st.success(f"✓ Saved {new_ticker}: {new_shares} shares @ ${new_cost:.2f}")
                    load_positions.clear()
                    st.balloons()


def _render_risk_tab(tab):
    """Risk Report tab — portfolio VaR + correlation analysis."""
    with tab:
        positions = load_positions()
        if not positions:
            st.info("Add at least one position first (use the **➕ Add Position** tab).")
            return

        tickers = [p["ticker"] for p in positions]
        shares_map = {p["ticker"]: p.get("shares", 0) for p in positions}

        st.markdown(f"**Portfolio:** {', '.join(tickers)} ({len(tickers)} positions)")

        weight_mode = st.radio(
            "Portfolio weights",
            ["By position size (shares × cost)", "Equal weight"],
            horizontal=True,
        )

        if st.button("📊 Run Risk Report", use_container_width=True, type="primary"):
            weights = None
            if weight_mode == "By position size (shares × cost)":
                prices = _fetch_prices(tuple(tickers))
                values = [shares_map[t] * prices.get(t, 0) for t in tickers]
                total  = sum(values)
                weights = [v / total for v in values] if total > 0 else None

            with st.spinner("Computing portfolio risk (Yahoo Finance)…"):
                import asyncio
                from agents.math_agent import compute_portfolio_risk
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(compute_portfolio_risk(tickers, weights=weights))
                finally:
                    loop.close()

            if "error" in result:
                st.error(result["error"])
                return

            p = result.get("portfolio", {})
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("Portfolio VaR 95%",  f"{p.get('var_95',0):.2f}%",  delta="1-day historical")
            with c2: st.metric("Portfolio CVaR 95%", f"{p.get('cvar_95',0):.2f}%", delta="Expected Shortfall")
            with c3: st.metric("Portfolio Sharpe",   f"{p.get('sharpe',0):.3f}",
                               delta=f"Vol: {p.get('annualised_vol',0):.1f}% ann.")

            import pandas as pd
            ind = result.get("individual", [])
            if ind:
                with st.expander("📋 Individual Holdings Risk", expanded=True):
                    df = pd.DataFrame([r for r in ind if "error" not in r])
                    if "weight" in df.columns:
                        df["weight"] = df["weight"].apply(lambda x: f"{x:.1%}")
                    st.dataframe(df.set_index("ticker"), use_container_width=True)

            corr = result.get("correlation")
            if corr and len(corr) > 1:
                with st.expander("🔥 Correlation Matrix", expanded=True):
                    st.dataframe(
                        pd.DataFrame(corr).round(3).style.background_gradient(
                            cmap="RdYlGn", vmin=-1, vmax=1),
                        use_container_width=True,
                    )
                    st.caption("Values near 1 = highly correlated (less diversification). "
                               "Values near -1 = inverse correlation.")


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_prices(tickers: tuple) -> dict:
    """Batched yfinance fetch — single API call for all tickers."""
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
            # Fallback: per-ticker
            for ticker in tickers:
                try:
                    h = yf.Ticker(ticker).history(period="2d", interval="1d", auto_adjust=True)
                    if not h.empty:
                        prices[ticker] = round(float(h["Close"].iloc[-1]), 2)
                except Exception:
                    pass
        return prices
    except Exception:
        return {}


main()
