"""
Sentiment analysis for intelligence pipeline.

Fast path : VADER compound score for all articles (offline, <1ms/article).
Deep path : Ollama phi3:mini for top-N stories (optional, ~2s each).
Entity    : regex ticker/company detection for market correlation.
"""

import re
from typing import Optional

# ── VADER ─────────────────────────────────────────────────────────────────────

_vader = None

def _get_vader():
    global _vader
    if _vader is None:
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            _vader = SentimentIntensityAnalyzer()
        except ImportError:
            pass
    return _vader


def vader_score(text: str) -> tuple[float, str]:
    """Return (compound, label) for a piece of text."""
    va = _get_vader()
    if va is None:
        return 0.0, "neutral"
    scores = va.polarity_scores(text)
    c = scores["compound"]
    if c >= 0.05:  return c, "bullish"
    if c <= -0.05: return c, "bearish"
    return c, "neutral"


def score_stage_sentiment(items: list[dict]) -> list[dict]:
    """
    Enrich every item with sentiment_score and sentiment_label using VADER.
    Works on title + preview combined for better accuracy.
    """
    for item in items:
        text = (item.get("title") or "") + " " + (item.get("preview") or "")
        sc, lb = vader_score(text[:512])
        item["sentiment_score"] = round(sc, 4)
        item["sentiment_label"] = lb
    return items


# ── Entity / Ticker Extraction ────────────────────────────────────────────────

TICKER_MAP = {
    # Major indices
    "S&P": "^GSPC", "S&P 500": "^GSPC", "NASDAQ": "^IXIC", "DOW": "^DJI",
    # Mega-caps
    "NVIDIA": "NVDA", "APPLE": "AAPL", "MICROSOFT": "MSFT", "GOOGLE": "GOOGL",
    "ALPHABET": "GOOGL", "META": "META", "AMAZON": "AMZN", "TESLA": "TSLA",
    "NETFLIX": "NFLX", "AMD": "AMD", "INTEL": "INTC", "QUALCOMM": "QCOM",
    "OPENAI": "MSFT",  # proxy
    "ANTHROPIC": "AMZN",  # proxy
    # Crypto
    "BITCOIN": "BTC", "ETHEREUM": "ETH", "SOLANA": "SOL",
    # Macro
    "FED": "FEDFUNDS", "FEDERAL RESERVE": "FEDFUNDS",
    "TREASURY": "DGS10", "INFLATION": "CPIAUCSL", "CPI": "CPIAUCSL",
}

# Direct ticker symbol regex (e.g. $NVDA or standalone uppercase 2-5 chars)
_TICKER_RE = re.compile(r'\$([A-Z]{1,5})\b|(?<![A-Za-z])([A-Z]{2,5})(?![a-z])')
_KNOWN_TICKERS = {
    "NVDA", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "TSLA",
    "AMD", "INTC", "NFLX", "QCOM", "CRM", "ORCL", "IBM",
    "BTC", "ETH", "SOL", "BNB", "XRP",
    "SPY", "QQQ", "IWM", "VIX",
}


def extract_entities(text: str) -> list[str]:
    """Extract likely ticker/company references from text."""
    text_up = text.upper()
    found = set()

    # Named company lookup
    for name, ticker in TICKER_MAP.items():
        if name in text_up:
            found.add(ticker)

    # $TICKER or ALLCAPS pattern
    for m in _TICKER_RE.finditer(text):
        t = (m.group(1) or m.group(2) or "").upper()
        if t in _KNOWN_TICKERS:
            found.add(t)

    return sorted(found)


def enrich_entities(items: list[dict]) -> list[dict]:
    for item in items:
        text = (item.get("title") or "") + " " + (item.get("preview") or "")
        item["entities"] = extract_entities(text[:400])
    return items


# ── Alert Generation ──────────────────────────────────────────────────────────

def detect_market_alerts(market_items: list[dict], threshold_pct: float = 3.0) -> list[dict]:
    """Return alert dicts for significant market moves."""
    alerts = []
    for m in market_items:
        pct = abs(m.get("change_pct", 0))
        if pct >= threshold_pct:
            direction = "up" if m["change_pct"] > 0 else "down"
            priority  = 2 if pct >= 5 else 1
            alerts.append({
                "type":     "market_move",
                "title":    f"{m['ticker']} {'+' if m['change_pct']>0 else ''}{m['change_pct']:.2f}%",
                "body":     f"{m['name']} moved {direction} {pct:.1f}% — significant move",
                "priority": priority,
                "ticker":   m["ticker"],
            })
    return alerts


def compute_sentiment_summary(items: list[dict]) -> dict:
    """Aggregate sentiment across all scored items."""
    scores = [i["sentiment_score"] for i in items if "sentiment_score" in i]
    if not scores:
        return {"bullish_pct": 0, "bearish_pct": 0, "neutral_pct": 0, "avg": 0.0}
    n = len(scores)
    bullish = sum(1 for s in scores if s >= 0.05)
    bearish = sum(1 for s in scores if s <= -0.05)
    neutral = n - bullish - bearish
    return {
        "bullish_pct": round(bullish / n * 100),
        "bearish_pct": round(bearish / n * 100),
        "neutral_pct": round(neutral / n * 100),
        "avg":         round(sum(scores) / n, 4),
        "total":       n,
    }
