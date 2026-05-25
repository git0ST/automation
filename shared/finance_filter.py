"""Financial relevance filter — every article must be finance/markets-related.

Used at the source layer (pre-fetch filter) AND scoring layer
(terminal_score multiplier). Without this, general HN/Reddit/RSS content
pollutes the intelligence feed with off-topic articles.
"""
from __future__ import annotations
import re

# ── Ticker universe — explicit watchlist + S&P 500 mega cap ──────────────────
TICKERS = frozenset({
    # Mega caps
    "NVDA", "AAPL", "MSFT", "GOOGL", "GOOG", "META", "AMZN", "TSLA", "AVGO",
    "ORCL", "BRK.B", "BRK-B", "BRKB",
    # Semis
    "AMD", "INTC", "QCOM", "ARM", "SMCI", "TSM", "MU", "MRVL", "ASML", "LRCX",
    "AMAT", "KLAC", "NXPI", "ON",
    # Software
    "CRM", "ADBE", "NOW", "SNOW", "PLTR", "DDOG", "MDB", "NET", "CRWD", "ZS",
    "PANW", "FTNT", "OKTA", "SHOP", "TEAM", "WDAY",
    # Financials
    "JPM", "GS", "MS", "BAC", "WFC", "C", "BLK", "V", "MA", "AXP", "SCHW",
    "USB", "PNC", "TFC", "COF", "SPGI", "MCO", "CB", "AIG", "PYPL",
    # Energy
    "XOM", "CVX", "COP", "SLB", "EOG", "OXY", "PSX", "VLO", "MPC", "PXD",
    # Healthcare
    "UNH", "LLY", "JNJ", "MRK", "PFE", "ABBV", "TMO", "ABT", "DHR", "AMGN",
    "BMY", "GILD", "MDT", "ISRG", "SYK",
    # Consumer
    "WMT", "COST", "HD", "MCD", "NKE", "SBUX", "TGT", "LOW", "DIS", "NFLX",
    "BKNG", "ABNB", "CMG", "LULU",
    # Communication
    "VZ", "T", "TMUS", "CMCSA", "CHTR", "EA", "TTWO", "RBLX",
    # Industrials
    "BA", "CAT", "GE", "RTX", "HON", "UPS", "FDX", "DE", "LMT", "NOC",
    "GD", "UNP", "CSX",
    # Indices/ETFs
    "SPY", "QQQ", "IWM", "DIA", "VTI", "GLD", "SLV", "TLT", "HYG", "LQD",
    "EEM", "VEA", "VWO", "ARKK", "XLK", "XLF", "XLE", "XLV", "XLY", "XLP",
    # Crypto (Yahoo format)
    "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "MATIC", "AVAX", "DOT",
    # Indices (Yahoo format)
    "^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX", "^FTSE", "^N225", "^HSI",
    "^STOXX50E", "^TNX", "^FVX",
})

# ── Finance + macro keywords (case-insensitive, word boundary matched) ──────
FINANCE_KEYWORDS = frozenset({
    # Markets
    "stock", "stocks", "equity", "equities", "market", "markets", "index",
    "indices", "etf", "etfs", "futures", "options", "derivative", "derivatives",
    "bond", "bonds", "treasury", "treasuries", "yield", "yields",
    # Macro
    "inflation", "cpi", "ppi", "pce", "gdp", "unemployment", "jobless",
    "payrolls", "nfp", "fomc", "fed", "fed funds", "interest rate", "rate cut",
    "rate hike", "powell", "hawkish", "dovish", "tightening", "easing",
    "stimulus", "quantitative easing", "qe", "qt", "balance sheet",
    # Trading
    "trading", "trader", "investor", "hedge fund", "institutional", "retail",
    "volume", "volatility", "vix", "rally", "selloff", "correction", "bear",
    "bull", "bullish", "bearish", "long", "short", "squeeze", "liquidity",
    "leverage", "margin", "derivative", "swap", "credit default",
    # Corporate
    "earnings", "revenue", "guidance", "outlook", "forecast", "beat", "miss",
    "merger", "acquisition", "ipo", "spinoff", "buyback", "dividend",
    "insider trading", "insider buy", "insider sell", "10-k", "10-q", "8-k",
    "sec filing", "proxy", "shareholders",
    # Sectors
    "semiconductor", "semiconductors", "chip", "chips", "ai chip", "ai stock",
    "biotech", "pharmaceutical", "ev", "electric vehicle", "renewable",
    "fintech", "saas", "cloud computing", "cybersecurity",
    # Macro themes
    "recession", "soft landing", "hard landing", "deflation", "stagflation",
    "goldilocks", "reflation", "yield curve", "inversion", "spread",
    "credit spread", "junk bond", "high yield", "investment grade",
    # Commodities
    "oil", "crude", "wti", "brent", "natural gas", "gasoline", "gold",
    "silver", "copper", "platinum", "wheat", "corn", "soybean", "opec",
    # FX / crypto
    "forex", "fx", "dollar", "dxy", "euro", "yen", "yuan", "renminbi",
    "currency", "exchange rate", "crypto", "cryptocurrency", "bitcoin",
    "ethereum", "stablecoin", "defi",
    # Banks / regulators
    "central bank", "ecb", "boj", "boe", "rbi", "pboc", "treasury", "sec",
    "cftc", "finra", "basel", "regulation",
    # Investment firms
    "blackrock", "vanguard", "fidelity", "berkshire", "buffett", "ackman",
    "burry", "goldman", "jpmorgan", "morgan stanley", "citigroup",
})

