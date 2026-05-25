"""
INTL Component Library — professional cards, tickers with logos, source badges.

Inspired by Bloomberg/TradingView/Aladdin tile layouts.
All components are self-contained HTML+CSS that work inside Streamlit's
unsafe_allow_html context.
"""
from __future__ import annotations
import streamlit as st


# ── Ticker → Company name + logo mapping ─────────────────────────────────────
# Logos served via Financial Modeling Prep's free CDN (no key needed for logo)
# Fallback: first letter colored block.

TICKER_META = {
    # Indices
    "^GSPC":   {"name": "S&P 500",        "logo": None, "type": "index", "country": "🇺🇸"},
    "^IXIC":   {"name": "Nasdaq Comp.",   "logo": None, "type": "index", "country": "🇺🇸"},
    "^DJI":    {"name": "Dow Jones",      "logo": None, "type": "index", "country": "🇺🇸"},
    "^RUT":    {"name": "Russell 2000",   "logo": None, "type": "index", "country": "🇺🇸"},
    "^VIX":    {"name": "VIX",            "logo": None, "type": "index", "country": "🇺🇸"},
    "^FTSE":   {"name": "FTSE 100",       "logo": None, "type": "index", "country": "🇬🇧"},
    "^N225":   {"name": "Nikkei 225",     "logo": None, "type": "index", "country": "🇯🇵"},

    # Mega cap
    "NVDA":  {"name": "NVIDIA",         "logo": "NVDA", "type": "stock", "sector": "Semis"},
    "AAPL":  {"name": "Apple",          "logo": "AAPL", "type": "stock", "sector": "Tech"},
    "MSFT":  {"name": "Microsoft",      "logo": "MSFT", "type": "stock", "sector": "Tech"},
    "GOOGL": {"name": "Alphabet",       "logo": "GOOGL","type": "stock", "sector": "Tech"},
    "META":  {"name": "Meta",           "logo": "META", "type": "stock", "sector": "Tech"},
    "AMZN":  {"name": "Amazon",         "logo": "AMZN", "type": "stock", "sector": "Tech"},
    "TSLA":  {"name": "Tesla",          "logo": "TSLA", "type": "stock", "sector": "Auto"},
    "AVGO":  {"name": "Broadcom",       "logo": "AVGO", "type": "stock", "sector": "Semis"},
    "ORCL":  {"name": "Oracle",         "logo": "ORCL", "type": "stock", "sector": "Tech"},

    # AI / Semis
    "AMD":   {"name": "AMD",            "logo": "AMD",  "type": "stock", "sector": "Semis"},
    "INTC":  {"name": "Intel",          "logo": "INTC", "type": "stock", "sector": "Semis"},
    "QCOM":  {"name": "Qualcomm",       "logo": "QCOM", "type": "stock", "sector": "Semis"},
    "ARM":   {"name": "Arm Holdings",   "logo": "ARM",  "type": "stock", "sector": "Semis"},
    "SMCI":  {"name": "Super Micro",    "logo": "SMCI", "type": "stock", "sector": "Semis"},
    "TSM":   {"name": "TSMC",           "logo": "TSM",  "type": "stock", "sector": "Semis"},
    "MU":    {"name": "Micron",         "logo": "MU",   "type": "stock", "sector": "Semis"},
    "MRVL":  {"name": "Marvell",        "logo": "MRVL", "type": "stock", "sector": "Semis"},
    "ASML":  {"name": "ASML",           "logo": "ASML", "type": "stock", "sector": "Semis"},

    # Financials
    "JPM":   {"name": "JPMorgan",       "logo": "JPM",  "type": "stock", "sector": "Bank"},
    "GS":    {"name": "Goldman Sachs",  "logo": "GS",   "type": "stock", "sector": "Bank"},
    "MS":    {"name": "Morgan Stanley", "logo": "MS",   "type": "stock", "sector": "Bank"},
    "BAC":   {"name": "Bank of America","logo": "BAC",  "type": "stock", "sector": "Bank"},
    "BRK-B": {"name": "Berkshire",      "logo": "BRK-B","type": "stock", "sector": "Conglomerate"},
    "WFC":   {"name": "Wells Fargo",    "logo": "WFC",  "type": "stock", "sector": "Bank"},
    "C":     {"name": "Citigroup",      "logo": "C",    "type": "stock", "sector": "Bank"},
    "BLK":   {"name": "BlackRock",      "logo": "BLK",  "type": "stock", "sector": "AssetMgmt"},
    "V":     {"name": "Visa",           "logo": "V",    "type": "stock", "sector": "Payments"},
    "MA":    {"name": "Mastercard",     "logo": "MA",   "type": "stock", "sector": "Payments"},

    # Energy
    "XOM":   {"name": "ExxonMobil",     "logo": "XOM",  "type": "stock", "sector": "Energy"},
    "CVX":   {"name": "Chevron",        "logo": "CVX",  "type": "stock", "sector": "Energy"},
    "COP":   {"name": "ConocoPhillips", "logo": "COP",  "type": "stock", "sector": "Energy"},
    "SLB":   {"name": "Schlumberger",   "logo": "SLB",  "type": "stock", "sector": "Energy"},
    "EOG":   {"name": "EOG Resources",  "logo": "EOG",  "type": "stock", "sector": "Energy"},
    "OXY":   {"name": "Occidental",     "logo": "OXY",  "type": "stock", "sector": "Energy"},

    # Healthcare
    "UNH":   {"name": "UnitedHealth",   "logo": "UNH",  "type": "stock", "sector": "Health"},
    "LLY":   {"name": "Eli Lilly",      "logo": "LLY",  "type": "stock", "sector": "Pharma"},
    "JNJ":   {"name": "J&J",            "logo": "JNJ",  "type": "stock", "sector": "Pharma"},
    "MRK":   {"name": "Merck",          "logo": "MRK",  "type": "stock", "sector": "Pharma"},
    "PFE":   {"name": "Pfizer",         "logo": "PFE",  "type": "stock", "sector": "Pharma"},
    "ABBV":  {"name": "AbbVie",         "logo": "ABBV", "type": "stock", "sector": "Pharma"},

    # Consumer
    "WMT":   {"name": "Walmart",        "logo": "WMT",  "type": "stock", "sector": "Retail"},
    "COST":  {"name": "Costco",         "logo": "COST", "type": "stock", "sector": "Retail"},
    "HD":    {"name": "Home Depot",     "logo": "HD",   "type": "stock", "sector": "Retail"},
    "MCD":   {"name": "McDonald's",     "logo": "MCD",  "type": "stock", "sector": "Restaurant"},
    "NKE":   {"name": "Nike",           "logo": "NKE",  "type": "stock", "sector": "Apparel"},
    "SBUX":  {"name": "Starbucks",      "logo": "SBUX", "type": "stock", "sector": "Restaurant"},

    # ETFs
    "SPY":   {"name": "SPDR S&P 500",   "logo": "SPY",  "type": "etf", "sector": "Broad"},
    "QQQ":   {"name": "Invesco QQQ",    "logo": "QQQ",  "type": "etf", "sector": "Tech"},
    "IWM":   {"name": "Russell 2000",   "logo": "IWM",  "type": "etf", "sector": "Small-cap"},
    "DIA":   {"name": "Dow ETF",        "logo": "DIA",  "type": "etf", "sector": "Broad"},
    "VTI":   {"name": "Total Market",   "logo": "VTI",  "type": "etf", "sector": "Broad"},
    "GLD":   {"name": "Gold",           "logo": "GLD",  "type": "etf", "sector": "Commodity"},
    "TLT":   {"name": "20Y Treasury",   "logo": "TLT",  "type": "etf", "sector": "Bond"},

    # Crypto
    "BTC-USD": {"name": "Bitcoin",       "logo": None, "type": "crypto", "icon": "₿"},
    "ETH-USD": {"name": "Ethereum",      "logo": None, "type": "crypto", "icon": "Ξ"},
    "SOL-USD": {"name": "Solana",        "logo": None, "type": "crypto", "icon": "◎"},
    "BNB-USD": {"name": "BNB",           "logo": None, "type": "crypto", "icon": "B"},
    "XRP-USD": {"name": "XRP",           "logo": None, "type": "crypto", "icon": "X"},
}


