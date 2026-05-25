"""
Math Agent — Quantitative risk analytics engine.

Calculates portfolio risk metrics used by institutional investors:
  - Historical Value at Risk (VaR) — 95% & 99% confidence levels
  - Conditional VaR (CVaR / Expected Shortfall)
  - Sharpe Ratio, Sortino Ratio
  - Maximum Drawdown
  - Beta vs benchmark (S&P 500)
  - Correlation matrix
  - Rolling volatility (30-day, annualised)

All calculations run on free data from Yahoo Finance (yfinance).
Data is cached in memory — 512MB RAM safe for up to 100 stocks × 1Y.

Memory safety:
  - Process max 20 tickers per call (configurable)
  - Return lean dicts, not DataFrames

Usage:
    from agents.math_agent import compute_portfolio_risk, compute_var

    risk = await compute_portfolio_risk(["NVDA", "AAPL", "MSFT"])
    var  = await compute_var("NVDA", confidence=0.95)
"""

import asyncio
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np

# ── yfinance wrapper (cached) ─────────────────────────────────────────────────

_price_cache: dict[str, dict] = {}   # {ticker: {prices:[], dates:[], ts:float}}
PRICE_CACHE_TTL = 3600               # 1 hour

BENCHMARK = "^GSPC"   # S&P 500 as universal benchmark


async def _fetch_prices(ticker: str, period: str = "1y") -> Optional[list[float]]:
    """Fetch daily closing prices. Cached for PRICE_CACHE_TTL seconds."""
    cache_key = f"{ticker}:{period}"
    entry = _price_cache.get(cache_key)
    if entry and (asyncio.get_event_loop().time() - entry["ts"]) < PRICE_CACHE_TTL:
        return entry["prices"]

    try:
        import yfinance as yf
        loop = asyncio.get_event_loop()
        ticker_obj = await loop.run_in_executor(None, lambda: yf.Ticker(ticker))
        hist = await loop.run_in_executor(
            None,
            lambda: ticker_obj.history(period=period, interval="1d", auto_adjust=True)
        )
        if hist.empty or "Close" not in hist.columns:
            return None
        prices = hist["Close"].dropna().tolist()
        if len(prices) < 20:
            return None
        _price_cache[cache_key] = {"prices": prices, "ts": asyncio.get_event_loop().time()}
        return prices
    except Exception as e:
        print(f"[math] price fetch error {ticker}: {e}")
        return None


def _daily_returns(prices: list[float]) -> list[float]:
    """Compute daily log returns."""
    if len(prices) < 2:
        return []
    return [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices))]


def _annualised_vol(returns: list[float]) -> float:
    """Annualised volatility from daily returns (252 trading days)."""
    if len(returns) < 5:
        return 0.0
    mean = sum(returns) / len(returns)
    var  = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(var * 252)


def _sharpe(returns: list[float], risk_free_annual: float = 0.05) -> float:
    """Sharpe ratio using annualised return and volatility."""
    if len(returns) < 20:
        return 0.0
    mean_daily   = sum(returns) / len(returns)
    annualised_r = mean_daily * 252
    vol          = _annualised_vol(returns)
    if vol < 1e-9:
        return 0.0
    return (annualised_r - risk_free_annual) / vol


def _sortino(returns: list[float], risk_free_annual: float = 0.05) -> float:
    """Sortino ratio: penalises only downside volatility."""
    if len(returns) < 20:
        return 0.0
    mean_daily   = sum(returns) / len(returns)
    annualised_r = mean_daily * 252
    downside = [r for r in returns if r < 0]
    if not downside:
        return float("inf")
    downside_var = sum(r ** 2 for r in downside) / len(downside)
    downside_vol = math.sqrt(downside_var * 252)
    if downside_vol < 1e-9:
        return 0.0
    return (annualised_r - risk_free_annual) / downside_vol


def _max_drawdown(prices: list[float]) -> float:
    """Maximum peak-to-trough drawdown as a positive percentage."""
    if len(prices) < 2:
        return 0.0
    peak = prices[0]
    max_dd = 0.0
    for p in prices[1:]:
        peak   = max(peak, p)
        dd     = (peak - p) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)
    return max_dd


def _var(returns: list[float], confidence: float = 0.95) -> float:
    """
    Historical Value at Risk (not parametric — no normality assumption).
    Returns the loss (positive number) at the given confidence level.
    """
    if not returns:
        return 0.0
    sorted_r = sorted(returns)
    idx = int(len(sorted_r) * (1 - confidence))
    idx = max(0, min(idx, len(sorted_r) - 1))
    return -sorted_r[idx]   # positive loss


