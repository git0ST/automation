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

    # ── Expanded scanner universe — full GICS sector coverage ────────────────
    # Software & IT services
    "CRM":   {"name": "Salesforce",      "logo": "CRM",  "type": "stock", "sector": "Software"},
    "ADBE":  {"name": "Adobe",           "logo": "ADBE", "type": "stock", "sector": "Software"},
    "NOW":   {"name": "ServiceNow",      "logo": "NOW",  "type": "stock", "sector": "Software"},
    "PLTR":  {"name": "Palantir",        "logo": "PLTR", "type": "stock", "sector": "Software"},
    "CRWD":  {"name": "CrowdStrike",     "logo": "CRWD", "type": "stock", "sector": "Software"},
    "PANW":  {"name": "Palo Alto Nets",  "logo": "PANW", "type": "stock", "sector": "Software"},
    "SHOP":  {"name": "Shopify",         "logo": "SHOP", "type": "stock", "sector": "Software"},
    "INTU":  {"name": "Intuit",          "logo": "INTU", "type": "stock", "sector": "Software"},
    "CSCO":  {"name": "Cisco",           "logo": "CSCO", "type": "stock", "sector": "Tech"},
    "ACN":   {"name": "Accenture",       "logo": "ACN",  "type": "stock", "sector": "Tech"},
    "IBM":   {"name": "IBM",             "logo": "IBM",  "type": "stock", "sector": "Tech"},
    "TXN":   {"name": "Texas Instr.",    "logo": "TXN",  "type": "stock", "sector": "Semis"},

    # Communication services
    "NFLX":  {"name": "Netflix",         "logo": "NFLX", "type": "stock", "sector": "Media"},
    "DIS":   {"name": "Disney",          "logo": "DIS",  "type": "stock", "sector": "Media"},
    "CMCSA": {"name": "Comcast",         "logo": "CMCSA","type": "stock", "sector": "Media"},
    "T":     {"name": "AT&T",            "logo": "T",    "type": "stock", "sector": "Telecom"},
    "VZ":    {"name": "Verizon",         "logo": "VZ",   "type": "stock", "sector": "Telecom"},
    "TMUS":  {"name": "T-Mobile",        "logo": "TMUS", "type": "stock", "sector": "Telecom"},

    # Consumer discretionary
    "LOW":   {"name": "Lowe's",          "logo": "LOW",  "type": "stock", "sector": "Discretionary"},
    "BKNG":  {"name": "Booking",         "logo": "BKNG", "type": "stock", "sector": "Discretionary"},

    # Consumer staples
    "PG":    {"name": "Procter & Gamble","logo": "PG",   "type": "stock", "sector": "Staples"},
    "KO":    {"name": "Coca-Cola",       "logo": "KO",   "type": "stock", "sector": "Staples"},
    "PEP":   {"name": "PepsiCo",         "logo": "PEP",  "type": "stock", "sector": "Staples"},
    "PM":    {"name": "Philip Morris",   "logo": "PM",   "type": "stock", "sector": "Staples"},
    "MDLZ":  {"name": "Mondelez",        "logo": "MDLZ", "type": "stock", "sector": "Staples"},

    # Financials
    "SCHW":  {"name": "Charles Schwab",  "logo": "SCHW", "type": "stock", "sector": "Bank"},
    "AXP":   {"name": "Amex",            "logo": "AXP",  "type": "stock", "sector": "Payments"},
    "SPGI":  {"name": "S&P Global",      "logo": "SPGI", "type": "stock", "sector": "Financials"},

    # Energy
    "MPC":   {"name": "Marathon Pet.",   "logo": "MPC",  "type": "stock", "sector": "Energy"},

    # Healthcare
    "TMO":   {"name": "Thermo Fisher",   "logo": "TMO",  "type": "stock", "sector": "MedTech"},
    "ABT":   {"name": "Abbott",          "logo": "ABT",  "type": "stock", "sector": "MedTech"},
    "DHR":   {"name": "Danaher",         "logo": "DHR",  "type": "stock", "sector": "MedTech"},
    "AMGN":  {"name": "Amgen",           "logo": "AMGN", "type": "stock", "sector": "Biotech"},
    "ISRG":  {"name": "Intuitive Surg.", "logo": "ISRG", "type": "stock", "sector": "MedTech"},

    # Industrials
    "BA":    {"name": "Boeing",          "logo": "BA",   "type": "stock", "sector": "Aerospace"},
    "CAT":   {"name": "Caterpillar",     "logo": "CAT",  "type": "stock", "sector": "Industrial"},
    "GE":    {"name": "GE Aerospace",    "logo": "GE",   "type": "stock", "sector": "Aerospace"},
    "RTX":   {"name": "RTX",             "logo": "RTX",  "type": "stock", "sector": "Aerospace"},
    "HON":   {"name": "Honeywell",       "logo": "HON",  "type": "stock", "sector": "Industrial"},
    "UPS":   {"name": "UPS",             "logo": "UPS",  "type": "stock", "sector": "Industrial"},
    "LMT":   {"name": "Lockheed Martin", "logo": "LMT",  "type": "stock", "sector": "Aerospace"},
    "DE":    {"name": "Deere",           "logo": "DE",   "type": "stock", "sector": "Industrial"},
    "MMM":   {"name": "3M",              "logo": "MMM",  "type": "stock", "sector": "Industrial"},

    # Materials
    "LIN":   {"name": "Linde",           "logo": "LIN",  "type": "stock", "sector": "Materials"},
    "FCX":   {"name": "Freeport-McM.",   "logo": "FCX",  "type": "stock", "sector": "Materials"},
    "NEM":   {"name": "Newmont",         "logo": "NEM",  "type": "stock", "sector": "Materials"},
    "APD":   {"name": "Air Products",    "logo": "APD",  "type": "stock", "sector": "Materials"},
    "SHW":   {"name": "Sherwin-Will.",   "logo": "SHW",  "type": "stock", "sector": "Materials"},

    # Real estate
    "PLD":   {"name": "Prologis",        "logo": "PLD",  "type": "stock", "sector": "REIT"},
    "AMT":   {"name": "American Tower",  "logo": "AMT",  "type": "stock", "sector": "REIT"},
    "EQIX":  {"name": "Equinix",         "logo": "EQIX", "type": "stock", "sector": "REIT"},

    # Utilities
    "NEE":   {"name": "NextEra Energy",  "logo": "NEE",  "type": "stock", "sector": "Utility"},
    "SO":    {"name": "Southern Co",     "logo": "SO",   "type": "stock", "sector": "Utility"},
    "DUK":   {"name": "Duke Energy",     "logo": "DUK",  "type": "stock", "sector": "Utility"},
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

