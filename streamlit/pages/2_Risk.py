"""
Risk & VaR analysis — institutional-grade risk metrics.

Aladdin-inspired features:
  - Historical Value-at-Risk (no normality assumption)
  - Multi-asset portfolio risk + correlation matrix
  - Stress test scenarios (rate shock, equity crash, vol spike)
  - Live Systemic Risk Score with factor decomposition
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for p in (ROOT, ROOT / "projects" / "daily_digest"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import streamlit as st

st.set_page_config(page_title="Risk & VaR · INTL", page_icon="🎯", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _theme import apply_theme, COLORS, status_pill
from _data  import supabase_client, fetch_fred_live
apply_theme()
from _terminal_chrome import render_chrome
render_chrome("Risk")


def main():
    st.title("🎯 Risk & Value at Risk")
    st.caption("Historical VaR · Multi-asset portfolios · Stress scenarios · Live SRS")

    tab_single, tab_portfolio, tab_scenarios, tab_srs = st.tabs([
        "📈 Single Asset", "📊 Portfolio", "⚡ Stress Scenarios", "🎯 Systemic Risk"
    ])

    # ── Single Asset VaR ──────────────────────────────────────────────────────
    with tab_single:
        _render_single_asset()

    # ── Portfolio Risk ────────────────────────────────────────────────────────
    with tab_portfolio:
        _render_portfolio_risk()

    # ── Aladdin-style Stress Scenarios ────────────────────────────────────────
    with tab_scenarios:
        _render_stress_scenarios()

    # ── Live Systemic Risk Score ──────────────────────────────────────────────
    with tab_srs:
        _render_systemic_risk()


def _render_single_asset():
    """Single-ticker VaR with full risk metrics."""
    st.markdown("#### Compute risk metrics for a single asset")
    st.caption("Historical VaR uses 1-year of daily returns — no normality assumption.")

    col1, col2 = st.columns([3, 1])
    with col1:
        ticker = st.text_input("Ticker Symbol", value="NVDA",
                               placeholder="e.g. AAPL, TSLA, BTC-USD").strip().upper()
    with col2:
        period = st.selectbox("Period", ["1y", "6mo", "3mo", "2y"], index=0)

    if st.button("📊 Compute Risk Metrics", use_container_width=True, type="primary"):
        if not ticker:
            st.error("Please enter a ticker symbol.")
            return

        with st.spinner(f"Computing VaR for {ticker}…"):
            try:
                import asyncio
                from agents.math_agent import compute_var, compute_technical
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(compute_var(ticker, period=period))
                    tech   = loop.run_until_complete(compute_technical(ticker))
                finally:
                    loop.close()
            except Exception as e:
                st.error(f"Failed to compute risk: {e}")
                return

        if "error" in result:
            st.error(f"Could not fetch data for {ticker}: {result['error']}")
            return

        # Primary metrics grid
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("VaR 95%",      f"{result.get('var_95', 0):.2f}%",  delta="daily, 95% conf")
        c2.metric("VaR 99%",      f"{result.get('var_99', 0):.2f}%",  delta="extreme loss")
        c3.metric("CVaR 95%",     f"{result.get('cvar_95', 0):.2f}%", delta="expected shortfall")
        c4.metric("Max Drawdown", f"{result.get('max_drawdown', 0):.2f}%", delta="peak-to-trough")

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Sharpe",     f"{result.get('sharpe', 0):.3f}",   delta="≥1 is good")
        c6.metric("Sortino",    f"{result.get('sortino', 0):.3f}",  delta="downside-adjusted")
        c7.metric("Annual Vol", f"{result.get('annualised_vol', 0):.1f}%")
        c8.metric("Beta vs SPY", f"{result.get('beta', 'N/A')}")

        # Technical overlay
        if "error" not in tech:
            with st.expander("📊 Technical Indicators", expanded=True):
                tc1, tc2, tc3, tc4 = st.columns(4)
                tc1.metric("RSI 14",    f"{tech.get('rsi14') or '—'}", delta=tech.get("rsi_signal", ""))
                tc2.metric("vs SMA 50", f"{tech.get('pct_vs_sma50') or 0:+.2f}%")
                tc3.metric("vs SMA 200", f"{tech.get('pct_vs_sma200') or 0:+.2f}%")
                tc4.metric("Trend",     (tech.get("trend_signal") or "—").upper())


def _render_portfolio_risk():
    """Multi-asset portfolio risk + correlation."""
    st.markdown("#### Portfolio risk decomposition")
    st.caption("Computes weighted VaR, individual contributions, and full correlation matrix.")

    tickers_input = st.text_input(
        "Tickers (comma-separated, max 10)",
        value="NVDA, AAPL, MSFT, GOOGL, META",
        placeholder="e.g. NVDA, AAPL, MSFT, TSLA",
    )
    use_equal_weight = st.checkbox("Equal weight portfolio", value=True)
    weights_input = ""
    if not use_equal_weight:
        weights_input = st.text_input(
            "Weights (comma-separated, must sum to 1)", value="0.3, 0.2, 0.2, 0.15, 0.15"
        )

    if st.button("📊 Compute Portfolio Risk", use_container_width=True, type="primary"):
        tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()][:10]
        if not tickers:
            st.error("Please enter at least one ticker.")
            return

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
                try:
                    result = loop.run_until_complete(
                        compute_portfolio_risk(tickers, weights=weights)
                    )
                finally:
                    loop.close()
            except Exception as e:
                st.error(f"Computation failed: {e}")
                return

        if "error" in result:
            st.error(result["error"])
            return

        p = result.get("portfolio", {})
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Portfolio VaR 95%",  f"{p.get('var_95', 0):.2f}%")
        c2.metric("Portfolio CVaR 95%", f"{p.get('cvar_95', 0):.2f}%")
        c3.metric("Portfolio Sharpe",   f"{p.get('sharpe', 0):.3f}")
        c4.metric("Portfolio Vol (Ann.)", f"{p.get('annualised_vol', 0):.1f}%")

        # Individual holdings
        ind = result.get("individual", [])
        if ind:
            with st.expander("📋 Individual Holdings", expanded=True):
                import pandas as pd
                df = pd.DataFrame([
                    {
                        "Ticker":   r.get("ticker"),
                        "Weight":   f"{r.get('weight', 0):.0%}",
                        "VaR 95%":  f"{r.get('var_95', 0):.2f}%",
                        "Sharpe":   f"{r.get('sharpe', 0):.3f}",
                        "Max DD":   f"{r.get('max_drawdown', 0):.2f}%",
                        "Ann. Vol":  f"{r.get('annualised_vol', 0):.1f}%",
                        "Return":   f"{r.get('total_return', 0):.2f}%",
                    }
                    for r in ind if "error" not in r
                ])
                if not df.empty:
                    st.dataframe(df.set_index("Ticker"), use_container_width=True)

        # Correlation matrix (Plotly — no matplotlib dependency)
        corr = result.get("correlation")
        if corr and len(corr) > 1:
            with st.expander("🔥 Correlation Matrix", expanded=True):
                _render_correlation_heatmap(corr)


def _render_correlation_heatmap(corr: dict):
    """Plotly correlation heatmap with annotations. No matplotlib needed."""
    import pandas as pd
    import plotly.graph_objects as go
    corr_df = pd.DataFrame(corr).round(3)
    fig = go.Figure(data=go.Heatmap(
        z=corr_df.values,
        x=list(corr_df.columns),
        y=list(corr_df.index),
        colorscale=[
            [0.0, "#ff5773"],   # -1 = red (inverse)
            [0.5, "#1a2034"],   #  0 = neutral
            [1.0, "#00d68f"],   # +1 = green (perfect)
        ],
        zmin=-1, zmax=1,
        text=corr_df.round(2).values,
        texttemplate="%{text:.2f}",
        textfont={"size": 12, "color": "white", "family": "IBM Plex Mono"},
        colorbar=dict(title="ρ", thickness=12, len=0.8,
                      tickfont=dict(color="#e6e9f0", family="IBM Plex Mono")),
        hovertemplate="<b>%{y} vs %{x}</b><br>Correlation: %{z:.3f}<extra></extra>",
    ))
    fig.update_layout(
        height=max(350, 50 * len(corr_df)),
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["bg"],
        font=dict(color=COLORS["text"], family="Inter"),
        xaxis=dict(side="bottom", gridcolor=COLORS["border"]),
        yaxis=dict(autorange="reversed", gridcolor=COLORS["border"]),
    )
    st.plotly_chart(fig, use_container_width=True, theme=None)
    st.caption("ρ near 1 = correlated (less diversification). Near -1 = inverse correlation.")


def _render_stress_scenarios():
    """Aladdin-inspired what-if stress tests on a portfolio."""
    st.markdown("#### Stress test scenarios")
    st.caption(
        "Apply shocks to risk factors and see estimated P&L impact on a portfolio. "
        "Inspired by Aladdin's Market-Driven Scenario tooling."
    )

    tickers_input = st.text_input(
        "Portfolio tickers",
        value="SPY, QQQ, NVDA, TLT, GLD",
        placeholder="e.g. SPY, QQQ, NVDA, TLT, GLD",
    )

    st.markdown("##### Shock factors")
    sc1, sc2, sc3, sc4 = st.columns(4)
    with sc1:
        equity_shock = st.slider("Equity shock (S&P)", -50, 30, -10, step=5, help="Change in SPY")
    with sc2:
        rate_shock = st.slider("Rate shock (bps)", -200, 200, 50, step=25, help="Δ in 10Y treasury")
    with sc3:
        vol_shock = st.slider("Vol regime change", -10, 30, 5, step=5, help="Δ VIX (points)")
    with sc4:
        usd_shock = st.slider("USD strength %", -20, 20, 0, step=2, help="DXY change")

    # Preset scenarios
    st.markdown("##### Preset scenarios")
    pc1, pc2, pc3, pc4, pc5 = st.columns(5)
    presets = {
        "2008-style crash":  (-30, -100, 25, 8),
        "Stagflation":       (-15, 100,  10, -5),
        "Goldilocks rally":  (15,  -50,  -3, 0),
        "Geopol shock":      (-12, 30,  15, 12),
        "Rate cuts":         (8,   -75,  -5, -8),
    }
    for col, (name, vals) in zip([pc1, pc2, pc3, pc4, pc5], presets.items()):
        with col:
            if st.button(name, use_container_width=True, key=f"preset_{name}"):
                st.session_state["scenario_preset"] = vals
                st.rerun()

    if st.session_state.get("scenario_preset"):
        equity_shock, rate_shock, vol_shock, usd_shock = st.session_state["scenario_preset"]
        st.info(f"Applied preset: equity {equity_shock:+}% · rates {rate_shock:+}bps · "
                f"vol {vol_shock:+} · USD {usd_shock:+}%", icon="📌")
        if st.button("Reset", key="reset_preset"):
            del st.session_state["scenario_preset"]
            st.rerun()

    if st.button("⚡ Run Stress Test", use_container_width=True, type="primary"):
        tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()][:10]
        if not tickers:
            st.error("Please enter at least one ticker.")
            return

        with st.spinner("Estimating shock impact on portfolio…"):
            results = _estimate_shock_impact(
                tickers, equity_shock, rate_shock, vol_shock, usd_shock
            )

        if not results:
            st.error("Couldn't compute shock impact — check ticker symbols.")
            return

        # Portfolio-level
        total_impact = sum(r["pnl_pct"] * r["weight"] for r in results)
        st.markdown(f"#### Portfolio P&L Impact: "
                    f"<span class='{'kpi-negative' if total_impact < 0 else 'kpi-positive'}'>"
                    f"{total_impact:+.2f}%</span>", unsafe_allow_html=True)

        # Per-asset breakdown
        import pandas as pd
        df = pd.DataFrame([{
            "Ticker":   r["ticker"],
            "Weight":   f"{r['weight']:.0%}",
            "Beta·Eq":  f"{r['beta_eq']:.2f}",
            "Dur·Rate": f"{r['duration']:.1f}",
            "P&L Impact": f"{r['pnl_pct']:+.2f}%",
            "Contrib":  f"{r['pnl_pct'] * r['weight']:+.3f}%",
        } for r in results])
        st.dataframe(df.set_index("Ticker"), use_container_width=True)

        st.caption(
            "**Methodology:** P&L impact = β_eq × equity_shock + duration × (-Δ rates / 100) "
            "+ vol_beta × Δ VIX. Betas + durations estimated from asset class (equity / bond / commodity / FX)."
        )


def _estimate_shock_impact(tickers, eq_shock, rate_shock_bps, vol_shock, usd_shock):
    """Estimate P&L impact of factor shocks per ticker. Uses asset-class heuristics."""
    # Asset class classification
    CLASS_MAP = {
        # Equity ETFs / stocks → high equity beta, low duration
        # Bond ETFs → equity beta ~0.2, high duration
        # Gold → equity beta -0.1, USD beta -1.0
        # Crypto → equity beta 1.5
    }
    # Heuristic classifier
    def classify(t):
        t = t.upper()
        if t in ("TLT", "IEF", "AGG", "BND", "LQD", "HYG"):
            return "bond"
        if t in ("GLD", "SLV", "GDX", "DBC"):
            return "commodity"
        if "BTC" in t or "ETH" in t or "SOL" in t or "USD" in t and "-USD" in t:
            return "crypto"
        if t in ("UUP",):
            return "fx_usd"
        if t.startswith("^"):
            return "index"
        return "equity"

    BETAS = {
        # (eq_beta, duration_years, vol_beta, usd_beta)
        "equity":    (1.0,  0.0,  -0.7,  0.1),
        "index":     (1.0,  0.0,  -0.5,  0.0),
        "bond":      (0.2,  7.0,  -0.1,  -0.2),
        "commodity": (0.3,  0.0,   0.0,  -0.6),
        "crypto":    (1.5,  0.0,  -1.0,  0.3),
        "fx_usd":    (0.0,  0.0,   0.0,   1.0),
    }
    n = len(tickers)
    weight = 1.0 / n
    results = []
    for t in tickers:
        cls = classify(t)
        eq_b, dur, vol_b, usd_b = BETAS[cls]
        # P&L decomposition
        eq_contrib   = eq_b * eq_shock
        rate_contrib = -dur * (rate_shock_bps / 100)
        vol_contrib  = vol_b * vol_shock * 0.3   # vol shock damped — % per VIX pt
        usd_contrib  = usd_b * usd_shock * 0.4   # USD shock damped
        pnl = eq_contrib + rate_contrib + vol_contrib + usd_contrib
        results.append({
            "ticker": t, "weight": weight,
            "beta_eq": eq_b, "duration": dur,
            "pnl_pct": round(pnl, 2),
            "class": cls,
        })
    return results


def _render_systemic_risk():
    """Live SRS with factor decomposition."""
    st.markdown("#### Live Systemic Risk Score")
    st.caption("Composite 0-100 score from VIX, yield curve, credit spreads, sentiment, labor.")

    client = supabase_client()
    risk_row = None

    if client:
        try:
            risk_row = (client.table("risk_scores")
                       .select("*")
                       .order("captured_at", desc=True)
                       .limit(1)
                       .execute()).data
        except Exception as e:
            if "risk_scores" in str(e) and "schema cache" in str(e):
                st.error(
                    "⚠ The `risk_scores` table doesn't exist. Run "
                    "[migration 003](https://github.com/git0ST/automation/blob/main/supabase/migrations/003_intelligence_tables.sql) "
                    "in [Supabase SQL Editor](https://supabase.com/dashboard/project/jptwbvigtgiffjqnctic/sql/new)."
                )
                return
            else:
                st.warning(f"Could not load risk data: {e}")

    # Fallback to live FRED computation
    if not risk_row:
        st.info("📡 No SRS history in Supabase yet — computing live from FRED…")
        from _data import compute_regime_risk_live
        _, risk_live = compute_regime_risk_live()
        if risk_live:
            _render_srs_card(risk_live)
        else:
            st.error("Could not compute SRS from live FRED data either. Check internet connectivity.")
        return

    _render_srs_card(risk_row[0])


def _render_srs_card(r: dict):
    """Render a Systemic Risk Score card with factor breakdown."""
    srs   = r.get("srs", 0)
    level = r.get("level", "—")
    c = "#00d68f" if srs < 26 else "#ffaa00" if srs < 51 else "#ff8800" if srs < 76 else "#ff5773"

    st.markdown(f"""
    <div style="background:#131825;border:1px solid #1f2937;border-radius:8px;padding:24px;margin:12px 0">
      <div style="display:flex;align-items:baseline;gap:14px">
        <span style="font-size:48px;font-weight:700;color:{c};font-family:'IBM Plex Mono',monospace;line-height:1">{srs:.0f}</span>
        <span style="font-size:14px;color:#8b93a7">/ 100</span>
        <span style="font-size:16px;color:{c};font-weight:600;margin-left:auto">{level}</span>
      </div>
      <div style="background:#0f1422;border-radius:4px;height:10px;overflow:hidden;margin-top:14px">
        <div style="height:100%;width:{srs}%;background:{c};border-radius:4px;transition:width 0.5s"></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    factors = r.get("factors", [])
    if factors:
        with st.expander("📊 Factor Decomposition", expanded=True):
            import pandas as pd
            df = pd.DataFrame(factors)
            if "name" in df.columns:
                cols = [c for c in ["name", "score", "weight", "description"] if c in df.columns]
                df = df[cols].round(2)
                if "score" in df.columns:
                    df["bar"] = df["score"].apply(
                        lambda x: f"{'█' * int(x/10)}{'░' * (10-int(x/10))} {x:.0f}"
                    )
                st.dataframe(df.rename(columns={
                    "name": "Factor", "score": "Score", "weight": "Weight",
                    "description": "Description", "bar": "Visual",
                }), use_container_width=True)

    top_risks = r.get("top_risks", [])
    if top_risks:
        st.markdown("##### Top risks")
        for risk in top_risks[:5]:
            st.markdown(f"- {risk}")


main()