def _cvar(returns: list[float], confidence: float = 0.95) -> float:
    """
    Conditional VaR (Expected Shortfall) — average of losses beyond VaR.
    More conservative than VaR, preferred by institutional risk managers.
    """
    if not returns:
        return 0.0
    sorted_r   = sorted(returns)
    cutoff_idx = int(len(sorted_r) * (1 - confidence))
    cutoff_idx = max(1, cutoff_idx)
    tail       = sorted_r[:cutoff_idx]
    if not tail:
        return 0.0
    return -sum(tail) / len(tail)


def _beta(asset_rets: list[float], bench_rets: list[float]) -> float:
    """Beta of asset vs benchmark using OLS covariance method."""
    n = min(len(asset_rets), len(bench_rets))
    if n < 20:
        return 1.0
    a = asset_rets[-n:]
    b = bench_rets[-n:]
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n)) / (n - 1)
    var_b = sum((b[i] - mean_b) ** 2 for i in range(n)) / (n - 1)
    if var_b < 1e-12:
        return 1.0
    return cov / var_b


def _correlation(rets_a: list[float], rets_b: list[float]) -> float:
    """Pearson correlation between two return series."""
    n = min(len(rets_a), len(rets_b))
    if n < 5:
        return 0.0
    a = rets_a[-n:]
    b = rets_b[-n:]
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    cov  = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n)) / max(n - 1, 1)
    std_a = math.sqrt(sum((x - mean_a) ** 2 for x in a) / max(n - 1, 1))
    std_b = math.sqrt(sum((x - mean_b) ** 2 for x in b) / max(n - 1, 1))
    if std_a < 1e-9 or std_b < 1e-9:
        return 0.0
    return cov / (std_a * std_b)


# ── Public API ────────────────────────────────────────────────────────────────

async def compute_var(
    ticker:     str,
    confidence: float = 0.95,
    period:     str   = "1y",
) -> dict:
    """
    Compute Value at Risk for a single ticker.

    Returns dict with var_95, var_99, cvar_95, sharpe, sortino,
    max_drawdown, annualised_vol, beta, current_price.
    """
    prices = await _fetch_prices(ticker, period)
    if not prices:
        return {"ticker": ticker, "error": "No price data"}

    returns = _daily_returns(prices)
    bench_p = await _fetch_prices(BENCHMARK, period)
    bench_r = _daily_returns(bench_p) if bench_p else []

    return {
        "ticker":         ticker,
        "current_price":  round(prices[-1], 2),
        "period":         period,
        "observations":   len(returns),
        "var_95":         round(_var(returns, 0.95) * 100, 2),      # % daily loss at 95% conf
        "var_99":         round(_var(returns, 0.99) * 100, 2),
        "cvar_95":        round(_cvar(returns, 0.95) * 100, 2),     # Expected Shortfall 95%
        "sharpe":         round(_sharpe(returns), 3),
        "sortino":        round(_sortino(returns), 3),
        "max_drawdown":   round(_max_drawdown(prices) * 100, 2),    # % drawdown
        "annualised_vol": round(_annualised_vol(returns) * 100, 2), # % annual vol
        "beta":           round(_beta(returns, bench_r), 3) if bench_r else None,
        "total_return":   round((prices[-1] / prices[0] - 1) * 100, 2) if prices[0] else 0,
    }