def _sparkline_svg(prices: list[float], color: str,
                   width: int = 220, height: int = 44) -> str:
    """Generate an inline SVG polyline from a price series."""
    if not prices or len(prices) < 2:
        return ""
    mn, mx = min(prices), max(prices)
    rng = mx - mn or 1
    n = len(prices)
    pts = " ".join(
        f"{i / (n - 1) * width:.1f},{height - (p - mn) / rng * (height - 4):.1f}"
        for i, p in enumerate(prices)
    )
    # Filled area under the line
    fill_pts = (
        f"0,{height} "
        + pts
        + f" {width},{height}"
    )
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" style="display:block;overflow:visible">'
        f'<defs><linearGradient id="sg{abs(hash(pts))%9999}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity="0.18"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0"/>'
        f'</linearGradient></defs>'
        f'<polygon points="{fill_pts}" fill="url(#sg{abs(hash(pts))%9999})"/>'
        f'<polyline points="{pts}" fill="none" stroke="{color}" '
        f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )


# Injected once per page load — CSS for card hover effects
_CARD_CSS = """<style>
.intl-tcard {
  background:#131825;border:1px solid #1f2937;border-radius:8px;
  padding:14px 16px;cursor:pointer;
  transition:border-color .15s,transform .15s,box-shadow .15s;
  position:relative;overflow:hidden;
}
.intl-tcard:hover {
  border-color:#2a3447;
  transform:translateY(-2px);
  box-shadow:0 6px 24px rgba(0,0,0,.45);
}
.intl-tcard .tc-spark {
  overflow:hidden;
  max-height:0;opacity:0;
  transition:max-height .22s ease,opacity .22s ease;
  margin-top:0;
}
.intl-tcard:hover .tc-spark {
  max-height:52px;opacity:1;
  margin-top:8px;
}
.intl-tcard .tc-analyze {
  opacity:0;
  transition:opacity .15s;
  font-size:10px;color:#4c8bf5;letter-spacing:.06em;
  position:absolute;top:10px;right:12px;font-weight:600;
}
.intl-tcard:hover .tc-analyze { opacity:1; }
</style>"""
_CARD_CSS_INJECTED = False


