"""INTL Intelligence Terminal — Overview page."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "projects" / "daily_digest"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import streamlit as st

# ── Page config MUST be first Streamlit call ──────────────────────────────────
st.set_page_config(
    page_title="INTL — Intelligence Terminal",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help":    "https://github.com/git0ST/automation",
        "Report a bug":"https://github.com/git0ST/automation/issues",
        "About":       "INTL v2.2 — Aladdin-inspired intelligence platform",
    },
)

# ── Apply unified theme ───────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _theme      import apply_theme, COLORS, REGIME_COLORS, status_pill, KPI_HELP
from _data       import (load_articles, load_signals, load_market_snapshots,
                         load_regime_risk, load_market_prices, supabase_client,
                         check_setup_status, load_weighted_sentiment)
from _components import (ticker_card, render_ticker_grid, news_item_card,
                         source_badge, regime_card, TICKER_META)
apply_theme()


# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR — regime card, risk gauge, navigation
# ════════════════════════════════════════════════════════════════════════════

def render_sidebar(regime: dict, risk: dict, source: str) -> None:
    with st.sidebar:
        # Header with explicit collapse hint
        col_title, col_close = st.columns([5, 1])
        with col_title:
            st.markdown("### 📊 INTL Terminal")
            st.caption("v2.3 · Aladdin-inspired platform")
        with col_close:
            st.markdown(
                '<div style="text-align:right;color:#5a6378;font-size:11px;margin-top:8px" '
                'title="Use the « icon at the top to collapse the sidebar">«</div>',
                unsafe_allow_html=True,
            )

        # Data freshness pill
        if source == "supabase":
            st.markdown(status_pill("● LIVE · Supabase", "live"), unsafe_allow_html=True)
        elif source == "live_fred":
            st.markdown(status_pill("● LIVE · FRED fallback", "stale"), unsafe_allow_html=True)
        else:
            st.markdown(status_pill("○ No data", "error"), unsafe_allow_html=True)

        st.divider()

        # Regime card
        if regime:
            r_label = regime.get("label", "—")
            r_color = REGIME_COLORS.get(regime.get("regime", ""), "#888")
            r_conf  = regime.get("confidence_pct", 0)
            t_risk  = regime.get("transition_risk", "—")
            st.markdown(f"""
            <div class="sidebar-card">
              <div style="font-size:9px;color:#8b93a7;letter-spacing:.14em;text-transform:uppercase;margin-bottom:8px;font-weight:600">Market Regime</div>
              <div class="regime-badge" style="color:{r_color};background:{r_color}1a;border:1px solid {r_color}44">{r_label}</div>
              <div style="margin-top:10px;font-size:11px;color:#8b93a7">
                Confidence: <span style="color:#e6e9f0;font-family:'IBM Plex Mono',monospace">{r_conf:.0f}%</span>
              </div>
              <div style="font-size:11px;color:#8b93a7;margin-top:4px">
                Transition: <span style="color:#e6e9f0">{t_risk}</span>
              </div>
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="sidebar-card">
              <div style="font-size:9px;color:#8b93a7;letter-spacing:.14em;text-transform:uppercase">Regime</div>
              <div style="color:#5a6378;font-size:13px;margin-top:8px">No data yet</div>
            </div>""", unsafe_allow_html=True)

        # Risk gauge
        if risk:
            srs   = risk.get("srs", 0)
            level = risk.get("level", "—")
            c = "#00d68f" if srs < 26 else "#ffaa00" if srs < 51 else "#ff8800" if srs < 76 else "#ff5773"
            st.markdown(f"""
            <div class="sidebar-card">
              <div style="font-size:9px;color:#8b93a7;letter-spacing:.14em;text-transform:uppercase;font-weight:600">Systemic Risk Score</div>
              <div style="display:flex;align-items:baseline;gap:8px;margin-top:8px">
                <span style="font-size:28px;font-weight:700;color:{c};font-family:'IBM Plex Mono',monospace">{srs:.0f}</span>
                <span style="font-size:11px;color:#8b93a7">/ 100 · <span style="color:{c}">{level}</span></span>
              </div>
              <div class="srs-bar-container" style="margin-top:8px">
                <div class="srs-bar" style="width:{srs}%;background:{c}"></div>
              </div>
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="sidebar-card">
              <div style="font-size:9px;color:#8b93a7;letter-spacing:.14em;text-transform:uppercase">Systemic Risk</div>
              <div style="color:#5a6378;font-size:13px;margin-top:8px">No data yet</div>
            </div>""", unsafe_allow_html=True)

        st.divider()
        st.markdown("**Navigation**")
        st.page_link("app.py",                label="🏠 Overview")
        st.page_link("pages/1_Markets.py",    label="📈 Markets")
        st.page_link("pages/2_Risk.py",       label="🎯 Risk & VaR")
        st.page_link("pages/3_Research.py",   label="🔬 AI Research")
        st.page_link("pages/4_Portfolio.py",  label="💼 Portfolio")
        st.divider()

        # Pipeline trigger CTA
        with st.expander("⚙️ Pipeline Status"):
            try:
                status = check_setup_status()
                if status.get("supabase_connected"):
                    has_data = status.get("has_pipeline_data", False)
                    if has_data:
                        rows = status["tables"]["articles"]["rows"]
                        st.markdown(f"✅ **{rows}** articles · Pipeline active")
                    else:
                        st.markdown("⚠️ **No pipeline data yet**")
                        st.link_button(
                            "🚀 Trigger pipeline cron",
                            "https://github.com/git0ST/automation/actions/workflows/digest.yml",
                            use_container_width=True,
                        )
                else:
                    st.markdown("❌ Supabase not connected")
            except Exception:
                st.caption("Status check failed")

        st.caption("Data: Yahoo Finance · FRED · ICE BofA · Groq AI")


# ════════════════════════════════════════════════════════════════════════════
# OVERVIEW PAGE
# ════════════════════════════════════════════════════════════════════════════

def main():
    # Load all data with graceful fallbacks
    regime, risk, missing_tables, source = load_regime_risk()
    render_sidebar(regime, risk, source)

    # ── Header bar ────────────────────────────────────────────────────────────
    col_title, col_status, col_refresh = st.columns([5, 2, 1])
    with col_title:
        st.title("Intelligence Terminal")
        st.caption("Real-time market intelligence · Regime detection · Risk scoring")
    with col_status:
        st.write("")
        st.write("")
        if source == "supabase":
            st.markdown(status_pill("● LIVE", "live"), unsafe_allow_html=True)
        elif source == "live_fred":
            st.markdown(status_pill("● LIVE FRED", "stale"), unsafe_allow_html=True)
        else:
            st.markdown(status_pill("○ NO DATA", "error"), unsafe_allow_html=True)
    with col_refresh:
        st.write("")
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # ── Setup warning if migrations missing ───────────────────────────────────
    if missing_tables:
        st.warning(
            f"⚠ **Database setup needed:** Tables `{', '.join(missing_tables)}` don't exist. "
            "Run [migration 003](https://github.com/git0ST/automation/blob/main/supabase/migrations/003_intelligence_tables.sql) "
            "in the [Supabase SQL Editor](https://supabase.com/dashboard/project/jptwbvigtgiffjqnctic/sql/new).",
            icon="⚠️",
        )

    st.divider()

    # KPI strip — tooltips explain each metric on hover
    articles, art_status = load_articles(limit=200)
    signals,  sig_status = load_signals(limit=50)
    market,   mkt_status = load_market_snapshots(limit=60)
    sentiment            = load_weighted_sentiment(limit=200)

    bull_pct = sentiment.get("bullish_pct", 0)
    bear_pct = sentiment.get("bearish_pct", 0)
    srs      = risk.get("srs", 0) if risk else 0
    level    = risk.get("level", "—") if risk else "—"

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric(
            label="Market Regime",
            value=(regime.get("label") if regime else "—"),
            delta=f"{regime.get('confidence_pct', 0):.0f}% confidence" if regime else "no data",
            delta_color="off",
            help=KPI_HELP["market_regime"],
        )
    with col2:
        st.metric(
            label="Systemic Risk",
            value=f"{srs:.0f} / 100",
            delta=level,
            delta_color="inverse" if srs >= 51 else "normal",
            help=KPI_HELP["systemic_risk"],
        )
    with col3:
        st.metric(
            label="News Sentiment",
            value=f"↑ {bull_pct}% / ↓ {bear_pct}%",
            delta=f"{sentiment.get('n_items', 0)} articles · weighted",
            delta_color="off",
            help=KPI_HELP["news_sentiment"],
        )
    with col4:
        st.metric(
            label="Alpha Signals",
            value=len(signals),
            delta="insider · options · congress",
            delta_color="off",
            help=KPI_HELP["alpha_signals"],
        )
    with col5:
        st.metric(
            label="Market Tickers",
            value=len(market),
            delta="FRED + Yahoo Finance",
            delta_color="off",
            help=KPI_HELP["market_tickers"],
        )

    st.divider()

    # ── Live Markets — professional ticker cards with logos ─────────────────
    st.markdown("#### 📈 Live Markets")
    WATCHLIST = (
        "^GSPC", "^IXIC", "^DJI",  "^VIX",
        "NVDA",  "AAPL",  "MSFT",  "GOOGL",
        "META",  "AMZN",  "TSLA",  "AVGO",
        "BTC-USD","ETH-USD","SPY","QQQ",
    )
    with st.spinner(f"Loading {len(WATCHLIST)} tickers…"):
        mkt = load_market_prices(WATCHLIST)

    if mkt:
        render_ticker_grid(mkt, cols=4)
    else:
        st.warning("Market data unavailable — yfinance may be rate-limited. Try Refresh.")

    st.divider()

    # ── Regime card — professional, comprehensive ────────────────────────────
    if regime:
        st.markdown("#### 🌐 Market Regime")
        st.markdown(regime_card(regime), unsafe_allow_html=True)

    st.divider()

    # ── News feed + Signals side panel ───────────────────────────────────────
    if articles:
        col_news, col_side = st.columns([3, 2])

        with col_news:
            st.markdown(f"#### 📰 Top Intelligence Feed · {len(articles)} items")
            for it in articles[:20]:
                st.markdown(news_item_card(it), unsafe_allow_html=True)

        with col_side:
            # Signals panel
            if signals:
                st.markdown(f"#### ⚡ Alpha Signals · {len(signals)}")
                label_map = {"edgar": "SEC", "options": "OPTS", "congress": "CONG",
                             "finra": "SHORT", "credit": "CREDIT"}
                for sig in signals[:15]:
                    s_sent  = sig.get("sentiment_label") or "neutral"
                    s_icon  = "▲" if s_sent == "bullish" else "▼" if s_sent == "bearish" else "—"
                    s_color = "#00d68f" if s_sent == "bullish" else "#ff5773" if s_sent == "bearish" else "#8b93a7"
                    src_html = source_badge(sig.get("source") or "?")
                    title    = (sig.get("title") or "—")[:60]
                    st.markdown(
                        f'<div style="background:#131825;border:1px solid #1f2937;'
                        f'border-radius:5px;padding:8px 12px;margin-bottom:6px">'
                        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">'
                        f'<span style="color:{s_color};font-weight:700">{s_icon}</span>'
                        f'{src_html}'
                        f'</div>'
                        f'<div style="color:#c8cce0;font-size:12px;line-height:1.4">{title}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            elif sig_status == "missing":
                st.markdown("#### ⚡ Alpha Signals")
                st.caption("Signals table missing — run migration 002")
            else:
                st.markdown("#### ⚡ Alpha Signals · Pending")
                st.info(
                    "**No signals yet.** Trigger the pipeline to populate "
                    "insider/options/congress data.",
                    icon="📭",
                )
                st.link_button(
                    "🚀 Run pipeline",
                    "https://github.com/git0ST/automation/actions/workflows/digest.yml",
                    use_container_width=True,
                    type="primary",
                )
    else:
        # Empty state — clear CTA
        st.info(
            "📭 **No news data yet.** This is normal on first deploy.\n\n"
            "**Next step:** trigger the pipeline cron at "
            "https://github.com/git0ST/automation/actions/workflows/digest.yml → "
            "click **Run workflow** → wait ~3-5 min → refresh this page."
        )


main()
