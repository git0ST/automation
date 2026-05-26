"""Strategies — recommended trades by horizon with position sizing.

Combines Opportunity Scanner with the strategy_engine to surface
named playbook recommendations (Quality Momentum, Value Reversal, etc.)
with entry/stop/target levels and Kelly-adjusted position sizes.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for p in (ROOT, ROOT / "projects" / "daily_digest"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import streamlit as st

st.set_page_config(page_title="Strategies · INTL", page_icon="🎲", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _theme           import apply_theme, COLORS, status_pill, KPI_HELP
from _strategy_engine import (STRATEGIES, find_strategies, position_sizing,
                                compute_levels, _grade_to_int)
from _components       import TICKER_META
apply_theme()
from _terminal_chrome import render_chrome
render_chrome("Strategies")


HORIZON_HELP = {
    "short":  "1-3 weeks. Active management, tighter stops, more turnover.",
    "medium": "2-12 weeks. Standard swing trade. Position-size by conviction.",
    "long":   "6 months+. Buy-and-hold quality. Lower turnover, tax-efficient.",
}


@st.cache_data(ttl=900, show_spinner=False)
def scan_with_strategies(tickers: tuple) -> list[dict]:
    """Reuse the opportunity scanner output + map each to its strategies."""
    # Import the scan from pages/6_Opportunities.py
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "opp", Path(__file__).parent / "6_Opportunities.py")
    opp_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(opp_mod)
    results = opp_mod.scan_universe(tickers)

    # Enrich each with strategy matches + sector
    enriched = []
    for r in results:
        ticker = r["ticker"]
        meta = TICKER_META.get(ticker, {})

        # Build setup dict for strategy engine
        f = r["factors"]
        setup = {
            "composite_quant":    r["quant_score"],
            "quant_grade":        r["quant_grade"],
            "value_grade":        f["value"]["grade"],
            "growth_grade":       f["growth"]["grade"],
            "profit_grade":       f["profit"]["grade"],
            "momentum_grade":     f["momentum"]["grade"],
            "technical_direction": r["direction"],
            "rsi":                r.get("rsi_14"),
            "above_sma_200":      (r.get("vs_sma_200") or -1) > 0,
            "below_sma_200":      (r.get("vs_sma_200") or 1) < 0,
            "sector":             meta.get("sector", ""),
            "confidence":         r["confidence"],
        }

        matches = find_strategies(setup)
        r["strategies"] = matches
        r["setup"]      = setup
        enriched.append(r)
    return enriched


def main():
    col_t, col_r = st.columns([6, 1])
    with col_t:
        st.title("🎲 Investment Strategies")
        st.caption("Setups mapped to named playbooks with entry/stop/target levels and "
                   "position sizing. Filter by time horizon.")
    with col_r:
        st.write("")
        if st.button("🔄 Refresh", use_container_width=True):
            scan_with_strategies.clear()
            st.rerun()

    # Universe + portfolio inputs
    col_uni, col_pv = st.columns([3, 1])
    with col_uni:
        SCAN_UNIVERSE = [
            "NVDA", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "TSLA", "AVGO", "ORCL",
            "AMD", "INTC", "QCOM", "TSM", "MU", "ARM", "SMCI",
            "JPM", "GS", "MS", "BAC", "V", "MA", "BLK",
            "XOM", "CVX", "COP", "UNH", "LLY", "JNJ", "MRK", "ABBV",
            "WMT", "COST", "HD", "MCD", "DIS", "NFLX",
            "BA", "CAT", "GE", "RTX",
        ]
        universe = st.multiselect(
            "Scan universe",
            SCAN_UNIVERSE, default=SCAN_UNIVERSE, max_selections=60,
        )
    with col_pv:
        portfolio_value = st.number_input("Portfolio value ($)", min_value=1000,
                                            value=100_000, step=10_000,
                                            help="Used for position sizing math")

    if not universe:
        st.warning("Select at least one ticker.")
        return

    with st.spinner(f"Scanning {len(universe)} tickers + matching strategies…"):
        results = scan_with_strategies(tuple(universe))

    # Count tickers with at least 1 strategy match
    with_strategies = [r for r in results if r.get("strategies")]
    by_horizon = {"short": [], "medium": [], "long": []}
    by_strategy = {}
    for r in with_strategies:
        for s in r["strategies"]:
            h = s["horizon"]
            by_horizon[h].append((r, s))
            by_strategy.setdefault(s["name"], []).append(r)

    # KPI strip
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Scanned", len(results))
    c2.metric("With strategies",  len(with_strategies),
              delta=f"{len(with_strategies)/max(len(results),1)*100:.0f}%",
              delta_color="off")
    c3.metric("Short-term",  len(by_horizon["short"]),
              delta="1-3 weeks", delta_color="off",
              help=HORIZON_HELP["short"])
    c4.metric("Long-term",   len(by_horizon["long"]),
              delta="6+ months", delta_color="off",
              help=HORIZON_HELP["long"])

    st.divider()

    # Tabs by horizon + by strategy
    tab_short, tab_mid, tab_long, tab_by_strat = st.tabs([
        f"⚡ Short ({len(by_horizon['short'])})",
        f"📊 Medium ({len(by_horizon['medium'])})",
        f"🏛 Long ({len(by_horizon['long'])})",
        f"🎯 By Strategy",
    ])

    with tab_short:
        st.caption(HORIZON_HELP["short"])
        _render_horizon_tab(by_horizon["short"], portfolio_value)

    with tab_mid:
        st.caption(HORIZON_HELP["medium"])
        _render_horizon_tab(by_horizon["medium"], portfolio_value)

    with tab_long:
        st.caption(HORIZON_HELP["long"])
        _render_horizon_tab(by_horizon["long"], portfolio_value)

    with tab_by_strat:
        st.caption("Each row = one named playbook. Tickers under each = current matches.")
        for strat_name, tickers in by_strategy.items():
            with st.expander(f"**{strat_name}** · {len(tickers)} match(es)",
                              expanded=False):
                # Find strategy def
                strat = next((s for s in STRATEGIES if s["name"] == strat_name), None)
                if strat:
                    st.markdown(f"**Summary:** {strat['summary']}")
                    cc1, cc2, cc3 = st.columns(3)
                    cc1.metric("Horizon", strat["horizon"].title())
                    cc2.metric("Expected return", strat["expected_return"])
                    cc3.metric("Expected duration", strat["expected_duration"])
                # Ticker list
                cols = st.columns(4)
                for i, r in enumerate(tickers[:12]):
                    with cols[i % 4]:
                        if st.button(f"{r['ticker']} ${r['price']:.2f}",
                                      key=f"strat_{strat_name}_{r['ticker']}",
                                      use_container_width=True):
                            st.session_state["detail_ticker"] = r["ticker"]
                            st.switch_page("pages/5_Stock_Detail.py")


def _render_horizon_tab(items: list[tuple], portfolio_value: float):
    """Render a horizon tab with setup cards."""
    if not items:
        st.info("No setups match strategies in this horizon. "
                "Try widening the scan universe.")
        return

    # Sort by composite quant score
    items_sorted = sorted(items, key=lambda x: -x[0]["quant_score"])[:15]

    for r, strat in items_sorted:
        # ATR for level calculation — synthetic 2% if we don't have it
        atr_estimate = r["price"] * 0.02
        levels = compute_levels(
            r["price"], atr_estimate,
            strat["stop_atr_mult"], strat["target_atr_mult"],
            direction=strat["direction"],
        )
        sizing = position_sizing(
            stop_pct=(levels.get("stop_pct") or 4) / 100,
            conviction=r["confidence"] / 100,
            portfolio_value=portfolio_value,
        )

        dir_color = ("#00d68f" if strat["direction"] == "long"
                     else "#ff5773")
        meta = TICKER_META.get(r["ticker"], {})

        with st.expander(
            f"**{r['ticker']}** · {meta.get('name', r['ticker'])} · "
            f"**{strat['name']}** · {strat['direction'].upper()} · "
            f"Quant {r['quant_grade']} · {r['confidence']:.0f}% conf",
            expanded=False,
        ):
            st.markdown(f"_{strat['summary']}_")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Entry",  f"${levels['entry']:.2f}",
                      help="Suggested entry price (current market)")
            c2.metric("Stop",   f"${levels['stop']:.2f}" if levels["stop"] else "—",
                      delta=f"-{levels['stop_pct']:.1f}%" if levels["stop_pct"] else "",
                      delta_color="inverse",
                      help="ATR-based stop loss")
            c3.metric("Target", f"${levels['target']:.2f}" if levels["target"] else "—",
                      delta=f"R/R {levels['r_multiple']:.1f}:1" if levels["r_multiple"] else "",
                      delta_color="off",
                      help="ATR-based price target")
            c4.metric("Expected", strat["expected_return"],
                      delta=strat["expected_duration"], delta_color="off")

            st.markdown("**Position sizing** (Kelly-adjusted, capped at 15% portfolio)")
            ss1, ss2, ss3 = st.columns(3)
            ss1.metric("Position",   f"${sizing['position_value']:,.0f}",
                       delta=f"{sizing['position_pct']:.1f}% portfolio",
                       delta_color="off",
                       help="$ amount to invest based on stop distance")
            ss2.metric("Risk if stop hit", f"${sizing['risk_amount']:,.0f}",
                       delta=f"{(sizing['risk_amount'] / portfolio_value) * 100:.2f}%",
                       delta_color="off",
                       help="Max $ loss if stop triggers")
            ss3.metric("Kelly fraction", f"{sizing['kelly_pct']:.1f}%",
                       delta="of full Kelly", delta_color="off",
                       help="Capped at half-Kelly to reduce ruin risk")

            if st.button(f"🔍 Open {r['ticker']} in Stock Detail",
                          key=f"open_{strat['name']}_{r['ticker']}",
                          use_container_width=True):
                st.session_state["detail_ticker"] = r["ticker"]
                st.switch_page("pages/5_Stock_Detail.py")


main()
