"""Single source of truth for the opportunity-scan universe.

Both the live Streamlit scanner (streamlit/pages/6_Opportunities.py) and the
headless pipeline scanner (projects/daily_digest/agents/opportunity_runner.py)
import from here so the two paths can never silently diverge in coverage.

Diversified across all 11 GICS sectors so no segment of the market can fall
through the cracks. Pure data — no third-party imports, safe to import anywhere.
"""
from __future__ import annotations

# Sector group → constituent tickers. Organized so coverage gaps are obvious.
UNIVERSE_BY_SECTOR: dict[str, list[str]] = {
    "Mega Tech":     ["NVDA", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "AVGO", "ORCL"],
    "Semis":         ["AMD", "INTC", "QCOM", "ARM", "SMCI", "TSM", "MU", "MRVL", "TXN"],
    "Software":      ["CRM", "ADBE", "NOW", "PLTR", "CRWD", "PANW", "SHOP", "INTU", "CSCO", "ACN", "IBM"],
    "Communication": ["NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS"],
    "Discretionary": ["TSLA", "HD", "MCD", "NKE", "SBUX", "LOW", "BKNG"],
    "Staples":       ["WMT", "COST", "PG", "KO", "PEP", "PM", "MDLZ"],
    "Financials":    ["JPM", "GS", "MS", "BAC", "WFC", "C", "SCHW", "BRK-B", "V", "MA", "AXP", "BLK", "SPGI"],
    "Energy":        ["XOM", "CVX", "COP", "SLB", "EOG", "OXY", "MPC"],
    "Healthcare":    ["UNH", "LLY", "JNJ", "MRK", "ABBV", "PFE", "TMO", "ABT", "DHR", "AMGN", "ISRG"],
    "Industrials":   ["BA", "CAT", "GE", "RTX", "HON", "UPS", "LMT", "DE", "MMM"],
    "Materials":     ["LIN", "FCX", "NEM", "APD", "SHW"],
    "Real Estate":   ["PLD", "AMT", "EQIX"],
    "Utilities":     ["NEE", "SO", "DUK"],
}

# Flattened broad default (~99 names, every sector represented)
SCAN_UNIVERSE: list[str] = [t for names in UNIVERSE_BY_SECTOR.values() for t in names]