async def compute_portfolio_risk(
    tickers:    list[str],
    weights:    Optional[list[float]] = None,
    period:     str = "1y",
    max_tickers: int = 20,
) -> dict:
    """
    Compute portfolio-level risk metrics for a list of tickers.

    Args:
        tickers:     List of ticker symbols (max 20 for memory safety).
        weights:     Portfolio weights (equal-weight if None).
        period:      Historical lookback period.
        max_tickers: Safety cap to prevent OOM on free-tier hosting.

    Returns:
        dict with portfolio VaR, individual metrics, and correlation matrix.
    """
    tickers = list(set(tickers))[:max_tickers]
    if not tickers:
        return {"error": "No tickers provided"}

    if weights is None:
        weights = [1.0 / len(tickers)] * len(tickers)
    else:
        total_w = sum(weights)
        weights = [w / total_w for w in weights]

    # Fetch all price series (batch to respect rate limits)
    tasks = [_fetch_prices(t, period) for t in tickers]
    all_prices = await asyncio.gather(*tasks, return_exceptions=True)

    # Compute individual metrics
    individual = []
    valid_pairs = []   # [(ticker, returns_list, weight)]
    for ticker, prices, weight in zip(tickers, all_prices, weights):
        if isinstance(prices, Exception) or not prices:
            individual.append({"ticker": ticker, "error": "No data"})
            continue
        rets = _daily_returns(prices)
        individual.append({
            "ticker":         ticker,
            "weight":         round(weight, 4),
            "var_95":         round(_var(rets, 0.95) * 100, 2),
            "sharpe":         round(_sharpe(rets), 3),
            "annualised_vol": round(_annualised_vol(rets) * 100, 2),
            "max_drawdown":   round(_max_drawdown(prices) * 100, 2),
            "total_return":   round((prices[-1] / prices[0] - 1) * 100, 2) if prices[0] else 0,
        })
        valid_pairs.append((ticker, rets, weight))

    if not valid_pairs:
        return {"error": "No valid price data", "individual": individual}

    # Portfolio returns = weighted sum of individual returns
    min_len = min(len(r) for _, r, _ in valid_pairs)
    portfolio_rets = [
        sum(r[-min_len:][i] * w for _, r, w in valid_pairs)
        for i in range(min_len)
    ]

    # Correlation matrix (only if ≥ 2 assets)
    corr_matrix = None
    if len(valid_pairs) >= 2:
        names = [t for t, _, _ in valid_pairs]
        corr_matrix = {}
        for i, (t1, r1, _) in enumerate(valid_pairs):
            corr_matrix[t1] = {}
            for j, (t2, r2, _) in enumerate(valid_pairs):
                corr_matrix[t1][t2] = round(_correlation(r1, r2), 3)

    return {
        "portfolio": {
            "tickers":        tickers,
            "weights":        weights,
            "var_95":         round(_var(portfolio_rets, 0.95) * 100, 2),
            "var_99":         round(_var(portfolio_rets, 0.99) * 100, 2),
            "cvar_95":        round(_cvar(portfolio_rets, 0.95) * 100, 2),
            "sharpe":         round(_sharpe(portfolio_rets), 3),
            "sortino":        round(_sortino(portfolio_rets), 3),
            "annualised_vol": round(_annualised_vol(portfolio_rets) * 100, 2),
            "period":         period,
            "observations":   min_len,
        },
        "individual":    individual,
        "correlation":   corr_matrix,
    }


async def compute_technical(ticker: str, period: str = "6mo") -> dict:
    """
    Compute basic technical indicators without any external TA library.
    Uses only pure Python + the already-fetched price series.

    Indicators: SMA20, SMA50, SMA200, RSI(14), price vs SMAs.
    """
    prices = await _fetch_prices(ticker, period)
    if not prices or len(prices) < 20:
        return {"ticker": ticker, "error": "Insufficient price data"}

    def sma(series, n):
        return sum(series[-n:]) / n if len(series) >= n else None

    def rsi(series, n=14):
        if len(series) < n + 1:
            return None
        changes = [series[i] - series[i-1] for i in range(1, len(series))][-n:]
        gains = [max(c, 0) for c in changes]
        losses = [max(-c, 0) for c in changes]
        avg_gain = sum(gains) / n
        avg_loss = sum(losses) / n
        if avg_loss < 1e-9:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - 100 / (1 + rs), 2)

    current = prices[-1]
    s20     = sma(prices, 20)
    s50     = sma(prices, 50)
    s200    = sma(prices, 200)
    rsi14   = rsi(prices)

    def pct_vs(sma_val):
        if sma_val is None or sma_val == 0:
            return None
        return round((current / sma_val - 1) * 100, 2)

    # Signal classification
    def trend_signal():
        if s50 and s200:
            if current > s50 > s200:
                return "bullish"
            if current < s50 < s200:
                return "bearish"
        return "neutral"

    def rsi_signal():
        if rsi14 is None:
            return "neutral"
        if rsi14 >= 70:
            return "overbought"
        if rsi14 <= 30:
            return "oversold"
        return "neutral"

    return {
        "ticker":        ticker,
        "current_price": round(current, 2),
        "sma20":         round(s20, 2) if s20 else None,
        "sma50":         round(s50, 2) if s50 else None,
        "sma200":        round(s200, 2) if s200 else None,
        "rsi14":         rsi14,
        "pct_vs_sma20":  pct_vs(s20),
        "pct_vs_sma50":  pct_vs(s50),
        "pct_vs_sma200": pct_vs(s200),
        "trend_signal":  trend_signal(),
        "rsi_signal":    rsi_signal(),
    }


async def screen_watchlist(
    tickers: list[str],
    metric:  str = "sharpe",
    top_n:   int = 5,
) -> list[dict]:
    """
    Rank a watchlist by a given metric (sharpe, var_95, annualised_vol, total_return).
    Useful for automated daily screening.
    """
    # Batch in groups of 10 to stay memory-safe
    all_results = []
    for i in range(0, len(tickers), 10):
        batch = tickers[i:i+10]
        tasks = [compute_var(t) for t in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, dict) and "error" not in r:
                all_results.append(r)
        await asyncio.sleep(0.3)  # respect rate limits between batches

    reverse = metric not in ("var_95", "var_99", "max_drawdown", "annualised_vol")
    ranked  = sorted(all_results, key=lambda x: x.get(metric, 0), reverse=reverse)
    return ranked[:top_n]
