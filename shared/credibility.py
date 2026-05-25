"""Source credibility weights for sentiment aggregation.

Higher weight → source carries more signal. Based on Reuters Institute
Digital News Report credibility surveys + traditional financial-media tiers.
"""
from __future__ import annotations
import re

# Tier 1 — top financial primary sources (regulator / direct filings)
TIER_1_REGULATORY = 1.0
# Tier 2 — major wire services with editorial standards
TIER_2_WIRE = 0.95
# Tier 3 — established financial media
TIER_3_FINANCIAL_MEDIA = 0.85
# Tier 4 — established general business news
TIER_4_BUSINESS_NEWS = 0.70
# Tier 5 — mainstream news
TIER_5_MAINSTREAM = 0.55
# Tier 6 — community / aggregator
TIER_6_COMMUNITY = 0.35
# Tier 7 — social signal (high noise)
TIER_7_SOCIAL = 0.20

# Default for unknown sources
DEFAULT_WEIGHT = 0.45


# Source ID (pipeline source name) → weight
SOURCE_WEIGHTS = {
    "edgar":        TIER_1_REGULATORY,     # SEC filings — primary source
    "congress":     TIER_1_REGULATORY,     # Congressional disclosures
    "finra":        TIER_1_REGULATORY,     # FINRA short interest reports
    "fred":         TIER_1_REGULATORY,     # Federal Reserve data
    "credit":       TIER_1_REGULATORY,     # ICE BofA via FRED
    "options":      TIER_2_WIRE,           # OPRA options flow

    "fear_greed":   TIER_3_FINANCIAL_MEDIA, # CNN F&G index — composite
    "coingecko":    TIER_3_FINANCIAL_MEDIA,
    "finance":      TIER_3_FINANCIAL_MEDIA, # Yahoo Finance feed
    "stocktwits":   TIER_6_COMMUNITY,      # Retail social

    "rss":          TIER_3_FINANCIAL_MEDIA, # depends on domain (see RSS_DOMAIN_WEIGHTS)
    "arxiv":        TIER_3_FINANCIAL_MEDIA, # peer-reviewed research
    "github":       TIER_4_BUSINESS_NEWS,
    "stackoverflow": TIER_5_MAINSTREAM,
    "hackernews":   TIER_5_MAINSTREAM,     # high quality but social aggregator
    "gdelt":        TIER_5_MAINSTREAM,     # broad news aggregator

    "reddit":       TIER_7_SOCIAL,
}


# RSS sources span many domains — weight by domain authority
RSS_DOMAIN_WEIGHTS = {
    # Tier 2 — wire services
    "reuters.com":      TIER_2_WIRE,
    "bloomberg.com":    TIER_2_WIRE,
    "ap.org":           TIER_2_WIRE,
    "ft.com":           TIER_2_WIRE,

    # Tier 3 — financial media
    "wsj.com":          TIER_3_FINANCIAL_MEDIA,
    "marketwatch.com":  TIER_3_FINANCIAL_MEDIA,
    "barrons.com":      TIER_3_FINANCIAL_MEDIA,
    "economist.com":    TIER_3_FINANCIAL_MEDIA,
    "morningstar.com":  TIER_3_FINANCIAL_MEDIA,
    "sec.gov":          TIER_1_REGULATORY,
    "federalreserve.gov": TIER_1_REGULATORY,

    # Tier 4 — business news
    "cnbc.com":         TIER_4_BUSINESS_NEWS,
    "businessinsider.com": TIER_4_BUSINESS_NEWS,
    "forbes.com":       TIER_4_BUSINESS_NEWS,
    "fortune.com":      TIER_4_BUSINESS_NEWS,
    "techcrunch.com":   TIER_4_BUSINESS_NEWS,

    # Tier 5 — mainstream
    "bbc.com":          TIER_5_MAINSTREAM,
    "bbc.co.uk":        TIER_5_MAINSTREAM,
    "nytimes.com":      TIER_5_MAINSTREAM,
    "theguardian.com":  TIER_5_MAINSTREAM,
    "axios.com":        TIER_5_MAINSTREAM,

    # Tier 6 — aggregators / community
    "seekingalpha.com": TIER_6_COMMUNITY,
    "zerohedge.com":    TIER_6_COMMUNITY,
    "fool.com":         TIER_6_COMMUNITY,
}


def credibility_weight(source: str, url: str | None = None) -> float:
    """Return credibility weight 0-1 for a source.

    For RSS items, the URL is used to look up the publishing domain.
    """
    if not source:
        return DEFAULT_WEIGHT
    source = source.lower().strip()

    # For RSS, the URL domain determines the weight
    if source == "rss" and url:
        domain = _extract_domain(url)
        if domain:
            for known_domain, weight in RSS_DOMAIN_WEIGHTS.items():
                if known_domain in domain:
                    return weight
        return TIER_4_BUSINESS_NEWS

    return SOURCE_WEIGHTS.get(source, DEFAULT_WEIGHT)


def weighted_sentiment(items: list[dict]) -> dict:
    """Aggregate sentiment across items, weighted by source credibility.

    Returns:
        {bullish_pct, bearish_pct, neutral_pct, weighted_score, n_items}
    """
    if not items:
        return {"bullish_pct": 0, "bearish_pct": 0, "neutral_pct": 0,
                "weighted_score": 0.0, "n_items": 0}

    bull_w = bear_w = neutral_w = total_w = 0.0
    raw_score_sum = 0.0
    for it in items:
        if not isinstance(it, dict):
            continue
        src = it.get("source", "")
        url = it.get("url", "")
        w = credibility_weight(src, url)
        total_w += w

        label = it.get("sentiment_label") or "neutral"
        if label == "bullish":
            bull_w += w
        elif label == "bearish":
            bear_w += w
        else:
            neutral_w += w

        # Numeric score if available (-1..1)
        score = it.get("sentiment_score")
        if score is not None:
            try:
                raw_score_sum += float(score) * w
            except (TypeError, ValueError):
                pass

    if total_w == 0:
        return {"bullish_pct": 0, "bearish_pct": 0, "neutral_pct": 100,
                "weighted_score": 0.0, "n_items": len(items)}

    return {
        "bullish_pct":    round(bull_w / total_w * 100, 1),
        "bearish_pct":    round(bear_w / total_w * 100, 1),
        "neutral_pct":    round(neutral_w / total_w * 100, 1),
        "weighted_score": round(raw_score_sum / total_w, 4),
        "n_items":        len(items),
    }


def _extract_domain(url: str) -> str | None:
    """Extract registrable domain (foo.bar.com → bar.com)."""
    if not url:
        return None
    match = re.search(r"https?://([^/]+)", url.lower())
    if not match:
        return None
    host = match.group(1)
    parts = host.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host