def get_logo_url(ticker: str) -> str | None:
    """Return logo URL from Financial Modeling Prep's free CDN (no key for logos)."""
    meta = TICKER_META.get(ticker, {})
    if meta.get("type") == "index":
        return None  # use country flag instead
    if meta.get("type") == "crypto":
        return f"https://cryptologos.cc/logos/{meta.get('name','').lower()}-{ticker.split('-')[0].lower()}-logo.png"
    if meta.get("logo"):
        # FMP serves free logo PNGs at this CDN endpoint
        return f"https://financialmodelingprep.com/image-stock/{meta['logo']}.png"
    return None


# ── Ticker card with logo, name, price, % change ─────────────────────────────

def ticker_card(ticker: str, price: float, change_pct: float,
                volume: int | None = None, extra: str = "") -> str:
    """Return HTML for a professional ticker card.

    Renders: [logo] TICKER · Name
             $price
             ▲/▼ change %
    """
    meta = TICKER_META.get(ticker, {})
    name = meta.get("name", ticker)
    color = "#00d68f" if change_pct >= 0 else "#ff5773"
    arrow = "▲" if change_pct >= 0 else "▼"
    logo_url = get_logo_url(ticker)

    # Logo cell: image OR emoji OR colored letter block
    if logo_url:
        logo_html = (
            f'<img src="{logo_url}" alt="{ticker}" '
            f'style="width:28px;height:28px;border-radius:6px;background:white;padding:2px;'
            f'object-fit:contain;flex-shrink:0" '
            f'onerror="this.outerHTML=\'<div style=&quot;width:28px;height:28px;border-radius:6px;'
            f'background:linear-gradient(135deg,#1f2937,#2a3447);display:flex;align-items:center;'
            f'justify-content:center;font-weight:700;font-size:12px;color:#8b93a7;'
            f'flex-shrink:0&quot;>{ticker[:2]}</div>\'">'
        )
    elif meta.get("country"):
        logo_html = (
            f'<div style="width:28px;height:28px;display:flex;align-items:center;'
            f'justify-content:center;font-size:20px;flex-shrink:0">'
            f'{meta["country"]}</div>'
        )
    elif meta.get("icon"):
        logo_html = (
            f'<div style="width:28px;height:28px;border-radius:6px;background:#1a2034;'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-weight:700;color:#ffaa00;flex-shrink:0">'
            f'{meta["icon"]}</div>'
        )
    else:
        logo_html = (
            f'<div style="width:28px;height:28px;border-radius:6px;'
            f'background:linear-gradient(135deg,#1f2937,#2a3447);'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-weight:700;font-size:11px;color:#8b93a7;flex-shrink:0">'
            f'{ticker[:2]}</div>'
        )

    volume_html = ""
    if volume:
        vol_str = _format_volume(volume)
        volume_html = (
            f'<div style="font-size:10px;color:#5a6378;margin-top:6px;'
            f'font-family:IBM Plex Mono,monospace">Vol {vol_str}</div>'
        )

    return f"""
    <div style="background:#131825;border:1px solid #1f2937;border-radius:8px;
                padding:14px 16px;margin-bottom:10px;transition:border-color 0.15s">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;min-width:0">
        {logo_html}
        <div style="min-width:0;flex:1">
          <div style="font-weight:600;font-size:13px;color:#e6e9f0;
                      white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{ticker}</div>
          <div style="font-size:10px;color:#8b93a7;
                      white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{name}</div>
        </div>
      </div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:18px;
                  font-weight:600;color:#e6e9f0;line-height:1.1;
                  white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
        ${price:,.2f}
      </div>
      <div style="display:flex;align-items:center;justify-content:space-between;margin-top:6px">
        <span style="color:{color};font-family:'IBM Plex Mono',monospace;
                     font-size:12px;font-weight:600">{arrow} {change_pct:+.2f}%</span>
        {extra}
      </div>
      {volume_html}
    </div>
    """


