"""Risk & VaR analysis page — institutional-grade risk metrics."""

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

st.set_page_config(page_title="Risk & VaR · INTL", page_icon="🎯", layout="wide")

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


def main():
    st.title("🎯 Risk & Value at Risk")
    st.caption("Historical VaR · CVaR · Sharpe · Sortino · Max Drawdown · Beta vs S&P 500")
    st.info("📌 All calculations use free Yahoo Finance data (15-minute delayed). VaR is computed using historical simulation — no normality assumption.", icon="ℹ️")

    # ── Single ticker VaR ──────────────────────────────────────────────────
    st.subheader("Single Asset Risk")
    col1, col2 = st.columns([2, 1])
    with col1:
        ticker = st.text_input("Ticker Symbol", value="NVDA", placeholder="e.g. AAPL, TSLA, BTC-USD").strip().upper()
    with col2:
        period = st.selectbox("Period", ["1y", "6mo", "3mo", "2y"], index=0)

    if st.button("Compute Risk Metrics", use_container_width=True):
        with st.spinner(f"Computing VaR for {ticker}…"):
            try:
                import asyncio
                from agents.math_agent import compute_var, compute_technical
                loop = asyncio.new_event_loop()
                result = loop.run_until_complete(compute_var(ticker, period=period))
                tech   = loop.run_until_complete(compute_technical(ticker))
                loop.close()

                if "error" in result:
                    st.error(f"Could not fetch data for {ticker}: {result['error']}")
                else:
                    c1, c2, c3, c4 = st.columns(4)
                    with c1: st.metric("VaR 95%", f"{result.get('var_95',0):.2f}%", delta="daily loss at 95% conf")
                    with c2: st.metric("VaR 99%", f"{result.get('var_99',0):.2f}%", delta="extreme loss estimate")
                    with c3: st.metric("CVaR 95%", f"{result.get('cvar_95',0):.2f}%", delta="expected shortfall")
                    with c4: st.metric("Max Drawdown", f"{result.get('max_drawdown',0):.2f}%", delta="peak-to-trough")

                    c5, c6, c7, c8 = st.columns(4)
                    with c5: st.metric("Sharpe Ratio", f"{result.get('sharpe',0):.3f}", delta="≥1 good")
                    with c6: st.metric("Sortino Ratio", f"{result.get('sortino',0):.3f}", delta="downside-adjusted")
                    with c7: st.metric("Annual Vol",    f"{result.get('annualised_vol',0):.1f}%")
                    with c8: st.metric("Beta vs SPY",   f"{result.get('beta','N/A')}")

                    st.metric("Total Return", f"{result.get('total_return',0):.2f}%",
                              delta=f"{result.get('observations',0)} observations",
                              delta_color="off")

                    # Technical overlay
                    if "error" not in tech:
                        st.subheader("Technical Indicators")
                        tc1, tc2, tc3, tc4 = st.columns(4)
                        with tc1: st.metric("RSI 14", f"{tech.get('rsi14') or '—'}",
                                            delta=tech.get("rsi_signal", ""))
                        with tc2: st.metric("vs SMA 50",  f"{tech.get('pct_vs_sma50') or 0:+.2f}%")
                        with tc3: st.metric("vs SMA 200", f"{tech.get('pct_vs_sma200') or 0:+.2f}%")
                        with tc4: st.metric("Trend",      tech.get("trend_signal", "—").upper())
            except Exception as e:
                st.error(f"Calculation error: {e}")

    st.divider()

    # ── Portfolio risk ─────────────────────────────────────────────────────
    st.subheader("Portfolio Risk Analysis")
    tickers_input = st.text_input(
        "Tickers (comma-separated, max 10)",
        value="NVDA, AAPL, MSFT, GOOGL, META",
        placeholder="e.g. NVDA, AAPL, MSFT, TSLA"
    )
    use_equal_weight = st.checkbox("Equal weight portfolio", value=True)
    weights_input = ""
    if not use_equal_weight:
        weights_input = st.text_input("Weights (comma-separated, must sum to 1)", value="0.3, 0.2, 0.2, 0.15, 0.15")

    if st.button("Compute Portfolio Risk", use_container_width=True):
        tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()][:10]
        weights = None
        if not use_equal_weight and weights_input:
            try:
                weights = [float(w.strip()) for w in weights_input.split(",")]
                if len(weights) != len(tickers):
                    st.error("Number of weights must match number of tickers.")
                    return
            except ValueError:
                st.error("Invalid weights format.")
                return

        with st.spinner("Computing portfolio metrics…"):
            try:
                import asyncio
                from agents.math_agent import compute_portfolio_risk
                loop = asyncio.new_event_loop()
                result = loop.run_until_complete(compute_portfolio_risk(tickers, weights=weights))
                loop.close()

                if "error" in result:
                    st.error(result["error"])
                    return

                p = result.get("portfolio", {})
                st.subheader(f"Portfolio: {', '.join(tickers)}")
                c1, c2, c3, c4 = st.columns(4)
                with c1: st.metric("Portfolio VaR 95%",   f"{p.get('var_95',0):.2f}%")
                with c2: st.metric("Portfolio CVaR 95%",  f"{p.get('cvar_95',0):.2f}%")
                with c3: st.metric("Portfolio Sharpe",     f"{p.get('sharpe',0):.3f}")
                with c4: st.metric("Portfolio Vol (Ann.)", f"{p.get('annualised_vol',0):.1f}%")

                # Individual holdings table
                ind = result.get("individual", [])
                if ind:
                    st.subheader("Individual Holdings")
                    import pandas as pd
                    df = pd.DataFrame([
                        {
                            "Ticker":   r.get("ticker"),
                            "Weight":   f"{r.get('weight',0):.0%}",
                            "VaR 95%":  f"{r.get('var_95',0):.2f}%",
                            "Sharpe":   f"{r.get('sharpe',0):.3f}",
                            "Max DD":   f"{r.get('max_drawdown',0):.2f}%",
                            "Ann. Vol":  f"{r.get('annualised_vol',0):.1f}%",
                            "Return":   f"{r.get('total_return',0):.2f}%",
                        }
                        for r in ind if "error" not in r
                    ])
                    if not df.empty:
                        st.dataframe(df.set_index("Ticker"), use_container_width=True)

                # Correlation matrix — Plotly heatmap (no matplotlib dependency)
                corr = result.get("correlation")
                if corr:
                    st.subheader("🔥 Correlation Matrix")
                    import pandas as pd
                    corr_df = pd.DataFrame(corr).round(3)
                    try:
                        import plotly.graph_objects as go
                        fig = go.Figure(data=go.Heatmap(
                            z=corr_df.values,
                            x=corr_df.columns,
                            y=corr_df.index,
                            colorscale=[
                                [0.0, "#f75050"],   # -1: red (inverse)
                                [0.5, "#1a1b2e"],   #  0: neutral dark
                                [1.0, "#22d472"],   # +1: green (perfect corr)
                            ],
                            zmin=-1, zmax=1,
                            text=corr_df.round(2).values,
                            texttemplate="%{text:.2f}",
                            textfont={"size": 12, "color": "white"},
                            colorbar=dict(title="ρ", thickness=12, len=0.8,
                                          tickfont=dict(color="#c8cce0")),
                            hovertemplate="<b>%{y} vs %{x}</b><br>Correlation: %{z:.3f}<extra></extra>",
                        ))
                        fig.update_layout(
                            height=max(350, 50 * len(corr_df)),
                            margin=dict(l=10, r=10, t=10, b=10),
                            paper_bgcolor="#0a0a14",
                            plot_bgcolor="#0a0a14",
                            font=dict(color="#c8cce0"),
                            xaxis=dict(side="bottom"),
                            yaxis=dict(autorange="reversed"),
                        )
                        st.plotly_chart(fig, use_container_width=True, theme=None)
                    except ImportError:
                        # Fallback: plain dataframe with conditional formatting via color column
                        def cell_color(v):
                            if v > 0.5:  return "color:#22d472;font-weight:600"
                            if v < -0.5: return "color:#f75050;font-weight:600"
                            return "color:#c8cce0"
                        styled = corr_df.style.map(cell_color) if hasattr(corr_df.style, "map") else corr_df
                        st.dataframe(styled, use_container_width=True)
                    st.caption("Values near 1 = highly correlated (less diversification). Values near -1 = inverse correlation.")

            except Exception as e:
                st.error(f"Calculation error: {e}")

    # ── Systemic Risk Score ────────────────────────────────────────────────
    st.divider()
    st.subheader("🎯 Live Systemic Risk Score")

    try:
        import os
        url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_ANON_KEY")
        if url and key:
            from supabase import create_client
            client  = create_client(url, key)
            try:
                risk_row = (client.table("risk_scores")
                           .select("*")
                           .order("captured_at", desc=True)
                           .limit(1)
                           .execute()).data
            except Exception as e:
                msg = str(e)
                if "risk_scores" in msg and "schema cache" in msg:
                    st.error(
                        "⚠ The `risk_scores` table does not exist in Supabase. "
                        "Run **`supabase/migrations/003_intelligence_tables.sql`** in the Supabase SQL editor.\n\n"
                        "Direct link: https://supabase.com/dashboard/project/jptwbvigtgiffjqnctic/sql/new"
                    )
                else:
                    st.warning(f"Could not load risk data: {e}")
                return
            if risk_row:
                r = risk_row[0]
                srs   = r.get("srs", 0)
                level = r.get("level", "—")
                c = "#22d472" if srs < 26 else "#e3b341" if srs < 51 else "#f07030" if srs < 76 else "#f75050"
                st.markdown(f"### SRS: {srs}/100 — **{level}**")
                st.progress(srs / 100, text=f"Systemic Risk Score: {srs:.1f}")
                factors = r.get("factors", [])
                if factors:
                    import pandas as pd
                    df = pd.DataFrame(factors)[["name", "score", "weight", "description"]].round(2)
                    df["score_bar"] = df["score"].apply(lambda x: f"{'█' * int(x/10)}{'░' * (10-int(x/10))} {x:.0f}")
                    st.dataframe(df.rename(columns={"name":"Factor","score":"Score","weight":"Weight","description":"Description","score_bar":"Risk"}), use_container_width=True)
        else:
            st.info("Connect Supabase to view live SRS data. Add SUPABASE_URL and SUPABASE_ANON_KEY to Streamlit secrets.")
    except Exception as e:
        st.warning(f"Could not load risk data: {e}")


main()
