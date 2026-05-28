"""Opportunity Scanner — ranked high-conviction setups across the watchlist.

Runs the composite prediction engine + multi-factor quant score across 50+
stocks and surfaces:
  - Top Bullish (highest confidence + bullish direction)
  - Top Bearish (highest confidence + bearish direction)
  - High Quant Score (A/A+ across factors)

For each setup the breakdown shows: which signals fired, confidence,
quant grade, 1-click drill-down to Stock Detail page.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for p in (ROOT, ROOT / "projects" / "daily_digest"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import streamlit as st

st.set_page_config(page_title="Opportunities · INTL", page_icon="🎯", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _theme              import apply_theme, COLORS, status_pill
from _stock_analysis     import (technical_signal, sentiment_signal, analyst_signal,
                                  sector_signal, vol_signal, composite_prediction)
from _advanced_technicals import compute_all_technicals
from _quant_score        import compute_quant_score
from _components         import TICKER_META
from _data               import supabase_client
apply_theme()
from _terminal_chrome import render_chrome
render_chrome("Opportunities")


@st.cache_data(ttl=120, show_spinner=False)
def load_latest_snapshot() -> tuple[list, str | None]:
    """Read latest opportunity scan from Supabase (populated by pipeline cron).

    Returns (results, scanned_at_iso). Empty list if snapshot table missing.
    """
    client = supabase_client()
    if not client:
        return [], None
    try:
        rows = (client.table("v_latest_opportunities")
                .select("*")
                .order("confidence", desc=True)
                .execute()).data or []
        if not rows:
            return [], None
        # Reshape to match scan_universe() output format
        results = []
        scanned_at = rows[0].get("scanned_at")
        for r in rows:
            results.append({
                "ticker":      r["ticker"],
                "name":        TICKER_META.get(r["ticker"], {}).get("name", r["ticker"]),
                "sector":      r.get("sector") or TICKER_META.get(r["ticker"], {}).get("sector", "—"),
                "price":       r.get("price") or 0,
                "chg_1d":      r.get("chg_1d") or 0,
                "ret_3m":      r.get("ret_3m"),
                "ret_6m":      r.get("ret_6m"),
                "ret_12m":     r.get("ret_12m"),
                "rsi_14":      r.get("rsi_14") or 50,
                "vs_sma_50":   r.get("vs_sma_50"),
                "vs_sma_200":  r.get("vs_sma_200"),
                "direction":   r.get("direction") or "neutral",
                "confidence":  r.get("confidence") or 0,
                "rationale":   r.get("rationale") or "",
                "components":  r.get("components") or [],
                "quant_score": r.get("quant_score") or 0,
                "quant_grade": r.get("quant_grade") or "—",
                "factors":     r.get("factors") or {},
                "strategies":  r.get("strategies") or [],
            })
        return results, scanned_at
    except Exception:
        return [], None


@st.cache_data(ttl=600, show_spinner=False)
def _sector_returns_map() -> dict:
    """Pull 5-day sector ETF returns for sector-confirmation signal."""
    try:
        import yfinance as yf
        ETF_MAP = {
            # Information technology
            "Tech": "XLK", "Software": "XLK", "Semis": "XLK",
            # Financials
            "Fin": "XLF", "Bank": "XLF", "Payments": "XLF", "Financials": "XLF",
            "AssetMgmt": "XLF", "Insurance": "XLF",
            # Healthcare
            "Health": "XLV", "Pharma": "XLV", "Biotech": "XLV", "MedTech": "XLV",
            # Energy / materials / utilities / real estate
            "Energy": "XLE", "Materials": "XLB", "Utility": "XLU", "REIT": "XLRE",
            # Consumer
            "Auto": "XLY", "Discretionary": "XLY", "Restaurant": "XLY", "Apparel": "XLY",
            "Retail": "XLP", "Staples": "XLP",
            # Communication
            "Media": "XLC", "Telecom": "XLC",
            # Industrials
            "Industrial": "XLI", "Aerospace": "XLI", "Conglomerate": "XLI",
        }
        returns = {}
        for sector, etf in ETF_MAP.items():
            try:
                hist = yf.Ticker(etf).history(period="10d", auto_adjust=True)
                if len(hist) >= 5:
                    ret = (float(hist["Close"].iloc[-1]) /
                           float(hist["Close"].iloc[-5]) - 1) * 100
                    returns[sector] = ret
            except Exception:
                continue
        return returns
    except Exception:
        return {}


# Scan universe — single source of truth lives in shared/scan_universe.py so the
# live scanner and the headless pipeline scanner can never diverge in coverage.
from shared.scan_universe import UNIVERSE_BY_SECTOR, SCAN_UNIVERSE

# Quick presets — let the user trade breadth vs. live-scan speed in one click.
# (Live scan time scales ~linearly with ticker count; snapshot mode is instant.)
UNIVERSE_PRESETS = {
    "Broad — all 11 sectors (90+)": SCAN_UNIVERSE,
    "Core mega caps (15)": ["NVDA", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "TSLA",
                            "AVGO", "JPM", "V", "UNH", "LLY", "XOM", "WMT", "HD"],
    "Tech & Semis focus": (UNIVERSE_BY_SECTOR["Mega Tech"] + UNIVERSE_BY_SECTOR["Semis"]
                           + UNIVERSE_BY_SECTOR["Software"]),
    "Defensive (Staples · Health · Utilities)": (UNIVERSE_BY_SECTOR["Staples"]
                           + UNIVERSE_BY_SECTOR["Healthcare"] + UNIVERSE_BY_SECTOR["Utilities"]),
    "Cyclical (Energy · Materials · Industrials · Financials)": (
                           UNIVERSE_BY_SECTOR["Energy"] + UNIVERSE_BY_SECTOR["Materials"]
                           + UNIVERSE_BY_SECTOR["Industrials"] + UNIVERSE_BY_SECTOR["Financials"]),
}

# Master option list for the multiselect (union of everything we know about)
_ALL_TICKERS = sorted({t for names in UNIVERSE_BY_SECTOR.values() for t in names})


@st.cache_data(ttl=900, show_spinner=False)  # 15 min — scan is expensive
def scan_universe(tickers: tuple, period: str = "1y",
                  regime: str | None = None, srs: float | None = None) -> list[dict]:
    """For each ticker: fetch data, compute prediction + quant score.

    Passes the live regime + systemic-risk score into the prediction engine so
    weighting and conviction are calibrated to the current environment, and
    fuses the quant factor + per-ticker sentiment + realized vol into each call.

    Returns list of dicts with all signals merged.
    """
    import numpy as np
    import yfinance as yf

    try:
        from shared.finnhub_client import (is_available, basic_financials_sync,
                                            recommendations_sync, quote_sync,
                                            normalize_quote)
        finnhub_ready = is_available()
    except ImportError:
        finnhub_ready = False
        basic_financials_sync = recommendations_sync = quote_sync = None

    # Batch-load per-ticker sentiment once (not per-iteration) so the collected
    # news sentiment actually feeds the scanner instead of being thrown away.
    sent_map: dict = {}
    try:
        from _data import load_per_ticker_sentiment
        sent_map = load_per_ticker_sentiment(tuple(tickers)) or {}
    except Exception:
        sent_map = {}

    # Sector ETF momentum map — fetched once, reused across tickers
    sector_returns = _sector_returns_map()

    results = []
    for ticker in tickers:
        try:
            # Historical for momentum + technicals
            hist = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=True)
            if hist.empty or len(hist) < 50:
                continue

            closes = hist["Close"].tolist()
            arr    = np.array(closes)
            price  = float(arr[-1])

            sma_20  = float(arr[-20:].mean())  if len(arr) >= 20  else None
            sma_50  = float(arr[-50:].mean())  if len(arr) >= 50  else None
            sma_200 = float(arr[-200:].mean()) if len(arr) >= 200 else None

            # RSI 14
            deltas = np.diff(arr[-15:])
            ups = deltas[deltas > 0].sum() if any(deltas > 0) else 0
            downs = -deltas[deltas < 0].sum() if any(deltas < 0) else 1e-9
            rs = ups / downs if downs else 0
            rsi_14 = 100 - 100 / (1 + rs) if rs else 50

            # Multi-period returns (momentum factor)
            ret_3m  = (arr[-1] / arr[-63] - 1) * 100  if len(arr) >= 63  else None
            ret_6m  = (arr[-1] / arr[-126] - 1) * 100 if len(arr) >= 126 else None
            ret_12m = (arr[-1] / arr[-252] - 1) * 100 if len(arr) >= 252 else (arr[-1] / arr[0] - 1) * 100

            # Finnhub fundamentals + analyst data
            fin = basic_financials_sync(ticker) if finnhub_ready else {}
            recs = recommendations_sync(ticker) if finnhub_ready else []

            # Build enriched technical signal (uses MACD + BB + ADX + VWAP)
            highs   = hist["High"].values
            lows    = hist["Low"].values
            volumes = hist["Volume"].values
            advanced = compute_all_technicals(highs, lows, arr, volumes)

            tech_sig = technical_signal(price, sma_20, sma_50, sma_200, rsi_14,
                                         advanced=advanced)
            # Real per-ticker news sentiment (was previously fed an empty dict)
            sent_sig = sentiment_signal(sent_map.get(ticker, {}))
            anal_sig = analyst_signal(recs)
            # Sector confirmation signal
            meta_sector = TICKER_META.get(ticker, {}).get("sector", "")
            sect_sig = sector_signal(meta_sector, sector_returns)

            # Realized annualized volatility from the last ~3mo of daily log
            # returns — feeds the engine's volatility-targeting step.
            realized_vol_annual = None
            if len(arr) >= 21:
                logret = np.diff(np.log(arr[-63:])) if len(arr) >= 63 else np.diff(np.log(arr))
                if logret.size > 1:
                    realized_vol_annual = float(np.std(logret, ddof=1) * np.sqrt(252) * 100)

            # Quant factor score — computed BEFORE the prediction so its quality
            # tilt can be fused into the directional call.
            target_upside = None
            if fin and fin.get("priceTargetMean") and fin.get("priceTargetMean") > 0:
                target_upside = (fin["priceTargetMean"] / price - 1) * 100

            quant = compute_quant_score(
                fundamentals=fin,
                momentum_data={"ret_3m": ret_3m, "ret_6m": ret_6m, "ret_12m": ret_12m},
                analyst_data={
                    "eps_revisions_up":   None,
                    "eps_revisions_down": None,
                    "target_upside_pct":  target_upside,
                },
            )

            prediction = composite_prediction(
                tech_sig, sent_sig, anal_sig,
                vol={},                              # realized vol passed directly below
                sector=sect_sig,
                quant=quant,
                regime=regime,
                srs=srs,
                realized_vol_annual=realized_vol_annual,
            )

            chg_1d = (arr[-1] / arr[-2] - 1) * 100 if len(arr) >= 2 else 0
            meta = TICKER_META.get(ticker, {})

            results.append({
                "ticker":      ticker,
                "name":        meta.get("name", ticker),
                "sector":      meta.get("sector", "—"),
                "price":       round(price, 2),
                "chg_1d":      round(chg_1d, 2),
                "ret_3m":      round(ret_3m, 2)  if ret_3m  is not None else None,
                "ret_6m":      round(ret_6m, 2)  if ret_6m  is not None else None,
                "ret_12m":     round(ret_12m, 2) if ret_12m is not None else None,
                "rsi_14":      round(rsi_14, 1),
                "vs_sma_50":   round((price / sma_50  - 1) * 100, 2) if sma_50  else None,
                "vs_sma_200":  round((price / sma_200 - 1) * 100, 2) if sma_200 else None,
                "direction":   prediction["direction"],
                "confidence":  prediction["confidence"],
                "rationale":   prediction["rationale"],
                "components":  prediction["components"],
                "quant_score": quant["composite_score"],
                "quant_grade": quant["composite_grade"],
                "factors":     quant["factors"],
            })
        except Exception:
            continue
    return results


def main():
    col_t, col_r = st.columns([6, 1])
    with col_t:
        st.title("🎯 Opportunity Scanner")
        st.caption("Multi-factor screen across the watchlist · ranked by confidence × "
                   "quant grade. Backtest-inspired Seeking Alpha-style model.")
    with col_r:
        st.write("")
        if st.button("🔄 Refresh", use_container_width=True,
                     help="Clears cache and re-scans (takes ~30 sec)"):
            scan_universe.clear()
            st.rerun()

    # Filter controls
    col_uni, col_conf, col_dir = st.columns([2, 1, 1])
    with col_uni:
        preset = st.selectbox(
            "Universe preset",
            list(UNIVERSE_PRESETS.keys()),
            index=0,
            help="Pick a starting set spanning the sectors you care about, "
                 "then add or remove individual names below.",
        )
        # key includes preset → multiselect re-seeds with the new default on switch
        universe = st.multiselect(
            "Scan universe — spans all 11 GICS sectors so no segment is missed",
            _ALL_TICKERS,
            default=UNIVERSE_PRESETS[preset],
            max_selections=120,
            key=f"uni_{preset}",
        )
    with col_conf:
        min_confidence = st.slider("Min confidence %", 0, 100, 40, step=5,
                                    help="Only surface setups with composite confidence ≥ this")
    with col_dir:
        direction_filter = st.selectbox("Direction", ["All", "Bullish", "Bearish"])

    # Sector-coverage readout — flag any GICS sector the selection misses
    if universe:
        sel = set(universe)
        covered = [s for s, names in UNIVERSE_BY_SECTOR.items() if sel & set(names)]
        missing = [s for s, names in UNIVERSE_BY_SECTOR.items() if not (sel & set(names))]
        cov_html = (
            f'<span style="color:#8b93a7;font-size:11px">Scanning '
            f'<b style="color:#e6e9f0">{len(universe)}</b> names · '
            f'<b style="color:#00d68f">{len(covered)}/{len(UNIVERSE_BY_SECTOR)}</b> '
            f'sectors covered'
        )
        if missing:
            cov_html += (f' · <span style="color:#ffaa00">no exposure to: '
                         f'{", ".join(missing)}</span>')
        cov_html += "</span>"
        st.markdown(cov_html, unsafe_allow_html=True)

    # Optional: filter by sector
    with st.expander("⚙ Advanced filters"):
        col_q, col_rsi, col_t1 = st.columns(3)
        with col_q:
            min_quant = st.slider("Min Quant Score", 0, 100, 0, step=10,
                                   help="0-100. A+ ≥ 95, A ≥ 85, B+ ≥ 75")
        with col_rsi:
            rsi_filter = st.selectbox("RSI filter", ["Any", "Oversold (<30)",
                                                       "Bullish momentum (50-70)",
                                                       "Overbought (>70)"])
        with col_t1:
            trend_filter = st.selectbox("Trend filter", ["Any",
                                                          "Above SMA 50",
                                                          "Above SMA 200",
                                                          "Golden Cross (50>200)"])

    if not universe:
        st.warning("Select at least one ticker.")
        return

    # ── Prefer pre-computed snapshot from pipeline cron ─────────────────────
    snapshot_results, scanned_at = load_latest_snapshot()
    use_snapshot = bool(snapshot_results)

    # Mode toggle
    col_mode, col_freshness = st.columns([1, 3])
    with col_mode:
        force_live = st.toggle(
            "🔄 Force live scan",
            value=False,
            help="Off (default) = read pipeline-computed snapshot (instant). "
                 "On = run scanner now (30+ seconds, hits yfinance)",
        )
    with col_freshness:
        if use_snapshot and not force_live and scanned_at:
            from datetime import datetime, timezone
            try:
                ts = datetime.fromisoformat(scanned_at.replace("Z", "+00:00"))
                age_min = (datetime.now(timezone.utc) - ts).total_seconds() / 60
                st.caption(f"📊 Showing **pipeline snapshot** · scanned "
                           f"{int(age_min)} min ago · "
                           f"{len(snapshot_results)} tickers")
            except Exception:
                st.caption(f"📊 Pipeline snapshot · {len(snapshot_results)} tickers")
        elif force_live:
            st.caption("⚡ Running **live scan** (~30 sec)…")
        else:
            st.caption("⚠ No snapshot yet — pipeline hasn't run with migration 011 applied. "
                       "Running live scan as fallback.")

    # Current market environment — fed INTO the scanner so the prediction engine
    # uses regime-conditional weights + a systemic-risk conviction haircut.
    try:
        from _data import load_regime_risk
        regime_dict, risk_dict, _, _ = load_regime_risk()
        current_regime = regime_dict.get("regime") if regime_dict else None
        current_srs    = risk_dict.get("srs") if risk_dict else None
    except Exception:
        current_regime = current_srs = None

    if use_snapshot and not force_live:
        results = snapshot_results
    else:
        with st.spinner(f"Scanning {len(universe)} tickers — multi-factor analysis…"):
            results = scan_universe(tuple(universe), regime=current_regime, srs=current_srs)

    # Log predictions for backtest tracking + self-improvement
    try:
        from shared.prediction_tracker import log_prediction

        logged = 0
        for r in results:
            if r["confidence"] >= 50 and r["direction"] != "neutral":
                meta_sector = TICKER_META.get(r["ticker"], {}).get("sector")
                ok = log_prediction(
                    ticker=r["ticker"],
                    direction=r["direction"],
                    confidence_pct=r["confidence"],
                    price=r["price"],
                    source_page="opportunities",
                    components=r.get("components"),
                    quant_score=r.get("quant_score"),
                    quant_grade=r.get("quant_grade"),
                    regime_at_pred=current_regime,
                    srs_at_pred=current_srs,
                    sector=meta_sector,
                )
                if ok:
                    logged += 1
        if logged:
            st.caption(f"📝 Logged {logged} predictions for backtest "
                       "(see Track Record → Model Evolution).")
    except Exception:
        pass

    if not results:
        st.error("Scan returned no usable data. Try Refresh or fewer tickers.")
        return

    # Apply filters
    filtered = [r for r in results if r["confidence"] >= min_confidence]
    if direction_filter == "Bullish":
        filtered = [r for r in filtered if r["direction"] == "bullish"]
    elif direction_filter == "Bearish":
        filtered = [r for r in filtered if r["direction"] == "bearish"]
    if min_quant > 0:
        filtered = [r for r in filtered if r["quant_score"] >= min_quant]
    if rsi_filter == "Oversold (<30)":
        filtered = [r for r in filtered if r["rsi_14"] < 30]
    elif rsi_filter == "Bullish momentum (50-70)":
        filtered = [r for r in filtered if 50 <= r["rsi_14"] <= 70]
    elif rsi_filter == "Overbought (>70)":
        filtered = [r for r in filtered if r["rsi_14"] > 70]
    if trend_filter == "Above SMA 50":
        filtered = [r for r in filtered if (r.get("vs_sma_50") or 0) > 0]
    elif trend_filter == "Above SMA 200":
        filtered = [r for r in filtered if (r.get("vs_sma_200") or 0) > 0]
    elif trend_filter == "Golden Cross (50>200)":
        filtered = [
            r for r in filtered
            if r.get("vs_sma_50") is not None and r.get("vs_sma_200") is not None
            and r["vs_sma_50"] > r["vs_sma_200"]
        ]

    st.divider()

    # Summary KPIs
    bull_count = sum(1 for r in filtered if r["direction"] == "bullish")
    bear_count = sum(1 for r in filtered if r["direction"] == "bearish")
    avg_conf   = sum(r["confidence"] for r in filtered) / len(filtered) if filtered else 0
    avg_quant  = sum(r["quant_score"] for r in filtered) / len(filtered) if filtered else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Setups matching", len(filtered),
              delta=f"of {len(results)} scanned")
    c2.metric("Bullish", bull_count, delta=f"{bull_count/max(len(filtered),1)*100:.0f}%",
              delta_color="off")
    c3.metric("Bearish", bear_count, delta=f"{bear_count/max(len(filtered),1)*100:.0f}%",
              delta_color="off")
    c4.metric("Avg quant", f"{avg_quant:.0f}", delta=f"Avg conf {avg_conf:.0f}%",
              delta_color="off")

    st.divider()

    # Tabs: Top Bullish | Top Bearish | All | Quant Leaders
    tab_bull, tab_bear, tab_quant, tab_all = st.tabs([
        "🚀 Top Bullish", "📉 Top Bearish", "🏆 Quant Leaders", "📋 All Setups"
    ])

    with tab_bull:
        bull = sorted([r for r in filtered if r["direction"] == "bullish"],
                      key=lambda r: (r["confidence"] * 0.6 + r["quant_score"] * 0.4),
                      reverse=True)
        _render_opportunity_list(bull[:15], emphasis="bullish")

    with tab_bear:
        bear = sorted([r for r in filtered if r["direction"] == "bearish"],
                      key=lambda r: (r["confidence"] * 0.6 + r["quant_score"] * 0.4),
                      reverse=True)
        _render_opportunity_list(bear[:15], emphasis="bearish")

    with tab_quant:
        # Top by quant score regardless of direction
        quant_sorted = sorted(filtered, key=lambda r: r["quant_score"], reverse=True)
        st.caption("Highest-quality fundamentals (Seeking Alpha-style: Value + Growth + "
                   "Profitability + Momentum + Revisions). Direction-agnostic.")
        _render_opportunity_list(quant_sorted[:15], emphasis="quant")

    with tab_all:
        _render_full_table(filtered)


def _render_opportunity_list(opportunities: list[dict], emphasis: str = "bullish"):
    """Render ranked list with rationale + signal breakdown per row."""
    if not opportunities:
        st.info("No setups match the current filters. Lower the confidence threshold "
                "or widen the universe.")
        return

    for r in opportunities:
        dir_color = ("#00d68f" if r["direction"] == "bullish"
                     else "#ff5773" if r["direction"] == "bearish"
                     else "#ffaa00")
        grade_color = ("#00d68f" if r["quant_grade"] in ("A+", "A")
                       else "#ffaa00" if r["quant_grade"] in ("B+", "B")
                       else "#ff8800" if r["quant_grade"] in ("C+", "C")
                       else "#ff5773")
        meta = TICKER_META.get(r["ticker"], {})
        sector = meta.get("sector") or r.get("sector") or "—"

        with st.expander(
            f"**{r['ticker']}** · {meta.get('name', r['ticker'])} · "
            f"{r['direction'].upper()} · {r['confidence']:.0f}% conf · "
            f"Quant {r['quant_grade']}",
            expanded=False,
        ):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Price", f"${r['price']:,.2f}",
                      delta=f"{r['chg_1d']:+.2f}% today")
            c2.metric("Direction", r["direction"].upper(),
                      delta=f"{r['confidence']:.0f}% conf", delta_color="off")
            c3.metric("Quant", f"{r['quant_grade']}",
                      delta=f"{r['quant_score']:.0f}/100", delta_color="off")
            c4.metric("Sector", sector, delta_color="off")

            st.markdown(f"**Rationale:** {r['rationale']}")

            # Factor grades
            f = r["factors"]
            st.markdown("**Quant factor grades**")
            cc1, cc2, cc3, cc4, cc5 = st.columns(5)
            cc1.metric("Value",     f["value"]["grade"],
                       delta=f"{f['value']['score']:.0f}", delta_color="off")
            cc2.metric("Growth",    f["growth"]["grade"],
                       delta=f"{f['growth']['score']:.0f}", delta_color="off")
            cc3.metric("Profit",    f["profit"]["grade"],
                       delta=f"{f['profit']['score']:.0f}", delta_color="off")
            cc4.metric("Momentum",  f["momentum"]["grade"],
                       delta=f"{f['momentum']['score']:.0f}", delta_color="off")
            cc5.metric("Revisions", f["revisions"]["grade"],
                       delta=f"{f['revisions']['score']:.0f}", delta_color="off")

            # Returns
            tt1, tt2, tt3 = st.columns(3)
            tt1.metric("3M return", f"{r.get('ret_3m', 0):+.1f}%" if r.get("ret_3m") is not None else "—")
            tt2.metric("6M return", f"{r.get('ret_6m', 0):+.1f}%" if r.get("ret_6m") is not None else "—")
            tt3.metric("12M return", f"{r.get('ret_12m', 0):+.1f}%" if r.get("ret_12m") is not None else "—")

            if st.button(f"🔍 Open {r['ticker']} in Stock Detail",
                         key=f"detail_{emphasis}_{r['ticker']}", use_container_width=True):
                st.session_state["detail_ticker"] = r["ticker"]
                st.switch_page("pages/5_Stock_Detail.py")


def _render_full_table(opportunities: list[dict]):
    """Compact sortable table view."""
    import pandas as pd
    if not opportunities:
        st.info("No setups match the current filters.")
        return
    rows = []
    for r in opportunities:
        rows.append({
            "Ticker":      r["ticker"],
            "Name":        TICKER_META.get(r["ticker"], {}).get("name", r["ticker"])[:30],
            "Direction":   r["direction"].upper(),
            "Confidence":  r["confidence"],
            "Quant Grade": r["quant_grade"],
            "Quant":       r["quant_score"],
            "Price":       r["price"],
            "1D %":        r["chg_1d"],
            "3M %":        r.get("ret_3m"),
            "6M %":        r.get("ret_6m"),
            "RSI":         r["rsi_14"],
        })
    df = pd.DataFrame(rows).set_index("Ticker")
    st.dataframe(
        df,
        use_container_width=True,
        column_config={
            "Confidence": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
            "Quant":      st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100),
            "Price":      st.column_config.NumberColumn(format="$%.2f"),
            "1D %":       st.column_config.NumberColumn(format="%+.2f%%"),
            "3M %":       st.column_config.NumberColumn(format="%+.1f%%"),
            "6M %":       st.column_config.NumberColumn(format="%+.1f%%"),
            "RSI":        st.column_config.NumberColumn(format="%.0f"),
        },
        height=min(len(rows) * 36 + 40, 600),
    )


main()