def render_ticker_grid(ticker_data: dict, cols: int = 4) -> None:
    """Render a grid of ticker cards with N columns. ticker_data: {ticker: {price, change_pct, volume}}."""
    items = list(ticker_data.items())
    for row_start in range(0, len(items), cols):
        row_items = items[row_start:row_start + cols]
        columns = st.columns(cols)
        for col, (ticker, d) in zip(columns, row_items):
            with col:
                st.markdown(
                    ticker_card(
                        ticker,
                        d.get("price", 0),
                        d.get("change_pct", 0),
                        volume=d.get("volume"),
                    ),
                    unsafe_allow_html=True,
                )


# ── Source badges for news feed ──────────────────────────────────────────────

SOURCE_META = {
    "hackernews":     {"label": "HN",      "color": "#ff6600", "icon": "Y"},
    "arxiv":          {"label": "ArXiv",   "color": "#b31b1b", "icon": "📜"},
    "reddit":         {"label": "Reddit",  "color": "#ff4500", "icon": "®"},
    "github":         {"label": "GitHub",  "color": "#6e40c9", "icon": "⚡"},
    "rss":            {"label": "RSS",     "color": "#f26522", "icon": "📡"},
    "finance":        {"label": "Yahoo",   "color": "#720e9e", "icon": "Y!"},
    "stackoverflow":  {"label": "SO",      "color": "#f48024", "icon": "🛒"},
    "fred":           {"label": "FRED",    "color": "#0f4d92", "icon": "$"},
    "fear_greed":     {"label": "F&G",     "color": "#e3b341", "icon": "😱"},
    "edgar":          {"label": "SEC",     "color": "#003366", "icon": "🏛"},
    "options":        {"label": "OPTS",    "color": "#22d472", "icon": "📊"},
    "congress":       {"label": "CONG",    "color": "#bf0a30", "icon": "🏛"},
    "finra":          {"label": "FINRA",   "color": "#005bbb", "icon": "📉"},
    "gdelt":          {"label": "GDELT",   "color": "#4a90e2", "icon": "🌐"},
    "stocktwits":     {"label": "ST",      "color": "#40b0c8", "icon": "💬"},
    "coingecko":      {"label": "Crypto",  "color": "#8dc63f", "icon": "🦎"},
    "credit":         {"label": "Credit",  "color": "#9b59b6", "icon": "💳"},
}