# Strong (single-word match → finance-relevant)
STRONG_KEYWORDS = frozenset({
    "earnings", "cpi", "ppi", "pce", "fomc", "fed", "vix", "ipo", "nasdaq",
    "s&p", "sp500", "djia", "nikkei", "ftse", "tariff", "tariffs", "treasury",
    "powell", "yellen", "etf", "options flow", "hedge fund", "wallstreet",
    "wall street",
})

# Bad keywords that disqualify content (anti-spam / off-topic guard)
BAD_KEYWORDS = frozenset({
    "encyclical", "vatican", "pope", "papal", "religion", "spiritual",
    "celebrity", "kardashian", "taylor swift", "music album", "movie release",
    "video game", "esports", "league of legends", "minecraft", "fortnite",
    "anime", "manga", "kpop",
    # Pure-tech non-financial
    "kubernetes tutorial", "rust crate", "javascript framework",
    "css trick", "react hook", "pytorch model", "tensorflow",
    # Hobby / lifestyle
    "recipe", "vegan", "diet", "marathon", "yoga", "meditation",
})


# Compiled regex patterns for fast matching
_TICKER_PATTERN = re.compile(
    r"\b\$?([A-Z]{1,5}(?:\.[A-Z])?|\^[A-Z]{2,5})\b"
)
_DOLLAR_TICKER_PATTERN = re.compile(r"\$([A-Z]{1,5})\b")


def extract_tickers(text: str) -> list[str]:
    """Extract probable ticker symbols from text. Validates against TICKERS set."""
    if not text:
        return []
    found = set()
    # $TICKER format is unambiguous
    for m in _DOLLAR_TICKER_PATTERN.finditer(text):
        sym = m.group(1).upper()
        if sym in TICKERS:
            found.add(sym)
    # Plain TICKER format — validate against universe to avoid false positives
    # (e.g. "USA" is not a ticker, but matches the pattern)
    for m in _TICKER_PATTERN.finditer(text):
        sym = m.group(1).upper()
        if sym in TICKERS:
            found.add(sym)
    return sorted(found)


def finance_relevance(title: str, preview: str = "") -> tuple[bool, float, list[str]]:
    """Return (is_relevant, score 0-1, matched_evidence).

    Decision logic:
      1. Hard-fail on BAD_KEYWORDS in title  → (False, 0.0)
      2. Strong keyword match in title       → (True, ≥0.7)
      3. Ticker symbol in title or preview   → (True, ≥0.6)
      4. ≥2 finance keywords in title+preview → (True, score = matches/10)
      5. <2 keywords → (False, score)
    """
    text = f"{title or ''} {preview or ''}".lower()
    title_l = (title or "").lower()

    # 1. Hard-fail on bad keywords in title
    for bad in BAD_KEYWORDS:
        if bad in title_l:
            return (False, 0.0, [f"bad:{bad}"])

    evidence: list[str] = []

    # 2. Strong keyword in title → high confidence
    for kw in STRONG_KEYWORDS:
        if kw in title_l:
            evidence.append(f"strong:{kw}")
    if evidence:
        return (True, min(1.0, 0.7 + 0.1 * len(evidence)), evidence)

    # 3. Ticker in title or preview
    tickers = extract_tickers(f"{title or ''} {preview or ''}")
    if tickers:
        evidence.extend(f"ticker:{t}" for t in tickers[:3])
        return (True, min(1.0, 0.6 + 0.1 * len(tickers)), evidence)

    # 4. Finance keyword count across title + preview
    keyword_matches = []
    for kw in FINANCE_KEYWORDS:
        # Word-boundary match (multi-word phrases ok)
        if re.search(r"\b" + re.escape(kw) + r"\b", text):
            keyword_matches.append(kw)
            if len(keyword_matches) >= 5:  # cap evidence
                break
    score = min(1.0, len(keyword_matches) / 5)

    if len(keyword_matches) >= 2:
        evidence.extend(f"kw:{kw}" for kw in keyword_matches[:5])
        return (True, max(0.4, score), evidence)

    return (False, score, evidence)


def filter_items(items: list[dict], min_score: float = 0.4) -> list[dict]:
    """Filter a list of pipeline items, keeping only finance-relevant ones.

    Annotates each kept item with `finance_score` + `entities`.
    """
    kept = []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = it.get("title", "")
        preview = it.get("preview", "")
        is_rel, score, evidence = finance_relevance(title, preview)
        if not is_rel or score < min_score:
            continue
        it["finance_score"] = round(score, 3)
        it["entities"] = extract_tickers(f"{title} {preview}")
        kept.append(it)
    return kept
