"""Terminal chrome — sidebar nav + ticker tape + command bar shown on every page.

Bloomberg-style persistent header: real-time prices on a strip + a
universal ticker lookup that jumps directly to Stock Detail.

Call render_chrome() at the top of every page right after apply_theme().
"""
from __future__ import annotations
import streamlit as st


# ── Sidebar navigation ────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _fetch_regime_srs() -> tuple[str, str, str, int, str]:
    """Return (regime_label, regime_color, conf_str, srs, srs_level). Cached 5 min."""
    try:
        from _data import load_regime_risk
        regime, risk, _, _ = load_regime_risk()
        from _theme import REGIME_COLORS
        r_label  = regime.get("label", "—") if regime else "—"
        r_conf   = f"{regime.get('confidence_pct', 0):.0f}%" if regime else "—"
        r_color  = REGIME_COLORS.get(regime.get("regime", ""), "#8b93a7") if regime else "#8b93a7"
        srs      = int(risk.get("srs", 0)) if risk else 0
        srs_lvl  = risk.get("level", "—") if risk else "—"
        return r_label, r_color, r_conf, srs, srs_lvl
    except Exception:
        return "—", "#8b93a7", "—", 0, "—"


def _render_sidebar_nav(current_page: str = "") -> None:
    """Render the persistent grouped navigation rail in the sidebar.

    Groups mirror an HFT trader's daily decision flow:
      SIGNALS  → what to act on now
      MARKETS  → situational awareness
      PORTFOLIO → manage current exposure
      RESEARCH  → build edge
    """
    with st.sidebar:
        # ── Brand ─────────────────────────────────────────────────────────────
        st.markdown(
            '<div style="display:flex;align-items:baseline;gap:8px;padding:10px 12px 6px">'
            '<span style="font-family:\'IBM Plex Mono\',monospace;font-size:17px;'
            'font-weight:700;color:#e8a435;letter-spacing:.18em">INTL</span>'
            '<span style="font-size:9px;color:#3a4060;letter-spacing:.06em">TERMINAL · v2.5</span>'
            '</div>',
            unsafe_allow_html=True,
        )

        # ── Persistent regime + SRS status strip ──────────────────────────────
        r_label, r_color, r_conf, srs, srs_lvl = _fetch_regime_srs()
        srs_color = (
            "#00d68f" if srs < 26 else
            "#ffaa00" if srs < 51 else
            "#ff8800" if srs < 76 else
            "#ff5773"
        )
        st.markdown(
            f'<div class="nav-status">'
            f'<div class="nav-stat">'
            f'<div class="nav-stat-lbl">REGIME</div>'
            f'<div class="nav-stat-val" style="color:{r_color}">{r_label}</div>'
            f'<div style="font-size:8.5px;color:#5a6378">{r_conf}</div>'
            f'</div>'
            f'<div class="nav-stat">'
            f'<div class="nav-stat-lbl">SRS</div>'
            f'<div class="nav-stat-val" style="color:{srs_color}">{srs}</div>'
            f'<div style="font-size:8.5px;color:#5a6378">{srs_lvl}</div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ── SIGNALS ───────────────────────────────────────────────────────────
        st.markdown('<div class="nav-section">SIGNALS</div>', unsafe_allow_html=True)
        st.page_link("app.py",                    label="📊 Overview",     help="Regime · macro pulse · top setups")
        st.page_link("pages/6_Opportunities.py",  label="🎯 Setups",       help="High-conviction trade ideas ranked by confidence")
        st.page_link("pages/8_Options_Flow.py",   label="⚡ Options Flow",  help="Unusual activity · institutional positioning")

        # ── MARKETS ───────────────────────────────────────────────────────────
        st.markdown('<div class="nav-section">MARKETS</div>', unsafe_allow_html=True)
        st.page_link("pages/A_Global_Markets.py", label="🌍 Global",        help="World indices · FX · commodities")
        st.page_link("pages/1_Markets.py",        label="📈 US Sectors",    help="Sector rotation heatmap · money flow")
        st.page_link("pages/5_Stock_Detail.py",   label="🔍 Deep Dive",     help="Single ticker · technicals · signals · news")

        # ── PORTFOLIO ─────────────────────────────────────────────────────────
        st.markdown('<div class="nav-section">PORTFOLIO</div>', unsafe_allow_html=True)
        st.page_link("pages/4_Portfolio.py",      label="💼 Positions",     help="Holdings · P&L · exposure")
        st.page_link("pages/2_Risk.py",           label="🛡 Risk",          help="VaR · drawdown · correlation")

        # ── RESEARCH ──────────────────────────────────────────────────────────
        st.markdown('<div class="nav-section">RESEARCH</div>', unsafe_allow_html=True)
        st.page_link("pages/3_Research.py",       label="🤖 AI Analysis",   help="LLM-powered research · data queries")
        st.page_link("pages/9_Strategies.py",     label="🎲 Strategies",    help="Playbooks · regime-matched tactics")
        st.page_link("pages/7_Track_Record.py",   label="📋 Track Record",  help="Model accuracy · backtests · hit rate")

        # ── Pipeline status (collapsed) ───────────────────────────────────────
        st.markdown('<div style="margin-top:10px;border-top:1px solid #1f2937"></div>',
                    unsafe_allow_html=True)
        with st.expander("⚙️ Pipeline", expanded=False):
            try:
                from _data import check_setup_status
                status = check_setup_status()
                if status.get("supabase_connected"):
                    if status.get("has_pipeline_data"):
                        rows = status["tables"]["articles"]["rows"]
                        st.markdown(f"✅ **{rows}** articles · active")
                    else:
                        st.markdown("⚠️ No pipeline data yet")
                        st.link_button(
                            "🚀 Trigger pipeline",
                            "https://github.com/git0ST/automation/actions/workflows/digest.yml",
                            use_container_width=True,
                        )
                else:
                    st.markdown("❌ Supabase not connected")
            except Exception:
                st.caption("Status unavailable")


# ── Tape configuration ────────────────────────────────────────────────────────

# Market type groups: (display_label, db_type_key, accent_color)
TAPE_GROUPS = [
    ("INDICES",    "index",     "#b47cf5"),
    ("EQUITIES",   "equity",    "#4da6ff"),
    ("FOREX",      "forex",     "#e8a435"),
    ("CRYPTO",     "crypto",    "#18d4a8"),
    ("COMMOD",     "commodity", "#f07030"),
    ("BONDS",      "bond",      "#26c2d6"),
]

# yfinance fallback — fires only when Supabase has no market data
_YF_FALLBACK = {
    "index":     [("^GSPC","S&P"),("^IXIC","NDX"),("^DJI","DOW"),("^VIX","VIX"),
                  ("^FTSE","FTSE"),("^GDAXI","DAX"),("^N225","NIK"),("^HSI","HSI")],
    "forex":     [("EURUSD=X","EUR"),("USDJPY=X","JPY"),("GBPUSD=X","GBP"),("DX-Y.NYB","DXY")],
    "crypto":    [("BTC-USD","BTC"),("ETH-USD","ETH"),("SOL-USD","SOL"),("BNB-USD","BNB")],
    "commodity": [("GC=F","GOLD"),("CL=F","OIL"),("SI=F","SILVER"),("NG=F","NAT GAS")],
    "equity":    [("NVDA","NVDA"),("AAPL","AAPL"),("MSFT","MSFT"),("GOOGL","GOOGL"),
                  ("META","META"),("AMZN","AMZN"),("TSLA","TSLA")],
    "bond":      [("^TNX","10Y"),("^TYX","30Y"),("^IRX","3M")],
}


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_tape_grouped() -> dict[str, list]:
    """Fetch all pipeline market data from Supabase grouped by type.

    Falls back to yfinance if Supabase has no market data.
    Returns dict[type_key -> list of {ticker, label, price, change}].
    """
    groups: dict[str, list] = {g[1]: [] for g in TAPE_GROUPS}

    # ── Primary: Supabase pipeline markets ────────────────────────────────────
    try:
        from _data import load_market_snapshots
        rows, status = load_market_snapshots(limit=300)
        if rows:
            seen: set[str] = set()
            for r in rows:
                tk = (r.get("ticker") or "").strip()
                if not tk or tk in seen:
                    continue
                seen.add(tk)
                mtype = (r.get("type") or "equity").lower()
                price = r.get("price") or r.get("last_price") or 0
                chg   = r.get("change_pct") or r.get("pct_change") or 0
                name  = r.get("name") or tk
                # Short display label: use ticker, strip common suffixes
                lbl = tk.replace("-USD","").replace("=X","").replace("=F","")[:8]
                if mtype in groups:
                    groups[mtype].append({
                        "ticker": tk, "label": lbl,
                        "price": float(price), "change": float(chg),
                        "name": name,
                    })
            # If we got data from Supabase, return it
            if any(groups.values()):
                return groups
    except Exception:
        pass

    # ── Fallback: yfinance for the curated symbol list ─────────────────────────
    try:
        import yfinance as yf
        for mtype, syms in _YF_FALLBACK.items():
            for sym, lbl in syms:
                try:
                    t = yf.Ticker(sym).history(period="5d", interval="1d", auto_adjust=True)
                    if t.empty or len(t) < 2:
                        continue
                    last = float(t["Close"].iloc[-1])
                    prev = float(t["Close"].iloc[-2])
                    groups[mtype].append({
                        "ticker": sym, "label": lbl,
                        "price": last,
                        "change": (last / prev - 1) * 100 if prev else 0,
                        "name": lbl,
                    })
                except Exception:
                    continue
    except ImportError:
        pass

    return groups


def render_chrome(current_page: str = "") -> None:
    """Render sidebar nav + ticker tape + command bar on every page.

    Call at the top of every page right after apply_theme().
    """
    _render_sidebar_nav(current_page)
    _render_tape()
    _render_command_bar()


def _fmt_price(price: float, mtype: str) -> str:
    """Format price compactly for the tape."""
    if price == 0:
        return "—"
    if mtype == "crypto" and price < 1:
        return f"${price:.4f}"
    if mtype in ("forex",):
        return f"{price:.4f}"
    if price >= 10_000:
        return f"{price:,.0f}"
    if price >= 1_000:
        return f"{price:,.1f}"
    if price >= 100:
        return f"{price:.2f}"
    return f"{price:.3f}"


def _render_tape():
    groups = _fetch_tape_grouped()
    if not any(groups.values()):
        return

    # Build one pass of ticker HTML — groups separated by colored pills
    items_html = []
    for lbl, mtype, color in TAPE_GROUPS:
        tickers = groups.get(mtype, [])
        if not tickers:
            continue
        # Group separator pill
        items_html.append(
            f'<span style="margin:0 14px 0 6px;font-size:9px;font-weight:800;'
            f'letter-spacing:.14em;color:{color};background:{color}18;'
            f'border:1px solid {color}44;padding:1px 6px;border-radius:3px;'
            f'vertical-align:middle;flex-shrink:0">{lbl}</span>'
        )
        for t in tickers:
            chg   = t["change"]
            tc    = "#00d68f" if chg >= 0 else "#ff5773"
            arrow = "▲" if chg >= 0 else "▼"
            price_str = _fmt_price(t["price"], mtype)
            items_html.append(
                f'<span style="margin-right:20px;white-space:nowrap;flex-shrink:0;'
                f'font-family:IBM Plex Mono,monospace;font-size:12px">'
                f'<b style="color:#c6cae2;letter-spacing:.03em">{t["label"]}</b>'
                f'<span style="color:#5a6378;margin:0 3px">·</span>'
                f'<span style="color:#e6e9f0;font-weight:600">{price_str}</span>'
                f'<span style="color:{tc};font-size:11px;margin-left:4px">'
                f'{arrow}{abs(chg):.2f}%</span>'
                f'</span>'
            )

    if not items_html:
        return

    # Total items drives animation speed: ~0.65s per item, min 30s
    n_items = sum(len(groups.get(g[1], [])) for g in TAPE_GROUPS)
    duration = max(30, int(n_items * 0.65))

    one_pass = "".join(items_html)
    # Duplicate for seamless loop (CSS translates -50%)
    inner = one_pass + one_pass

    st.markdown(
        f'<style>'
        f'@keyframes intl-tape {{'
        f'  0%   {{ transform: translateX(0); }}'
        f'  100% {{ transform: translateX(-50%); }}'
        f'}}'
        f'.intl-tape-inner {{'
        f'  display:flex;align-items:center;'
        f'  animation:intl-tape {duration}s linear infinite;'
        f'  will-change:transform;'
        f'}}'
        f'.intl-tape-inner:hover {{ animation-play-state:paused; }}'
        f'</style>'
        f'<div style="background:#04040c;border-bottom:1px solid #1a1a2e;'
        f'height:28px;overflow:hidden;position:relative;'
        f'margin:-1rem -1rem 0.5rem -1rem;display:flex;align-items:center">'
        f'<div style="position:absolute;left:0;top:0;bottom:0;width:40px;z-index:2;'
        f'background:linear-gradient(to right,#04040c 50%,transparent)"></div>'
        f'<div style="position:absolute;right:0;top:0;bottom:0;width:40px;z-index:2;'
        f'background:linear-gradient(to left,#04040c 50%,transparent)"></div>'
        f'<div class="intl-tape-inner" style="padding-left:40px">{inner}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_command_bar():
    """Universal ticker lookup. Type ticker → jump to Stock Detail."""
    col_cmd, col_help = st.columns([5, 1])
    with col_cmd:
        query = st.text_input(
            "Quick lookup",
            value=st.session_state.get("_cmd", ""),
            placeholder="Type a ticker (NVDA, AAPL, ^GSPC, BTC-USD) and press Enter →",
            key="_cmd_input",
            label_visibility="collapsed",
        )
    with col_help:
        st.markdown(
            '<div style="color:#5a6378;font-size:10px;text-align:right;padding-top:8px">'
            '⌨️ Type ticker + Enter</div>',
            unsafe_allow_html=True,
        )

    if query and query.strip():
        sym = query.strip().upper()
        # Heuristic: looks like a ticker, jump to Stock Detail
        if 1 <= len(sym) <= 12 and any(c.isalpha() for c in sym):
            st.session_state["detail_ticker"] = sym
            st.session_state["_cmd"] = ""
            st.switch_page("pages/5_Stock_Detail.py")


def render_kpi_row(items: list[dict]) -> None:
    """Compact horizontal KPI strip — denser than st.metric, no big numbers.

    items: list of {label, value, color (optional), tooltip (optional)}
    Each rendered as: LABEL  value (color)
    """
    pieces = []
    for it in items:
        color = it.get("color", "#e6e9f0")
        pieces.append(
            f'<div style="display:inline-block;margin-right:24px;vertical-align:top">'
            f'  <div style="color:#8b93a7;font-size:9px;letter-spacing:.12em;'
            f'text-transform:uppercase;font-weight:600">{it["label"]}</div>'
            f'  <div style="color:{color};font-size:18px;font-weight:600;'
            f'font-family:IBM Plex Mono,monospace;line-height:1.1">{it["value"]}</div>'
            f'  {("<div style=color:#8b93a7;font-size:10px>" + it["sub"] + "</div>") if it.get("sub") else ""}'
            f'</div>'
        )
    st.markdown("".join(pieces), unsafe_allow_html=True)