def source_badge(source: str) -> str:
    """Return HTML for a source badge."""
    meta = SOURCE_META.get(source, {"label": (source or "?").upper()[:5], "color": "#5a6378", "icon": "?"})
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:4px;'
        f'background:{meta["color"]}1f;color:{meta["color"]};'
        f'font-size:10px;font-weight:700;letter-spacing:0.04em;'
        f'border:1px solid {meta["color"]}44;font-family:Inter,sans-serif">'
        f'{meta["label"]}</span>'
    )


# ── News item card with logo, title, preview, score ──────────────────────────

def news_item_card(item: dict) -> str:
    """Render a single news item as a clean card."""
    sent = item.get("sentiment_label") or "neutral"
    icon = "▲" if sent == "bullish" else "▼" if sent == "bearish" else "·"
    color = "#00d68f" if sent == "bullish" else "#ff5773" if sent == "bearish" else "#8b93a7"
    src = (item.get("source") or "?").lower()
    title = (item.get("title") or "—")[:120]
    url = item.get("url") or "#"
    score = item.get("terminal_score") or 0
    preview = (item.get("preview") or "")[:200]

    return f"""
    <div style="background:#131825;border:1px solid #1f2937;border-radius:6px;
                padding:12px 16px;margin-bottom:8px;transition:all 0.15s">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;flex-wrap:wrap">
        <span style="color:{color};font-weight:700;font-size:14px">{icon}</span>
        {source_badge(src)}
        <span style="margin-left:auto;color:#5a6378;font-size:11px;font-family:IBM Plex Mono,monospace">
          {score:.0f}pts
        </span>
      </div>
      <a href="{url}" target="_blank" rel="noopener" style="text-decoration:none">
        <div style="color:#e6e9f0;font-weight:500;font-size:14px;line-height:1.4;
                    margin-bottom:6px;cursor:pointer">{title}</div>
      </a>
      {('<div style="color:#8b93a7;font-size:12px;line-height:1.5">' + preview + '</div>') if preview else ''}
    </div>
    """


