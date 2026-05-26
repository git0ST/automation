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
from _theme      import apply_theme, COLORS, REGIME_COLORS, status_pill
from _kpi_help   import (MARKET_REGIME, SYSTEMIC_RISK, NEWS_SENTIMENT,
                          ALPHA_SIGNALS, DATA_FRESHNESS)
from _data       import (load_articles, load_signals, load_market_snapshots,
                         load_regime_risk, load_market_prices, supabase_client,
                         check_setup_status, load_weighted_sentiment,
                         load_data_freshness)
from _components import (ticker_card, render_ticker_grid, news_item_card,
                         source_badge, regime_card, TICKER_META)
apply_theme()


# Sector ETF proxies — used to show "money flowing into X" rotation
SECTOR_ETFS = {
    "Technology":             ("XLK",  "Tech"),
    "Financials":             ("XLF",  "Fin"),
    "Energy":                 ("XLE",  "Energy"),
    "Healthcare":             ("XLV",  "Health"),
    "Consumer Discretionary": ("XLY",  "Cons Disc"),
    "Consumer Staples":       ("XLP",  "Cons Stap"),
    "Industrials":            ("XLI",  "Indust"),
    "Materials":              ("XLB",  "Materials"),
    "Real Estate":             ("XLRE", "Real Est"),
    "Utilities":              ("XLU",  "Util"),
    "Communication":          ("XLC",  "Comm"),
}


@st.cache_data(ttl=600, show_spinner=False)
def _sector_rotation_data() -> list[dict]:
    """Fetch 5-day returns for the 11 GICS sector SPDR ETFs."""
    try:
        import yfinance as yf
        rows = []
        for sector, (etf, short) in SECTOR_ETFS.items():
            try:
                hist = yf.Ticker(etf).history(period="10d", interval="1d", auto_adjust=True)
                if hist.empty or len(hist) < 5:
                    continue
                last = float(hist["Close"].iloc[-1])
                week_ago = float(hist["Close"].iloc[-5])
                ret_5d = (last / week_ago - 1) * 100
                # Use volume × price as a market-cap-ish size proxy
                size = float(hist["Volume"].iloc[-5:].mean()) * last
                rows.append({
                    "sector": sector,
                    "short":  short,
                    "etf":    etf,
                    "ret_5d": round(ret_5d, 2),
                    "price":  round(last, 2),
                    "size":   size,
                })
            except Exception:
                continue
        return rows
    except Exception:
        return []


def _render_sector_rotation():
    rows = _sector_rotation_data()
    if not rows:
        st.caption("Sector data unavailable — Yahoo Finance may be rate-limited.")
        return
    try:
        import plotly.express as px
        import pandas as pd
        df = pd.DataFrame(rows)
        fig = px.treemap(
            df,
            path=[px.Constant("Sectors"), "sector"],
            values="size",
            color="ret_5d",
            color_continuous_scale=[
                (0.0, "#7c1d1d"),
                (0.35, "#ff5773"),
                (0.5, "#1a2034"),
                (0.65, "#00d68f"),
                (1.0, "#0d5e2a"),
            ],
            color_continuous_midpoint=0,
            range_color=[-3, 3],
            custom_data=["short", "ret_5d", "price", "etf"],
        )
        fig.update_traces(
            textinfo="label+text",
            text=df.apply(lambda r: f"<b>{r['ret_5d']:+.2f}%</b><br>{r['etf']}", axis=1),
            textfont=dict(size=13, color="white", family="IBM Plex Mono"),
            marker=dict(line=dict(color=COLORS["bg"], width=2)),
            hovertemplate="<b>%{label}</b> (%{customdata[3]})<br>"
                          "5-day return: %{customdata[1]:+.2f}%<br>"
                          "Last: $%{customdata[2]:,.2f}<extra></extra>",
        )
        fig.update_layout(
            margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor=COLORS["bg"], plot_bgcolor=COLORS["bg"],
            font=dict(color=COLORS["text"], family="Inter"),
            height=380,
            coloraxis_colorbar=dict(
                title="5-day %", thickness=12, len=0.7,
                tickfont=dict(color=COLORS["text"], family="IBM Plex Mono"),
            ),
        )
        st.plotly_chart(fig, use_container_width=True, theme=None)

        # Quick takeaway
        df_sorted = df.sort_values("ret_5d", ascending=False)
        leader  = df_sorted.iloc[0]
        laggard = df_sorted.iloc[-1]
        st.caption(
            f"**Inflow leader:** {leader['sector']} ({leader['ret_5d']:+.2f}% / 5d). "
            f"**Outflow laggard:** {laggard['sector']} ({laggard['ret_5d']:+.2f}% / 5d). "
            "Rotation is typically a leading indicator of regime change — money flows "
            "into expected outperformers ~1-2 weeks before consensus catches up."
        )
    except Exception as e:
        st.caption(f"Sector chart failed: {e}")


