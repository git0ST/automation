"""India Invest — positional portfolio growth on the NSE (the India-first view).

The full calibrated engine on NIFTY 50: technicals + 5-factor quant scores
(yfinance fundamentals) + 30-analyst consensus + India-VIX risk haircut +
empirical calibration. Outputs a ranked BUY list with ₹ position sizing
(¼-Kelly, 60% gross cap), vol-scaled stops, an AVOID screen, and — when the
Breeze session is live — your actual ICICI holdings reviewed by the engine.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for p in (ROOT, ROOT / "projects" / "daily_digest"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import streamlit as st

st.set_page_config(page_title="India Invest · INTL", page_icon="💼", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _theme import apply_theme
from _strategy_engine import kelly_position_sizing
from shared import breeze_client as bz
apply_theme()
from _terminal_chrome import render_chrome
render_chrome("India Invest")

GROSS_CAP = 0.60   # max fraction of capital deployed across all positions


@st.cache_data(ttl=1800, show_spinner=False)
def _scan():
    from shared.india_swing import scan_india
    return scan_india()


def main():
    col_t, col_r = st.columns([6, 1])
    with col_t:
        st.title("💼 India Invest")
        st.caption("NIFTY 50 positional setups · quant factors · 30-analyst "
                   "consensus · calibrated conviction · ₹ sizing")
    with col_r:
        st.write("")
        if st.button("🔄 Refresh", use_container_width=True):
            _scan.clear()
            st.rerun()

    with st.spinner("Scanning NIFTY 50 (fundamentals + technicals + consensus)…"):
        results, regime = _scan()
    if not results:
        st.error("Scan returned no data — Yahoo may be rate-limited. Retry shortly.")
        return

    # Regime banner
    trend_color = {"bull": "#00d68f", "chop": "#ffaa00", "bear": "#ff5773"}[regime["trend"]]
    st.markdown(
        f"<div style='background:#131825;border:1px solid {trend_color}44;"
        f"border-left:3px solid {trend_color};border-radius:6px;padding:10px 14px;"
        f"margin-bottom:12px'><b style='color:{trend_color}'>{regime['label']}</b>"
        f"<span style='color:#8b93a7;font-size:12px'> · risk haircut SRS≈"
        f"{regime['srs']:.0f}/100 · "
        f"{'longs favoured, fresh shorts gated' if regime['trend'] == 'bull' else 'defensive sizing applies' if regime['trend'] == 'bear' else 'mixed tape — selectivity matters'}"
        f"</span></div>", unsafe_allow_html=True)

    buys = sorted([r for r in results if r["direction"] == "bullish"
                   and r["avoid_level"] != "AVOID"],
                  key=lambda r: -(r["confidence"] * 0.6 + r["quant_score"] * 0.4))
    avoids = [r for r in results if r["avoid_level"] == "AVOID"]
    reduces = [r for r in results if r["avoid_level"] == "REDUCE"
               and r["direction"] != "bullish"]

    c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 2])
    c1.metric("Scanned", len(results))
    c2.metric("BUY candidates", len(buys))
    c3.metric("Avoid", len(avoids))
    c4.metric("Caution", len(reduces))
    with c5:
        capital = st.number_input(
            "Investable capital (₹)", min_value=25_000, max_value=1_000_000_000,
            value=int(st.session_state.get("india_inv_capital", 500_000)),
            step=50_000, key="india_inv_capital",
            help="Position sizes below use ¼-Kelly per name, capped so total "
                 f"deployment ≤ {GROSS_CAP*100:.0f}% of this.")

    # Log the directional calls (learning loop, horizon from the engine)
    try:
        from shared.prediction_tracker import log_prediction
        logged = 0
        for r in buys[:15]:
            if r["confidence"] >= 55:
                if log_prediction(ticker=r["ticker"], direction="bullish",
                                  confidence_pct=r["confidence"], price=r["price"],
                                  source_page="india_invest", sector=r["sector"],
                                  quant_score=r["quant_score"],
                                  quant_grade=r["quant_grade"],
                                  regime_at_pred=f"india_{regime['trend']}",
                                  srs_at_pred=regime["srs"],
                                  horizon=r.get("horizon")):
                    logged += 1
        if logged:
            st.caption(f"📝 {logged} calls logged for outcome scoring.")
    except Exception:
        pass

    tab_buy, tab_avoid, tab_hold = st.tabs([
        f"🚀 Where to invest ({len(buys)})",
        f"🚫 Avoid / caution ({len(avoids) + len(reduces)})",
        "💼 My ICICI holdings",
    ])

    with tab_buy:
        _render_buys(buys, capital)
    with tab_avoid:
        for r in avoids + reduces:
            st.markdown(
                f"<div style='padding:8px 12px;background:#131825;border-left:3px "
                f"solid #ff8800;border-radius:6px;margin-bottom:5px'>"
                f"<b style='color:#e6e9f0'>{r['ticker'].replace('.NS','')}</b> "
                f"<span style='color:#8b93a7;font-size:12px'>{r['name']} — "
                f"{' · '.join(r['avoid_reasons']) or r['avoid_level']}</span></div>",
                unsafe_allow_html=True)
    with tab_hold:
        _render_holdings(results)

    st.caption("⚠ Positional calls (weeks–months). India calibration is young — "
               "sizes are ¼-Kelly conservative on purpose. Track Record shows "
               "the measured hit-rate as outcomes settle.")


def _render_buys(buys: list[dict], capital: float):
    if not buys:
        st.info("No BUY candidates clear the calibrated bar right now — that is "
                "the system telling you to hold cash, not a malfunction.")
        return

    # Sizing pass with the gross-exposure cap
    sized, total = [], 0.0
    for r in buys[:12]:
        daily_vol = (r.get("realized_vol") or 25.0) / 100 / (252 ** 0.5)
        stop_pct = min(0.12, max(0.025, 2.0 * daily_vol))
        k = kelly_position_sizing(win_prob=r["confidence"] / 100, payoff_ratio=2.0,
                                  portfolio_value=capital, stop_pct=stop_pct,
                                  kelly_fraction=0.25)
        sized.append((r, stop_pct, k))
        if not k["no_trade"]:
            total += k["position_value"]
    scale = min(1.0, (capital * GROSS_CAP) / total) if total > 0 else 1.0
    st.markdown(
        f"<div style='font-size:11px;color:#8b93a7;margin-bottom:8px'>Deploying "
        f"<b style='color:#e6e9f0'>{min(total*scale, capital*GROSS_CAP)/capital*100:.0f}%</b> "
        f"of ₹{capital:,.0f} across <b style='color:#e6e9f0'>"
        f"{sum(1 for _, _, k in sized if not k['no_trade'])}</b> names · "
        f"gross cap {GROSS_CAP*100:.0f}%{' · scaled to fit' if scale < 1 else ''} · "
        f"stops volatility-scaled</div>", unsafe_allow_html=True)

    for r, stop_pct, k in sized:
        sym = r["ticker"].replace(".NS", "")
        pos_val = k["position_value"] * scale
        qty = int(pos_val / r["price"]) if r["price"] else 0
        stop = r["price"] * (1 - stop_pct)
        target = r["price"] * (1 + 2 * stop_pct)
        hz = f" · ⏱ {r['horizon_label']}" if r.get("horizon_label") else ""
        with st.expander(
            f"**{sym}** · {r['name']} · {r['confidence']:.0f}% · "
            f"Quant {r['quant_grade']} · ₹{r['price']:,.1f}{hz}",
            expanded=False,
        ):
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Buy ≈", f"₹{r['price']:,.1f}",
                      delta=f"{r['chg_1d']:+.2f}% today")
            c2.metric("Stop", f"₹{stop:,.1f}",
                      delta=f"-{stop_pct*100:.1f}%", delta_color="off")
            c3.metric("Target (2R)", f"₹{target:,.1f}")
            c4.metric("Position", "SKIP" if k["no_trade"] or qty < 1 else
                      f"₹{pos_val:,.0f}",
                      delta=None if qty < 1 else f"{qty} sh · "
                      f"{pos_val/capital*100:.1f}%", delta_color="off")
            c5.metric("Analyst upside", f"{r['target_upside']:+.1f}%"
                      if r.get("target_upside") is not None else "—",
                      delta=f"{r.get('n_analysts', 0)} analysts", delta_color="off")
            st.markdown(f"**Why:** {r['rationale']}")
            f = r.get("factors") or {}
            if f:
                cc = st.columns(5)
                for col, key, lbl in zip(cc, ["value", "growth", "profit",
                                              "momentum", "revisions"],
                                          ["Value", "Growth", "Profit",
                                           "Momentum", "Revisions"]):
                    g = (f.get(key) or {})
                    col.metric(lbl, g.get("grade", "—"),
                               delta=f"{g.get('score', 0):.0f}", delta_color="off")


def _render_holdings(results: list[dict]):
    if not bz.is_live():
        st.info("Connect Breeze (daily session token) to review your actual "
                "ICICI holdings here — each gets a HOLD / ADD / TRIM verdict "
                "from the engine.")
        return
    try:
        b = bz.connect()
        resp = b.get_portfolio_holdings(exchange_code="NSE", from_date="",
                                        to_date="", stock_code="", portfolio_type="")
        rows = (resp or {}).get("Success") or []
    except Exception as e:
        st.warning(f"Holdings fetch failed: {e}")
        return
    if not rows:
        st.info("No NSE holdings returned for this account.")
        return

    by_name = {r["name"].lower(): r for r in results}
    for h in rows:
        nm = (h.get("stock_code") or h.get("company_name") or "?")
        qty = h.get("quantity") or h.get("total_quantity") or "—"
        avg = h.get("average_price") or "—"
        match = next((r for key, r in by_name.items()
                      if str(nm).lower()[:6] in key.replace(" ", "")), None)
        verdict, color = "—", "#8b93a7"
        if match:
            if match["avoid_level"] == "AVOID":
                verdict, color = "TRIM / EXIT", "#ff5773"
            elif match["direction"] == "bullish" and match["confidence"] >= 60:
                verdict, color = "ADD", "#00d68f"
            else:
                verdict, color = "HOLD", "#ffaa00"
        st.markdown(
            f"<div style='display:flex;gap:14px;align-items:center;padding:8px 12px;"
            f"background:#131825;border:1px solid #1f2937;border-radius:6px;"
            f"margin-bottom:5px'><b style='color:#e6e9f0;min-width:90px'>{nm}</b>"
            f"<span style='color:#8b93a7;font-size:12px'>qty {qty} · avg ₹{avg}</span>"
            f"<span style='margin-left:auto;color:{color};font-weight:700'>{verdict}</span>"
            f"</div>", unsafe_allow_html=True)


main()
