"""Terminal chrome — ticker tape + command bar shown on every page.

Bloomberg-style persistent header: real-time prices on a strip + a
universal ticker lookup that jumps directly to Stock Detail.

Call render_chrome() at the top of every page right after apply_theme().
"""
from __future__ import annotations
import streamlit as st


# Always-visible tape tickers — global + US + crypto pulse
TAPE_SYMBOLS = (
    "^GSPC", "^IXIC", "^DJI", "^VIX",
    "^FTSE", "^GDAXI", "^N225", "^HSI",
    "DX-Y.NYB", "EURUSD=X", "USDJPY=X",
    "GC=F", "CL=F",
    "BTC-USD", "ETH-USD",
)

TAPE_LABELS = {
    "^GSPC":    "S&P",     "^IXIC":   "NDX",    "^DJI":    "DOW",
    "^VIX":     "VIX",
    "^FTSE":    "FTSE",    "^GDAXI":  "DAX",    "^N225":   "NIK",   "^HSI":    "HSI",
    "DX-Y.NYB": "DXY",     "EURUSD=X":"EUR",    "USDJPY=X":"JPY",
    "GC=F":     "GOLD",    "CL=F":    "OIL",
    "BTC-USD":  "BTC",     "ETH-USD": "ETH",
}


@st.cache_data(ttl=120, show_spinner=False)
def _fetch_tape() -> dict:
    """Real-time tape pulse via Finnhub if available, else yfinance."""
    out = {}
    # Try Finnhub first for stock indices  / yfinance for futures + indices
    try:
        import yfinance as yf
        for sym in TAPE_SYMBOLS:
            try:
                t = yf.Ticker(sym).history(period="5d", interval="1d", auto_adjust=True)
                if t.empty or len(t) < 2:
                    continue
                last = float(t["Close"].iloc[-1])
                prev = float(t["Close"].iloc[-2])
                out[sym] = {
                    "label":  TAPE_LABELS.get(sym, sym),
                    "price":  last,
                    "change": (last / prev - 1) * 100 if prev else 0,
                }
            except Exception:
                continue
    except ImportError:
        pass
    return out


def render_chrome(current_page: str = "") -> None:
    """Render the persistent ticker tape + command bar.

    Call at the top of every page right after apply_theme().
    """
    _render_tape()
    _render_command_bar()


def _render_tape():
    tape = _fetch_tape()
    if not tape:
        return

    pieces = []
    for sym in TAPE_SYMBOLS:
        d = tape.get(sym)
        if not d:
            continue
        color = "#00d68f" if d["change"] >= 0 else "#ff5773"
        arrow = "▲" if d["change"] >= 0 else "▼"
        # Format price compactly — major indices use no decimals, FX 4-5 decimals
        if d["price"] >= 1000:
            price_str = f"{d['price']:,.0f}"
        elif d["price"] >= 100:
            price_str = f"{d['price']:,.2f}"
        elif d["price"] >= 1:
            price_str = f"{d['price']:.3f}"
        else:
            price_str = f"{d['price']:.5f}"

        pieces.append(
            f'<span style="margin-right:18px;font-family:IBM Plex Mono,monospace">'
            f'<b style="color:#8b93a7;font-size:10px;letter-spacing:.06em">{d["label"]}</b> '
            f'<span style="color:#e6e9f0;font-weight:600">{price_str}</span> '
            f'<span style="color:{color};font-size:11px">{arrow}{abs(d["change"]):.2f}%</span>'
            f'</span>'
        )

    st.markdown(
        f'<div class="ticker-tape" style="background:#0c0c18;border-bottom:1px solid #1f2937;'
        f'padding:6px 14px;margin:-1rem -1rem 0.5rem -1rem;'
        f'font-size:12px;overflow-x:auto;white-space:nowrap">'
        f'{"".join(pieces)}'
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