def ticker_card(ticker: str, price: float, change_pct: float,
                volume: int | None = None, extra: str = "",
                sparkline_prices: list[float] | None = None) -> str:
    """Return HTML for an interactive ticker card.

    Features:
    - Logo (38px) + Ticker and Name at equal visual weight
    - Price + % change + volume
    - Sparkline chart that fades in on hover (pure CSS, no JS)
    - ↗ Analyze hint appears on hover (navigation handled by caller button)
    """
    global _CARD_CSS_INJECTED
    css = ""
    if not _CARD_CSS_INJECTED:
        css = _CARD_CSS
        _CARD_CSS_INJECTED = True

    meta = TICKER_META.get(ticker, {})
    name = meta.get("name", ticker)
    color = "#00d68f" if change_pct >= 0 else "#ff5773"
    arrow = "▲" if change_pct >= 0 else "▼"
    logo_url = get_logo_url(ticker)
    sector = meta.get("sector", meta.get("type", ""))

    # ── Logo ──────────────────────────────────────────────────────────────────
    if logo_url:
        logo_html = (
            f'<img src="{logo_url}" alt="{ticker}" '
            f'style="width:38px;height:38px;border-radius:7px;background:#fff;padding:3px;'
            f'object-fit:contain;flex-shrink:0" '
            f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'">'
            f'<div style="display:none;width:38px;height:38px;border-radius:7px;'
            f'background:linear-gradient(135deg,#1f2937,#2a3447);align-items:center;'
            f'justify-content:center;font-weight:700;font-size:13px;color:#8b93a7;flex-shrink:0">'
            f'{ticker[:2]}</div>'
        )
    elif meta.get("country"):
        logo_html = (
            f'<div style="width:38px;height:38px;display:flex;align-items:center;'
            f'justify-content:center;font-size:26px;flex-shrink:0">'
            f'{meta["country"]}</div>'
        )
    elif meta.get("icon"):
        logo_html = (
            f'<div style="width:38px;height:38px;border-radius:7px;background:#1a2034;'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-size:18px;font-weight:700;color:#ffaa00;flex-shrink:0">'
            f'{meta["icon"]}</div>'
        )
    else:
        logo_html = (
            f'<div style="width:38px;height:38px;border-radius:7px;'
            f'background:linear-gradient(135deg,#1f2937,#2a3447);'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-weight:700;font-size:13px;color:#8b93a7;flex-shrink:0">'
            f'{ticker[:2]}</div>'
        )

    # ── Sector chip ───────────────────────────────────────────────────────────
    sector_html = (
        f'<span style="font-size:8px;padding:1px 5px;border-radius:3px;'
        f'background:#1a2034;border:1px solid #2a3447;color:#5a6378;'
        f'letter-spacing:.06em;text-transform:uppercase;white-space:nowrap">'
        f'{sector}</span>'
    ) if sector else ""

    # ── Volume ────────────────────────────────────────────────────────────────
    volume_html = ""
    if volume:
        volume_html = (
            f'<span style="font-size:10px;color:#5a6378;font-family:IBM Plex Mono,monospace">'
            f'Vol {_format_volume(volume)}</span>'
        )

    # ── Sparkline (shown on hover via CSS) ────────────────────────────────────
    spark_html = ""
    if sparkline_prices and len(sparkline_prices) >= 2:
        spark_svg = _sparkline_svg(sparkline_prices, color)
        spark_html = f'<div class="tc-spark">{spark_svg}</div>'

    return (
        f'{css}'
        f'<div class="intl-tcard">'
        f'  <div class="tc-analyze">↗ Analyze</div>'
        f'  <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">'
        f'    {logo_html}'
        f'    <div style="min-width:0;flex:1">'
        f'      <div style="font-size:13px;font-weight:700;color:#e6e9f0;'
        f'letter-spacing:.03em;line-height:1.2">{ticker}</div>'
        f'      <div style="font-size:13px;font-weight:400;color:#8b93a7;'
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1.2">{name}</div>'
        f'    </div>'
        f'    {sector_html}'
        f'  </div>'
        f'  <div style="font-family:IBM Plex Mono,monospace;font-size:20px;'
        f'font-weight:600;color:#e6e9f0;line-height:1.1">${price:,.2f}</div>'
        f'  <div style="display:flex;align-items:center;gap:10px;margin-top:5px;flex-wrap:wrap">'
        f'    <span style="color:{color};font-family:IBM Plex Mono,monospace;'
        f'font-size:13px;font-weight:600">{arrow} {change_pct:+.2f}%</span>'
        f'    {volume_html}'
        f'    {extra}'
        f'  </div>'
        f'  {spark_html}'
        f'</div>'
    )


def render_ticker_grid(ticker_data: dict, cols: int = 4,
                       sparkline_data: dict | None = None,
                       key_prefix: str = "tcard") -> None:
    """Render a responsive grid of interactive ticker cards.

    ticker_data: {ticker: {price, change_pct, volume}}
    sparkline_data: {ticker: [price, price, ...]} — shown on card hover
    key_prefix: namespaces the per-card buttons so the same ticker can appear
        in more than one grid on a page (e.g. Cards tab + Top Movers) without a
        StreamlitDuplicateElementKey collision.
    Clicking a card navigates to Stock Detail via session state.
    """
    global _CARD_CSS_INJECTED
    _CARD_CSS_INJECTED = False  # reset so CSS is injected for first card each render

    items = list(ticker_data.items())
    for row_start in range(0, len(items), cols):
        row_items = items[row_start:row_start + cols]
        columns = st.columns(cols)
        for col, (ticker, d) in zip(columns, row_items):
            with col:
                spark = (sparkline_data or {}).get(ticker)
                st.markdown(
                    ticker_card(
                        ticker,
                        d.get("price", 0),
                        d.get("change_pct", 0),
                        volume=d.get("volume"),
                        sparkline_prices=spark,
                    ),
                    unsafe_allow_html=True,
                )
                # Invisible-width button captures the click and navigates
                if st.button(
                    "↗",
                    key=f"{key_prefix}_{ticker}_{row_start}",
                    help=f"Open {ticker} in Stock Detail",
                    use_container_width=True,
                ):
                    st.session_state["detail_ticker"] = ticker
                    st.switch_page("pages/5_Stock_Detail.py")


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
