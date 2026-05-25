"""
INTL — Intelligence Terminal · Overview Page
Bloomberg/Aladdin-inspired professional trading dashboard.

Design principles applied:
  - Bloomberg: information density, tile-based layout, predictability
  - Aladdin: regime + risk side-by-side, factor breakdown
  - TradingView: IBM Plex Mono for numbers, Inter for UI, dark navy (not black)
  - LSEG Workspace: customizable tile grid, AI-powered widgets
"""
import os
import sys
from pathlib import Path

# ── Path setup — make BOTH repo-root and projects/daily_digest importable ──
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
from _theme import apply_theme, COLORS, REGIME_COLORS, status_pill
from _data  import (load_articles, load_signals, load_market_snapshots,
                    load_regime_risk, load_market_prices, supabase_client,
                    check_setup_status)
apply_theme()


# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR — regime card, risk gauge, navigation
# ════════════════════════════════════════════════════════════════════════════

def render_sidebar(regime: dict, risk: dict, source: str) -> None:
    with st.sidebar:
        st.markdown("### 📊 INTL Terminal")
        st.caption("v2.2 · Aladdin-inspired platform")

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

    # ── KPI strip — Bloomberg-style tile row ──────────────────────────────────
    articles, art_status = load_articles(limit=200)
    signals,  sig_status = load_signals(limit=50)
    market,   mkt_status = load_market_snapshots(limit=60)

    # Sentiment aggregation (defensive)
    bull = sum(1 for a in articles if a.get("sentiment_label") == "bullish")
    bear = sum(1 for a in articles if a.get("sentiment_label") == "bearish")
    total = max(len(articles), 1)
    bull_pct = round(bull / total * 100)
    bear_pct = round(bear / total * 100)

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        r_label = regime.get("label", "—") if regime else "—"
        r_color = REGIME_COLORS.get(regime.get("regime", ""), "#888") if regime else "#888"
        st.markdown(f"""
        <div class="stMetric">
          <div style="font-size:10px;color:#8b93a7;text-transform:uppercase;letter-spacing:.12em;font-weight:600;margin-bottom:6px">Market Regime</div>
          <div style="font-size:18px;font-weight:600;color:{r_color}">{r_label}</div>
          <div style="font-size:11px;color:#8b93a7;margin-top:4px;font-family:'IBM Plex Mono',monospace">
            {regime.get("confidence_pct", 0):.0f}% conf
          </div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        srs   = risk.get("srs", 0) if risk else 0
        level = risk.get("level", "—") if risk else "—"
        c = "#00d68f" if srs < 26 else "#ffaa00" if srs < 51 else "#ff8800" if srs < 76 else "#ff5773"
        st.markdown(f"""
        <div class="stMetric">
          <div style="font-size:10px;color:#8b93a7;text-transform:uppercase;letter-spacing:.12em;font-weight:600;margin-bottom:6px">Systemic Risk</div>
          <div style="font-size:22px;font-weight:600;color:{c};font-family:'IBM Plex Mono',monospace">{srs:.0f}<span style="font-size:11px;color:#8b93a7;font-weight:400">/100</span></div>
          <div style="font-size:11px;color:{c};margin-top:4px">{level}</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="stMetric">
          <div style="font-size:10px;color:#8b93a7;text-transform:uppercase;letter-spacing:.12em;font-weight:600;margin-bottom:6px">News Sentiment</div>
          <div style="display:flex;gap:10px;align-items:baseline">
            <span style="font-size:18px;font-weight:600;color:#00d68f;font-family:'IBM Plex Mono',monospace">↑{bull_pct}%</span>
            <span style="font-size:18px;font-weight:600;color:#ff5773;font-family:'IBM Plex Mono',monospace">↓{bear_pct}%</span>
          </div>
          <div style="font-size:11px;color:#8b93a7;margin-top:4px;font-family:'IBM Plex Mono',monospace">{len(articles)} articles</div>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        st.markdown(f"""
        <div class="stMetric">
          <div style="font-size:10px;color:#8b93a7;text-transform:uppercase;letter-spacing:.12em;font-weight:600;margin-bottom:6px">Alpha Signals</div>
          <div style="font-size:22px;font-weight:600;color:#e6e9f0;font-family:'IBM Plex Mono',monospace">{len(signals)}</div>
          <div style="font-size:11px;color:#8b93a7;margin-top:4px">insider · options · congress</div>
        </div>
        """, unsafe_allow_html=True)
    with col5:
        st.markdown(f"""
        <div class="stMetric">
          <div style="font-size:10px;color:#8b93a7;text-transform:uppercase;letter-spacing:.12em;font-weight:600;margin-bottom:6px">Market Tickers</div>
          <div style="font-size:22px;font-weight:600;color:#e6e9f0;font-family:'IBM Plex Mono',monospace">{len(market)}</div>
          <div style="font-size:11px;color:#8b93a7;margin-top:4px">FRED + Yahoo Finance</div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # ── Live Markets — 4×4 grid with full price visibility ───────────────────
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
        mkt_items = list(mkt.items())
        for row_start in range(0, len(mkt_items), 4):
            row_items = mkt_items[row_start:row_start + 4]
            cols = st.columns(4)
            for col, (ticker, d) in zip(cols, row_items):
                with col:
                    delta_color = "normal" if d["change_pct"] >= 0 else "inverse"
                    st.metric(
                        label=ticker,
                        value=f"${d['price']:,.2f}",
                        delta=f"{d['change_pct']:+.2f}%",
                        delta_color=delta_color,
                    )
    else:
        st.warning("Market data unavailable — yfinance may be rate-limited. Try Refresh.")

    st.divider()

    # ── Regime details (when available) ──────────────────────────────────────
    if regime:
        with st.expander("🌐 Market Regime Analysis", expanded=True):
            c1, c2 = st.columns([1, 2])
            with c1:
                r_color = REGIME_COLORS.get(regime.get("regime", ""), "#888")
                st.markdown(f"""
                <div style="font-size:20px;font-weight:600;color:{r_color}">{regime.get('label', '—')}</div>
                <div style="color:#8b93a7;margin-top:8px;line-height:1.5">{regime.get('description', '—')}</div>
                """, unsafe_allow_html=True)
                st.metric("Confidence",      f"{regime.get('confidence_pct', 0):.0f}%")
                st.metric("Transition Risk", regime.get("transition_risk", "—").upper())
            with c2:
                if regime.get("favors"):
                    st.markdown("**↑ Favors:**  " + " · ".join(regime["favors"]))
                if regime.get("avoids"):
                    st.markdown("**↓ Avoids:**  " + " · ".join(regime["avoids"]))
                g = regime.get("growth_score", 0)
                i = regime.get("inflation_score", 0)
                st.progress(min(max((g + 1) / 2, 0), 1), text=f"Growth axis: {g:+.3f}")
                st.progress(min(max((i + 1) / 2, 0), 1), text=f"Inflation axis: {i:+.3f}")

    st.divider()

    # ── News feed + Signals side panel ────────────────────────────────────────
    if articles:
        col_news, col_side = st.columns([3, 2])

        with col_news:
            with st.expander(f"📰 Top Intelligence Feed · {len(articles)} items", expanded=True):
                for it in articles[:25]:
                    sent = it.get("sentiment_label") or "neutral"
                    sentiment_icon = "▲" if sent == "bullish" else "▼" if sent == "bearish" else "·"
                    sent_color = "#00d68f" if sent == "bullish" else "#ff5773" if sent == "bearish" else "#8b93a7"
                    src = (it.get("source") or "?").upper()[:4]
                    title = (it.get("title") or "—")[:90]
                    url   = it.get("url") or "#"
                    score = it.get("terminal_score") or 0
                    st.markdown(
                        f"<span style='color:{sent_color};font-weight:600'>{sentiment_icon}</span> "
                        f"<code>{src}</code> [{title}]({url}) "
                        f"<span style='color:#5a6378;font-size:11px;font-family:IBM Plex Mono,monospace'>{score:.0f}pts</span>",
                        unsafe_allow_html=True,
                    )
                    if it.get("preview"):
                        st.caption(it["preview"][:160])

        with col_side:
            # Signals panel
            if signals:
                with st.expander(f"⚡ Alpha Signals · {len(signals)}", expanded=True):
                    label_map = {"edgar": "SEC", "options": "OPTS", "congress": "CONG", "finra": "SHORT"}
                    for sig in signals[:12]:
                        s_label = label_map.get(sig.get("source"), (sig.get("source") or "?").upper()[:5])
                        s_sent  = sig.get("sentiment_label") or "neutral"
                        s_icon  = "▲" if s_sent == "bullish" else "▼" if s_sent == "bearish" else "—"
                        s_color = "#00d68f" if s_sent == "bullish" else "#ff5773" if s_sent == "bearish" else "#8b93a7"
                        st.markdown(
                            f"<span style='color:{s_color}'>{s_icon}</span> "
                            f"<code>{s_label}</code> {(sig.get('title') or '—')[:48]}",
                            unsafe_allow_html=True,
                        )
            elif sig_status == "missing":
                with st.expander("⚡ Alpha Signals", expanded=True):
                    st.caption("Signals table missing — run migration 002")
            else:
                with st.expander("⚡ Alpha Signals · Pending", expanded=True):
                    st.markdown("**No signals yet.**")
                    st.caption("Trigger pipeline to populate insider/options/congress data.")
                    st.link_button(
                        "🚀 Run pipeline",
                        "https://github.com/git0ST/automation/actions/workflows/digest.yml",
                        use_container_width=True,
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
