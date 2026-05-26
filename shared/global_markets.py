"""Global markets registry — indices, forex pairs, commodities organized by region.

Single source of truth for all non-US market data. Other modules import
from here rather than defining their own registries.

Tickers use Yahoo Finance symbols (free, broad coverage).
"""
from __future__ import annotations


# ── Equity indices by region ────────────────────────────────────────────────
REGIONS = {
    "Americas": {
        "^GSPC":    {"name": "S&P 500",        "country": "US", "flag": "🇺🇸"},
        "^IXIC":    {"name": "Nasdaq Comp.",   "country": "US", "flag": "🇺🇸"},
        "^DJI":     {"name": "Dow Jones",      "country": "US", "flag": "🇺🇸"},
        "^RUT":     {"name": "Russell 2000",   "country": "US", "flag": "🇺🇸"},
        "^VIX":     {"name": "VIX",            "country": "US", "flag": "🇺🇸"},
        "^GSPTSE":  {"name": "TSX Composite",  "country": "Canada", "flag": "🇨🇦"},
        "^BVSP":    {"name": "Bovespa",        "country": "Brazil", "flag": "🇧🇷"},
        "^MXX":     {"name": "IPC Mexico",     "country": "Mexico", "flag": "🇲🇽"},
    },
    "Europe": {
        "^FTSE":     {"name": "FTSE 100",        "country": "UK",      "flag": "🇬🇧"},
        "^GDAXI":    {"name": "DAX 40",          "country": "Germany", "flag": "🇩🇪"},
        "^FCHI":     {"name": "CAC 40",          "country": "France",  "flag": "🇫🇷"},
        "^STOXX50E": {"name": "Euro Stoxx 50",   "country": "EU",      "flag": "🇪🇺"},
        "^AEX":      {"name": "AEX",             "country": "Netherlands", "flag": "🇳🇱"},
        "^IBEX":     {"name": "IBEX 35",         "country": "Spain",   "flag": "🇪🇸"},
        "FTSEMIB.MI": {"name": "FTSE MIB",       "country": "Italy",   "flag": "🇮🇹"},
        "^SSMI":     {"name": "SMI",             "country": "Switzerland", "flag": "🇨🇭"},
        "^OMX":      {"name": "OMX Stockholm 30", "country": "Sweden",  "flag": "🇸🇪"},
    },
    "Asia-Pacific": {
        "^N225":     {"name": "Nikkei 225",      "country": "Japan",    "flag": "🇯🇵"},
        "^HSI":      {"name": "Hang Seng",       "country": "Hong Kong","flag": "🇭🇰"},
        "000001.SS": {"name": "Shanghai Comp.",  "country": "China",    "flag": "🇨🇳"},
        "399001.SZ": {"name": "Shenzhen Comp.",  "country": "China",    "flag": "🇨🇳"},
        "^KS11":     {"name": "KOSPI",           "country": "South Korea","flag": "🇰🇷"},
        "^TWII":     {"name": "Taiwan Weighted", "country": "Taiwan",   "flag": "🇹🇼"},
        "^STI":      {"name": "Straits Times",   "country": "Singapore","flag": "🇸🇬"},
        "^AXJO":     {"name": "ASX 200",         "country": "Australia","flag": "🇦🇺"},
        "^NSEI":     {"name": "Nifty 50",        "country": "India",    "flag": "🇮🇳"},
        "^BSESN":    {"name": "Sensex",          "country": "India",    "flag": "🇮🇳"},
    },
    "Emerging": {
        "^JSE":      {"name": "JSE All Share",   "country": "South Africa", "flag": "🇿🇦"},
        "^XU100":    {"name": "BIST 100",        "country": "Turkey",     "flag": "🇹🇷"},
        "^TA125.TA": {"name": "TA-125",          "country": "Israel",     "flag": "🇮🇱"},
        "^MERV":     {"name": "Merval",          "country": "Argentina",  "flag": "🇦🇷"},
    },
}


# ── Forex pairs ─────────────────────────────────────────────────────────────
FOREX = {
    "majors": {
        "DX-Y.NYB": {"name": "DXY (Dollar Index)", "flag": "💵"},
        "EURUSD=X": {"name": "EUR / USD",          "flag": "🇪🇺🇺🇸"},
        "GBPUSD=X": {"name": "GBP / USD",          "flag": "🇬🇧🇺🇸"},
        "USDJPY=X": {"name": "USD / JPY",          "flag": "🇺🇸🇯🇵"},
        "USDCHF=X": {"name": "USD / CHF",          "flag": "🇺🇸🇨🇭"},
        "AUDUSD=X": {"name": "AUD / USD",          "flag": "🇦🇺🇺🇸"},
        "USDCAD=X": {"name": "USD / CAD",          "flag": "🇺🇸🇨🇦"},
        "NZDUSD=X": {"name": "NZD / USD",          "flag": "🇳🇿🇺🇸"},
    },
    "crosses": {
        "EURGBP=X": {"name": "EUR / GBP", "flag": "🇪🇺🇬🇧"},
        "EURJPY=X": {"name": "EUR / JPY", "flag": "🇪🇺🇯🇵"},
        "GBPJPY=X": {"name": "GBP / JPY", "flag": "🇬🇧🇯🇵"},
        "AUDJPY=X": {"name": "AUD / JPY", "flag": "🇦🇺🇯🇵"},
        "EURCHF=X": {"name": "EUR / CHF", "flag": "🇪🇺🇨🇭"},
    },
    "emerging": {
        "USDCNY=X": {"name": "USD / CNY", "flag": "🇺🇸🇨🇳"},
        "USDINR=X": {"name": "USD / INR", "flag": "🇺🇸🇮🇳"},
        "USDBRL=X": {"name": "USD / BRL", "flag": "🇺🇸🇧🇷"},
        "USDMXN=X": {"name": "USD / MXN", "flag": "🇺🇸🇲🇽"},
        "USDZAR=X": {"name": "USD / ZAR", "flag": "🇺🇸🇿🇦"},
        "USDTRY=X": {"name": "USD / TRY", "flag": "🇺🇸🇹🇷"},
        "USDKRW=X": {"name": "USD / KRW", "flag": "🇺🇸🇰🇷"},
    },
}


# ── Commodities (already in sources/commodities.py — referenced here for unity) ─
COMMODITIES = {
    "energy":  ["CL=F", "BZ=F", "NG=F"],     # WTI, Brent, NatGas
    "metals":  ["GC=F", "SI=F", "HG=F", "PL=F"],  # Gold, Silver, Copper, Platinum
    "agri":    ["ZC=F", "ZW=F", "ZS=F"],     # Corn, Wheat, Soybeans
}


# ── Flat helpers ────────────────────────────────────────────────────────────
def all_index_symbols() -> list[str]:
    """Flat list of every index ticker across all regions."""
    syms = []
    for region in REGIONS.values():
        syms.extend(region.keys())
    return syms


def all_forex_symbols() -> list[str]:
    """Flat list of every forex pair across categories."""
    syms = []
    for cat in FOREX.values():
        syms.extend(cat.keys())
    return syms


def lookup(symbol: str) -> dict | None:
    """Find metadata for any symbol across indices + forex."""
    for region in REGIONS.values():
        if symbol in region:
            return {**region[symbol], "type": "index"}
    for cat_name, cat in FOREX.items():
        if symbol in cat:
            return {**cat[symbol], "type": "forex", "category": cat_name}
    return None