# ── Regime card ──────────────────────────────────────────────────────────────

def regime_card(regime: dict) -> str:
    """Render a polished regime card."""
    label = regime.get("label", "—")
    desc  = regime.get("description", "No regime description.")
    conf  = regime.get("confidence_pct", 0)
    trans = (regime.get("transition_risk", "—") or "—").upper()

    color_map = {
        "Goldilocks": "#00d68f", "Reflation": "#ffaa00",
        "Stagflation": "#ff5773", "Deflation/Recession": "#4da6ff",
    }
    color = color_map.get(label, "#888")

    growth   = regime.get("growth_score", 0)
    inflation = regime.get("inflation_score", 0)

    favors = regime.get("favors") or []
    avoids = regime.get("avoids") or []

    favors_html = ""
    if favors:
        chips = "".join(
            f'<span style="display:inline-block;padding:3px 8px;border-radius:10px;'
            f'background:#00d68f1f;color:#00d68f;font-size:11px;font-weight:600;'
            f'margin:2px 4px 2px 0">{f}</span>'
            for f in favors[:6]
        )
        favors_html = f'<div style="margin-top:10px"><b style="color:#8b93a7;font-size:10px;letter-spacing:0.08em;text-transform:uppercase">FAVORS</b><br>{chips}</div>'

    avoids_html = ""
    if avoids:
        chips = "".join(
            f'<span style="display:inline-block;padding:3px 8px;border-radius:10px;'
            f'background:#ff57731f;color:#ff5773;font-size:11px;font-weight:600;'
            f'margin:2px 4px 2px 0">{a}</span>'
            for a in avoids[:6]
        )
        avoids_html = f'<div style="margin-top:6px"><b style="color:#8b93a7;font-size:10px;letter-spacing:0.08em;text-transform:uppercase">AVOIDS</b><br>{chips}</div>'

    return f"""
    <div style="background:#131825;border:1px solid #1f2937;border-radius:8px;
                padding:20px;margin-bottom:14px">
      <div style="display:flex;align-items:baseline;justify-content:space-between;margin-bottom:12px">
        <div>
          <div style="font-size:10px;color:#8b93a7;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:4px">Market Regime</div>
          <div style="font-size:22px;font-weight:700;color:{color}">{label}</div>
        </div>
        <div style="text-align:right">
          <div style="font-size:24px;font-weight:700;color:#e6e9f0;font-family:IBM Plex Mono,monospace">{conf:.0f}%</div>
          <div style="font-size:10px;color:#8b93a7">CONFIDENCE</div>
        </div>
      </div>
      <div style="color:#c8cce0;font-size:13px;line-height:1.5;margin-bottom:14px">{desc}</div>
      <div style="display:flex;gap:14px;margin-bottom:8px">
        <div style="flex:1">
          <div style="font-size:10px;color:#8b93a7;letter-spacing:0.08em">GROWTH</div>
          <div style="font-family:IBM Plex Mono,monospace;color:{('#00d68f' if growth >= 0 else '#ff5773')};font-weight:600">{growth:+.3f}</div>
        </div>
        <div style="flex:1">
          <div style="font-size:10px;color:#8b93a7;letter-spacing:0.08em">INFLATION</div>
          <div style="font-family:IBM Plex Mono,monospace;color:{('#ffaa00' if inflation >= 0 else '#4da6ff')};font-weight:600">{inflation:+.3f}</div>
        </div>
        <div style="flex:1">
          <div style="font-size:10px;color:#8b93a7;letter-spacing:0.08em">TRANSITION</div>
          <div style="color:#e6e9f0;font-weight:600">{trans}</div>
        </div>
      </div>
      {favors_html}
      {avoids_html}
    </div>
    """


def _format_volume(v: int) -> str:
    """1234567 → 1.23M, 1234 → 1.23K"""
    if v >= 1_000_000_000:
        return f"{v / 1_000_000_000:.2f}B"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"{v / 1_000:.1f}K"
    return str(v)
