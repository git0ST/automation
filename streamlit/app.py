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
from _theme           import apply_theme, COLORS, REGIME_COLORS, status_pill
from _terminal_chrome  import render_chrome, render_kpi_row
from _kpi_help         import (MARKET_REGIME, SYSTEMIC_RISK, NEWS_SENTIMENT,
                                ALPHA_SIGNALS, DATA_FRESHNESS)
from _data             import (load_articles, load_signals, load_market_snapshots,
                                load_regime_risk, load_market_prices, supabase_client,
                                check_setup_status, load_weighted_sentiment,
                                load_data_freshness)
from _components       import (ticker_card, render_ticker_grid, news_item_card,
                                source_badge, regime_card, TICKER_META)
apply_theme()
render_chrome("overview")


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


def _render_todays_setups():
    """Top 5 highest-conviction setups from the latest pipeline snapshot,
    each with concrete entry/stop/target/position size + freshness watcher."""
    client = supabase_client()
    if not client:
        return
    try:
        rows = (client.table("v_latest_opportunities")
                .select("*")
                .gte("confidence", 60)
                .neq("direction", "neutral")
                .order("confidence", desc=True)
                .limit(5)
                .execute()).data or []
    except Exception:
        return

    if not rows:
        return

    # Freshness check — warn if scan is >30 min old (signals may have shifted)
    from datetime import datetime, timezone
    scanned_at_str = rows[0].get("scanned_at")
    setup_age_min = None
    if scanned_at_str:
        try:
            ts = datetime.fromisoformat(scanned_at_str.replace("Z", "+00:00"))
            setup_age_min = (datetime.now(timezone.utc) - ts).total_seconds() / 60
        except Exception:
            pass

    col_h, col_age = st.columns([3, 2])
    with col_h:
        st.markdown("#### 🎯 Today's Top Setups")
    with col_age:
        if setup_age_min is not None:
            if setup_age_min < 30:
                pill_color, pill_label = "#00d68f", f"● Fresh · {int(setup_age_min)} min ago"
            elif setup_age_min < 90:
                pill_color, pill_label = "#ffaa00", f"● Aging · {int(setup_age_min)} min ago"
            else:
                pill_color, pill_label = "#ff5773", f"⚠ Stale · {int(setup_age_min/60)}h old"
            st.markdown(
                f'<div style="text-align:right;margin-top:14px">'
                f'<span style="color:{pill_color};font-size:11px;font-weight:600;'
                f'background:{pill_color}1f;padding:4px 10px;border-radius:10px">{pill_label}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    if setup_age_min is not None and setup_age_min > 90:
        st.info(
            "⚠ Setups are over 90 minutes old. Market conditions may have shifted. "
            "Re-check before placing trades — confidence values are based on stale signals.",
            icon="⚠️",
        )

    st.caption("Auto-scanned every 30 min by the pipeline cron. "
               "Entry/stop/target use 2× ATR. Click **Open** for full analysis.")

    # Portfolio value input (session-persisted)
    if "portfolio_value" not in st.session_state:
        st.session_state["portfolio_value"] = 100_000

    col_pv, col_action = st.columns([1, 4])
    with col_pv:
        st.session_state["portfolio_value"] = st.number_input(
            "Portfolio $", min_value=1000, max_value=100_000_000,
            value=int(st.session_state["portfolio_value"]),
            step=10_000, key="pv_overview",
            help="Used to size positions below. Stored in this session only.",
        )

    portfolio = st.session_state["portfolio_value"]

    for r in rows:
        ticker     = r["ticker"]
        direction  = r["direction"]
        confidence = r["confidence"]
        price      = r.get("price") or 0
        if price <= 0:
            continue

        # ATR proxy: use 2% of price as stop distance (conservative default)
        # since we don't have ATR in the snapshot — could be refined later
        atr_pct = 0.02
        if direction == "bullish":
            stop_pct   = 2 * atr_pct
            target_pct = 4 * atr_pct
            stop   = price * (1 - stop_pct)
            target = price * (1 + target_pct)
            action_label = "BUY"
            action_color = "#00d68f"
        else:
            stop_pct   = 2 * atr_pct
            target_pct = 4 * atr_pct
            stop   = price * (1 + stop_pct)
            target = price * (1 - target_pct)
            action_label = "SHORT"
            action_color = "#ff5773"

        # Position sizing: risk 1% of portfolio scaled by conviction
        max_risk = portfolio * 0.01 * (0.5 + confidence / 100)
        position_value = min(max_risk / stop_pct, portfolio * 0.15)
        shares = position_value / price if price > 0 else 0

        # Strategy names (if any)
        strategies = r.get("strategies") or []
        strat_names = ", ".join(s.get("name", "") for s in strategies[:2]) if strategies else None

        from _components import TICKER_META
        meta = TICKER_META.get(ticker, {})
        name = meta.get("name", ticker)

        with st.container():
            cols = st.columns([1, 1, 1, 1, 1, 1, 1])
            cols[0].markdown(
                f"<div style='font-weight:700;font-size:16px'>{ticker}</div>"
                f"<div style='font-size:10px;color:#8b93a7'>{name[:18]}</div>",
                unsafe_allow_html=True,
            )
            cols[1].markdown(
                f"<div style='color:{action_color};font-weight:700;font-size:14px'>{action_label}</div>"
                f"<div style='font-size:10px;color:#8b93a7'>{confidence:.0f}% conf</div>",
                unsafe_allow_html=True,
            )
            cols[2].markdown(
                f"<div style='font-family:IBM Plex Mono,monospace;font-weight:600'>${price:,.2f}</div>"
                f"<div style='font-size:10px;color:#8b93a7'>Entry</div>",
                unsafe_allow_html=True,
            )
            cols[3].markdown(
                f"<div style='font-family:IBM Plex Mono,monospace;color:#ff5773'>${stop:,.2f}</div>"
                f"<div style='font-size:10px;color:#8b93a7'>Stop ({stop_pct*100:.1f}%)</div>",
                unsafe_allow_html=True,
            )
            cols[4].markdown(
                f"<div style='font-family:IBM Plex Mono,monospace;color:#00d68f'>${target:,.2f}</div>"
                f"<div style='font-size:10px;color:#8b93a7'>Target (R/R 2:1)</div>",
                unsafe_allow_html=True,
            )
            cols[5].markdown(
                f"<div style='font-family:IBM Plex Mono,monospace;font-weight:600'>${position_value:,.0f}</div>"
                f"<div style='font-size:10px;color:#8b93a7'>{shares:.1f} sh · "
                f"{position_value/portfolio*100:.1f}% port</div>",
                unsafe_allow_html=True,
            )
            with cols[6]:
                if st.button("Open", key=f"setup_{ticker}", use_container_width=True):
                    st.session_state["detail_ticker"] = ticker
                    st.switch_page("pages/5_Stock_Detail.py")

            if strat_names:
                st.caption(f"📌 Matches: {strat_names}")
            st.markdown("<hr style='margin:6px 0;border-color:#1a2034'>", unsafe_allow_html=True)


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
    """Render regime + SRS detail cards on the overview page.

    Navigation is handled by _terminal_chrome.render_chrome() on all pages.
    These cards add expanded detail only on the overview.
    """
    with st.sidebar:
        # Data source pill
        if source == "supabase":
            st.markdown(status_pill("● LIVE · Supabase", "live"), unsafe_allow_html=True)
        elif source == "live_fred":
            st.markdown(status_pill("● LIVE · FRED fallback", "stale"), unsafe_allow_html=True)
        else:
            st.markdown(status_pill("○ No data", "error"), unsafe_allow_html=True)

        # Regime detail card
        if regime:
            r_label = regime.get("label", "—")
            r_color = REGIME_COLORS.get(regime.get("regime", ""), "#888")
            r_conf  = regime.get("confidence_pct", 0)
            t_risk  = regime.get("transition_risk", "—")
            favors  = ", ".join((regime.get("favors") or [])[:3])
            avoids  = ", ".join((regime.get("avoids") or [])[:2])
            st.markdown(f"""
            <div class="sidebar-card" style="margin-top:8px">
              <div style="font-size:9px;color:#8b93a7;letter-spacing:.14em;text-transform:uppercase;margin-bottom:8px;font-weight:600">Regime Detail</div>
              <div class="regime-badge" style="color:{r_color};background:{r_color}1a;border:1px solid {r_color}44">{r_label}</div>
              <div style="margin-top:8px;font-size:11px;color:#8b93a7">Confidence: <span style="color:#e6e9f0;font-family:'IBM Plex Mono',monospace">{r_conf:.0f}%</span></div>
              <div style="font-size:11px;color:#8b93a7;margin-top:3px">Transition: <span style="color:#e6e9f0">{t_risk}</span></div>
              {f'<div style="font-size:10px;color:#5a6378;margin-top:6px">↑ {favors}</div>' if favors else ''}
              {f'<div style="font-size:10px;color:#5a6378">↓ {avoids}</div>' if avoids else ''}
            </div>""", unsafe_allow_html=True)

        # SRS detail card
        if risk:
            srs   = risk.get("srs", 0)
            level = risk.get("level", "—")
            c     = "#00d68f" if srs < 26 else "#ffaa00" if srs < 51 else "#ff8800" if srs < 76 else "#ff5773"
            factors = risk.get("factors") or []
            factor_html = "".join(
                f'<div style="display:flex;justify-content:space-between;font-size:10px;margin-top:3px">'
                f'<span style="color:#5a6378">{f["name"]}</span>'
                f'<span style="color:{c}">{f["score"]:.0f}</span></div>'
                for f in factors[:4]
            )
            st.markdown(f"""
            <div class="sidebar-card">
              <div style="font-size:9px;color:#8b93a7;letter-spacing:.14em;text-transform:uppercase;font-weight:600">Risk Factors</div>
              <div style="display:flex;align-items:baseline;gap:6px;margin-top:6px">
                <span style="font-size:24px;font-weight:700;color:{c};font-family:'IBM Plex Mono',monospace">{srs:.0f}</span>
                <span style="font-size:11px;color:#8b93a7">/ 100 · <span style="color:{c}">{level}</span></span>
              </div>
              <div class="srs-bar-container" style="margin-top:6px">
                <div class="srs-bar" style="width:{srs}%;background:{c}"></div>
              </div>
              {factor_html}
            </div>""", unsafe_allow_html=True)

        st.caption("Yahoo Finance · FRED · ICE BofA · Groq AI")


# ════════════════════════════════════════════════════════════════════════════
# OVERVIEW PAGE
# ════════════════════════════════════════════════════════════════════════════

def main():
    regime, risk, missing_tables, source = load_regime_risk()
    render_sidebar(regime, risk, source)

    # ── Active alerts surface first (most urgent) ───────────────────────────
    _render_alert_banner()

    # ── Title + compact pulse pills (no big KPI cards) ──────────────────────
    fresh = load_data_freshness()
    minutes_ago = fresh.get("minutes_since_latest")
    fresh_text, fresh_kind = _format_freshness(minutes_ago)

    col_title, col_pulse, col_refresh = st.columns([5, 4, 1])
    with col_title:
        st.markdown("### Home")
        st.caption("Trade ideas · market pulse · alerts")
    with col_pulse:
        # 3 compact pills: regime, SRS, freshness — densely packed
        r_label = regime.get("label", "—") if regime else "—"
        r_conf = regime.get("confidence_pct", 0) if regime else 0
        r_color = REGIME_COLORS.get(regime.get("regime", ""), "#888") if regime else "#888"
        srs = risk.get("srs", 0) if risk else 0
        srs_level = risk.get("level", "—") if risk else "—"
        srs_color = "#00d68f" if srs < 26 else "#ffaa00" if srs < 51 else "#ff8800" if srs < 76 else "#ff5773"
        st.markdown(
            f'<div style="display:flex;gap:14px;align-items:center;margin-top:6px;'
            f'font-family:IBM Plex Mono,monospace;font-size:13px">'
            f'<span><b style="color:#8b93a7;font-size:10px">REGIME </b>'
            f'<b style="color:{r_color}">{r_label}</b> '
            f'<span style="color:#8b93a7">{r_conf:.0f}%</span></span>'
            f'<span><b style="color:#8b93a7;font-size:10px">SRS </b>'
            f'<b style="color:{srs_color}">{srs:.0f}</b>'
            f'<span style="color:#8b93a7">/100 {srs_level}</span></span>'
            f'<span><b style="color:#8b93a7;font-size:10px">DATA </b>'
            f'<b style="color:{"#00d68f" if fresh_kind == "live" else "#ffaa00"}">'
            f'{fresh_text.lstrip("● ⚠ ○ ")}</b></span>'
            f'</div>', unsafe_allow_html=True)
    with col_refresh:
        st.write("")
        if st.button("🔄", use_container_width=True, help="Refresh data"):
            st.cache_data.clear()
            st.rerun()

    # Soft warning only if blocking — migrations missing or data very stale
    if missing_tables:
        st.warning(
            f"⚠ Run [migration 003]"
            f"(https://github.com/git0ST/automation/blob/main/supabase/migrations/003_intelligence_tables.sql) "
            f"in Supabase → tables `{', '.join(missing_tables)}` missing.",
            icon="⚠️",
        )
    elif minutes_ago is not None and minutes_ago > 120:
        st.info(
            f"⏰ Data {int(minutes_ago / 60)}h old. "
            f"[Trigger pipeline](https://github.com/git0ST/automation/actions/workflows/digest.yml) "
            f"for fresh news + signals.",
            icon="⏰",
        )

    st.divider()

    # ── PRIMARY: Today's Top Setups (the one thing that matters) ────────────
    _render_todays_setups()

    st.divider()

    # ── SECONDARY: Compact 2-column — Sector heatmap + recent alpha signals ─
    col_sectors, col_signals = st.columns([3, 2])

    with col_sectors:
        st.markdown("##### Sector Rotation · 5d")
        _render_sector_rotation()

    with col_signals:
        signals, sig_status = load_signals(limit=12)
        st.markdown("##### Alpha Signals")
        if signals:
            for sig in signals[:8]:
                s_sent  = sig.get("sentiment_label") or "neutral"
                s_icon  = "▲" if s_sent == "bullish" else "▼" if s_sent == "bearish" else "—"
                s_color = "#00d68f" if s_sent == "bullish" else "#ff5773" if s_sent == "bearish" else "#8b93a7"
                src     = (sig.get("source") or "?").upper()[:5]
                title   = (sig.get("title") or "—")[:48]
                st.markdown(
                    f'<div style="background:#131825;border:1px solid #1f2937;'
                    f'border-radius:4px;padding:6px 10px;margin-bottom:4px;'
                    f'display:flex;gap:8px;align-items:center;font-size:11px">'
                    f'<span style="color:{s_color};font-weight:700">{s_icon}</span>'
                    f'<code style="font-size:10px">{src}</code>'
                    f'<span style="color:#c8cce0">{title}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No signals yet — run pipeline to populate")


main()