def _render_alert_banner():
    """Show unacknowledged alerts as banners at the top."""
    try:
        from shared.alerts import recent_events, acknowledge_event
        events = recent_events(limit=5, unacknowledged_only=True)
    except Exception:
        events = []
    if not events:
        return

    for ev in events:
        lvl = ev.get("level", "info")
        icon_emoji = "🔴" if lvl == "critical" else "🟡" if lvl == "warning" else "🔵"
        col_msg, col_ack = st.columns([10, 1])
        with col_msg:
            st.markdown(
                f"<div style='background:#131825;border-left:3px solid "
                f"{'#ff5773' if lvl=='critical' else '#ffaa00' if lvl=='warning' else '#4c8bf5'};"
                f"padding:10px 16px;border-radius:4px;margin-bottom:6px'>"
                f"{icon_emoji} <b>{ev.get('ticker') or 'SYSTEM'}</b> — {ev.get('message', '')}"
                f"</div>",
                unsafe_allow_html=True,
            )
        with col_ack:
            if st.button("✓", key=f"ack_{ev['id']}", help="Acknowledge", use_container_width=True):
                acknowledge_event(ev["id"])
                st.rerun()


def _render_diff_section():
    """Show 'What changed since yesterday' panel."""
    try:
        from shared.diff_engine import summary
        diff = summary()
    except Exception:
        return

    if not diff or not any(diff.values()):
        return

    with st.expander("🔄 What changed since yesterday", expanded=True):
        col1, col2, col3 = st.columns(3)

        # Regime diff
        reg = diff.get("regime") or {}
        with col1:
            if reg.get("changed"):
                cur = reg["current"]["label"]
                prev = reg["previous"]["label"]
                st.markdown(f"**Regime shifted** 🚨")
                st.markdown(f"`{prev}` → **`{cur}`**")
            elif reg.get("current"):
                g_d = reg.get("growth_delta", 0)
                i_d = reg.get("inflation_delta", 0)
                st.markdown(f"**Regime: {reg['current']['label']}** (stable)")
                st.caption(f"Growth Δ {g_d:+.3f} · Inflation Δ {i_d:+.3f}")
            else:
                st.caption("Regime data unavailable")

        # Risk diff
        risk = diff.get("risk") or {}
        with col2:
            if risk.get("current"):
                cur = risk["current"]
                delta = risk.get("srs_delta", 0)
                arrow = "🔼" if delta > 1 else "🔽" if delta < -1 else "—"
                st.markdown(f"**SRS: {cur.get('srs', 0):.0f}/100** {arrow}")
                st.caption(f"Δ {delta:+.1f} · {cur.get('level', '—')}")
            else:
                st.caption("Risk data unavailable")

        # Sentiment diff
        sent = diff.get("sentiment") or {}
        with col3:
            if sent.get("current") and sent["current"].get("total", 0) > 0:
                b_d = sent.get("bull_delta", 0)
                arrow = "🟢" if b_d > 5 else "🔴" if b_d < -5 else "—"
                st.markdown(f"**Sentiment shift** {arrow}")
                st.caption(f"Bull Δ {b_d:+.1f}pp · {sent['current']['total']} articles")
            else:
                st.caption("Sentiment data unavailable")

        # New signals
        sigs = diff.get("signals") or {}
        if sigs.get("new_count", 0) > 0:
            st.divider()
            st.markdown(f"**🆕 {sigs['new_count']} new signals in last 24h**")
            cols = st.columns(min(4, len(sigs.get("by_source", {}))))
            for col, (src, count) in zip(cols, sigs.get("by_source", {}).items()):
                col.metric(src.upper(), count)


def _format_freshness(minutes_ago: float | None) -> tuple[str, str]:
    """Returns (display_text, status_kind). status_kind: live | stale | error."""
    if minutes_ago is None:
        return ("○ NO DATA", "error")
    if minutes_ago < 60:
        return (f"● {int(minutes_ago)} min ago", "live")
    if minutes_ago < 360:
        return (f"● {int(minutes_ago / 60)}h {int(minutes_ago % 60)}m ago", "live")
    if minutes_ago < 1440:
        return (f"⚠ {int(minutes_ago / 60)}h ago", "stale")
    days = int(minutes_ago / 1440)
    return (f"⚠ {days}d ago", "stale")


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
        st.page_link("app.py",                       label="🏠 Overview")
        st.page_link("pages/A_Global_Markets.py",    label="🌍 Global Markets")
        st.page_link("pages/1_Markets.py",           label="📈 US Markets")
        st.page_link("pages/6_Opportunities.py",     label="🎯 Opportunities")
        st.page_link("pages/9_Strategies.py",        label="🎲 Strategies")
        st.page_link("pages/5_Stock_Detail.py",      label="🔍 Stock Detail")
        st.page_link("pages/8_Options_Flow.py",      label="⚡ Options Flow")
        st.page_link("pages/2_Risk.py",              label="📊 Risk & VaR")
        st.page_link("pages/3_Research.py",          label="🔬 AI Research")
        st.page_link("pages/4_Portfolio.py",         label="💼 Portfolio")
        st.page_link("pages/7_Track_Record.py",      label="📈 Track Record")
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

    # ── Header bar with multiple freshness indicators ────────────────────────
    fresh = load_data_freshness()
    minutes_ago = fresh.get("minutes_since_latest")
    fresh_text, fresh_kind = _format_freshness(minutes_ago)

    col_title, col_pipe, col_data, col_refresh = st.columns([4, 2, 2, 1])
    with col_title:
        st.title("Intelligence Terminal")
        st.caption("Real-time market intelligence · Regime detection · Risk scoring")
    with col_pipe:
        st.caption("PIPELINE")
        st.markdown(status_pill(fresh_text, fresh_kind), unsafe_allow_html=True)
    with col_data:
        st.caption("REGIME DATA")
        if source == "supabase":
            st.markdown(status_pill("● SUPABASE", "live"), unsafe_allow_html=True)
        elif source == "live_fred":
            st.markdown(status_pill("● LIVE FRED", "stale"), unsafe_allow_html=True)
        else:
            st.markdown(status_pill("○ NO DATA", "error"), unsafe_allow_html=True)
    with col_refresh:
        st.write("")
        if st.button("🔄 Refresh", use_container_width=True,
                     help="Clears Streamlit cache and re-reads from Supabase (does NOT trigger pipeline)"):
            st.cache_data.clear()
            st.rerun()

    # ── Active alert banners (acknowledged-aware) ───────────────────────────
    _render_alert_banner()

    # If data is stale (>2 hours), surface a prominent CTA to trigger pipeline
    if minutes_ago is not None and minutes_ago > 120:
        st.warning(
            f"⏰ **Data is {int(minutes_ago / 60)}h {int(minutes_ago % 60)}m old.** "
            f"News pipeline runs on a cron (US market hours every 30 min, "
            f"off-hours every ~6h). Trigger a fresh run now:",
            icon="⏰",
        )
        cta1, cta2 = st.columns([1, 5])
        with cta1:
            st.link_button(
                "🚀 Run pipeline now",
                "https://github.com/git0ST/automation/actions/workflows/digest.yml",
                use_container_width=True,
                type="primary",
            )
        with cta2:
            st.caption(
                "**On the Actions page → click 'Run workflow' → wait 3-5 min → click Refresh here.** "
                "Free GitHub plan gives unlimited cron runs but they can be delayed by ~5-15 min during high load."
            )

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
            help=MARKET_REGIME,
        )
    with col2:
        st.metric(
            label="Systemic Risk",
            value=f"{srs:.0f} / 100",
            delta=level,
            delta_color="inverse" if srs >= 51 else "normal",
            help=SYSTEMIC_RISK,
        )
    with col3:
        st.metric(
            label="News Sentiment",
            value=f"↑ {bull_pct}% / ↓ {bear_pct}%",
            delta=f"{sentiment.get('n_items', 0)} articles · weighted",
            delta_color="off",
            help=NEWS_SENTIMENT,
        )
    with col4:
        st.metric(
            label="Alpha Signals",
            value=len(signals),
            delta="insider · options · congress",
            delta_color="off",
            help=ALPHA_SIGNALS,
        )
    with col5:
        st.metric(
            label="Data Freshness",
            value=fresh_text.lstrip("● ⚠ ○ "),
            delta=f"{len(market)} tickers cached",
            delta_color="off",
            help=DATA_FRESHNESS,
        )

    st.divider()

    # ── What changed since yesterday ────────────────────────────────────────
    _render_diff_section()

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

    # ── Sector Rotation heatmap ──────────────────────────────────────────────
    st.markdown("#### 🔥 Sector Rotation · 5-day momentum")
    st.caption("Where capital is flowing. Each tile sized by sector market cap, "
               "colored by 5-day return. Green = inflows, red = outflows.")
    _render_sector_rotation()

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
