"""KPI tooltips — focused on HOW TO USE each metric, not what it means.

Inspired by Bloomberg Terminal HELP function: every term assumes the reader
knows the definition. The value of the tooltip is in the operational guidance.

Format: 2 sentences max. Sentence 1 = what the current reading suggests.
Sentence 2 = decision rule or comparison anchor.
"""
from __future__ import annotations


# ── Market structure KPIs ──────────────────────────────────────────────────
MARKET_REGIME = (
    "**Use:** Goldilocks/Reflation favor risk-on (equities, growth, EM). "
    "Stagflation/Deflation favor defensives (bonds, gold, utilities). "
    "Confidence <50% = mixed signals; reduce position size."
)

SYSTEMIC_RISK = (
    "**Use:** SRS <26 = full risk-on. 26-50 = normal. 51-75 = trim leverage. "
    ">75 = de-risk aggressively. Add 5% to position sizes per 10pt below 30; "
    "halve them per 10pt above 60."
)

NEWS_SENTIMENT = (
    "**Use:** Bull% - Bear% >25 = strong tailwind for long entries. "
    "Spread <-25 = avoid new longs. Always compared to article count — "
    "20%/5% spread on 200 articles beats 60%/30% on 5 articles."
)

ALPHA_SIGNALS = (
    "**Use:** Insider buying / call flow / Congress purchases >2× normal = "
    "watch for breakout. Cluster of 3+ signals on same name = high-conviction setup."
)


# ── Price & momentum KPIs ──────────────────────────────────────────────────
PRICE = (
    "**Use:** Real-time when Finnhub configured. Compare 1D/1W/1M to "
    "sector ETF (XLK for tech, XLF for finance) — outperformance >2% = "
    "relative strength leader, ride it."
)

CHANGE_1D = (
    "**Use:** Moves >3% on rising volume = institutional flow. "
    "Combine with sector heatmap — solo movers reverse faster than sector waves."
)

CHANGE_1W = (
    "**Use:** Stronger signal than 1D for swing trades. "
    "Compare to peer median in same sector — significant divergence = company-specific catalyst."
)

CHANGE_1Y = (
    "**Use:** Compare to S&P 500 (~10%/yr historical). Outperformance "
    "with rising margins = momentum compounder; outperformance with shrinking "
    "margins = late-cycle warning."
)

MARKET_CAP = (
    "**Use:** >$200B = mega cap (low vol, slow growth). $10-200B = large cap. "
    "$2-10B = mid cap (best risk/reward zone). <$2B = small cap (higher vol, illiquid)."
)


# ── Technical KPIs ─────────────────────────────────────────────────────────
RSI = (
    "**Use:** <30 in uptrend = buy the dip zone. >70 = trim or hedge. "
    "55-65 = healthy momentum. RSI divergence (price up, RSI down) = momentum fading."
)

SMA_50 = (
    "**Use:** Price above SMA50 = medium-term uptrend, hold/buy on pullbacks. "
    "Sharp break below on volume = trend change, exit longs."
)

SMA_200 = (
    "**Use:** Price above SMA200 = long-term bull case intact. "
    "Golden Cross (SMA50 > SMA200) on rising volume = institutional accumulation signal."
)

MACD = (
    "**Use:** Bullish cross + above zero line = momentum entry. "
    "Histogram expanding = trend strengthening; contracting = trend exhausting."
)

ADX = (
    "**Use:** >25 = strong trend (follow direction). 15-25 = weak/transitioning. "
    "<15 = ranging market, use mean-reversion (RSI extremes) instead of trend follow."
)

BOLLINGER = (
    "**Use:** Tag of lower band = oversold bounce zone. Tag of upper band = "
    "overbought (trim or hedge). Band squeeze (low width) = breakout pending."
)


# ── Fundamental KPIs ───────────────────────────────────────────────────────
PE_RATIO = (
    "**Use:** Compare to 5-yr median for same stock, not absolute. "
    "Above median + slowing growth = overvalued; below median + accelerating = entry."
)

EPS = (
    "**Use:** Track sequential growth. 2 consecutive quarters of accelerating "
    "EPS growth = upgrade candidate. Quality > magnitude — adjusted vs GAAP gap matters."
)

DIV_YIELD = (
    "**Use:** 0% = growth stock (capital appreciation play). 2-4% = balanced. "
    ">5% = scrutinize sustainability; if dividend > earnings = cut risk high."
)

BETA = (
    "**Use:** β>1.2 = amplifier (more upside + more drawdown). "
    "β 0.8-1.2 = standard equity. β<0.7 = defensive (hedge holding). "
    "β<0 = inverse-correlated (gold miners, VIX ETFs) — use as portfolio hedge."
)


# ── Risk KPIs ──────────────────────────────────────────────────────────────
VAR_95 = (
    "**Use:** This is your typical worst day. Size positions so 2× VaR < "
    "your max single-day drawdown tolerance. If VaR > 4%, expect 1-2 days "
    "per month at this loss level."
)

VAR_99 = (
    "**Use:** Tail-loss estimate. Hit on roughly 2-3 days per year. "
    "Compare to your stop distance — if stop_pct < VaR_99, your stop will get "
    "hit by normal volatility."
)

CVAR = (
    "**Use:** What you actually lose on the bad days, not the threshold. "
    "Always larger than VaR. Use this for position sizing — risk = position × CVaR."
)

MAX_DRAWDOWN = (
    "**Use:** Historical worst peak-to-trough. Adds 2-3× during bear markets. "
    "If MaxDD > 35%, treat as cyclical; <20% = quality compounder."
)

SHARPE = (
    "**Use:** >1 = good (better than holding cash + small risk premium). "
    ">2 = excellent (rare; usually mean-reverting). Negative = stop trading this name."
)

SORTINO = (
    "**Use:** Like Sharpe but ignores upside vol. Better measure for "
    "asymmetric strategies (covered calls, deep value). >2 = strong risk-adjusted edge."
)

ANNUAL_VOL = (
    "**Use:** Tech ~30-50%, utilities ~15-25%, broad index ~15-20%. "
    "Use to translate VaR — 30% annual vol ≈ 1.9% daily vol ≈ 3.1% one-day VaR(95%)."
)


# ── Composite / AI KPIs ────────────────────────────────────────────────────
CONFIDENCE = (
    "**Use:** 70%+ = high-conviction (full position). 55-70% = scale in. "
    "<50% = wait or pass. Confidence ≠ probability of gain — it's "
    "model agreement × signal quality."
)

QUANT_SCORE = (
    "**Use:** A/A+ = quality core hold (longer hold periods). "
    "B = solid swing trade candidate. C/D = avoid or short candidate. "
    "F = stay out unless catalyst-driven."
)

QUANT_FACTORS = (
    "**Use:** A in Profit + A in Growth + B+ Momentum = compounder. "
    "A in Value + bullish technical = reversal play. F in Profit + bearish = short candidate."
)

PREDICTION = (
    "**Use:** Bullish ≥70% conf = act this week. Bearish ≥70% = exit/short. "
    "Read the signal breakdown — same direction across Technical + Sentiment + "
    "Analyst = trust the level; one outlier = wait for confirmation."
)


# ── Regime / cycle KPIs ────────────────────────────────────────────────────
CONFIDENCE_REGIME = (
    "**Use:** >70% = regime is durable, lean into its preferred assets. "
    "40-70% = transitional, reduce concentration. <40% = mixed signals, "
    "stick to index ETFs until clearer."
)

TRANSITION_RISK = (
    "**Use:** Low = current playbook valid for 3-8 weeks. Medium = "
    "rebalance toward defensives over 1-2 weeks. High = regime shift imminent, "
    "actively reduce exposure."
)


# ── Cross-source / data quality ────────────────────────────────────────────
HOT_ENTITY = (
    "**Use:** 3+ sources mentioning same name in 24h = follow within "
    "1-3 days. Combined with bullish sentiment = front-run institutional positioning."
)

DATA_FRESHNESS = (
    "**Use:** <30 min = use real-time. 30 min - 2h = trust prices, "
    "skip news-driven trades. >2h = trigger pipeline before acting on signals."
)


# ── Forex / FX KPIs ────────────────────────────────────────────────────────
DXY = (
    "**Use:** DXY ↑ = USD strength → headwind for emerging markets, "
    "commodities, large-cap exporters (AAPL/MSFT >50% revenue intl). "
    "DXY breaking 105 = de-risk EM."
)

EURUSD = (
    "**Use:** EUR/USD rising = USD weakening = supports gold + EM. "
    "Falling below 1.05 = USD strength regime; rotate away from non-US assets."
)

USDJPY = (
    "**Use:** USD/JPY ↑ = yen weakening = supports Japanese exporters "
    "(7203.T Toyota, 6758.T Sony). Above 150 = BoJ intervention risk."
)


# ── Strategy / position sizing ─────────────────────────────────────────────
STOP_PCT = (
    "**Use:** ATR-based stops adjust to volatility. Always < your VaR(95%). "
    "Tighter stops = more frequent stops but lower per-trade loss."
)

POSITION_SIZE = (
    "**Use:** Kelly-capped at half-Kelly to reduce ruin risk. "
    "Never risk >1% of portfolio on a single trade. Position % drops "
    "as stop_pct or vol_regime rise."
)

R_MULTIPLE = (
    "**Use:** Target/stop ratio. 2:1 minimum; 3:1+ for trend follows; "
    "1.5:1 ok for mean-reversion scalps. Below 1.5:1 = bad risk-reward, pass."
)


# ── Aggregator: get tooltip by short code ──────────────────────────────────
ALL = {
    "market_regime":      MARKET_REGIME,
    "systemic_risk":      SYSTEMIC_RISK,
    "news_sentiment":     NEWS_SENTIMENT,
    "alpha_signals":      ALPHA_SIGNALS,
    "price":              PRICE,
    "change_1d":          CHANGE_1D,
    "change_1w":          CHANGE_1W,
    "change_1y":          CHANGE_1Y,
    "market_cap":         MARKET_CAP,
    "rsi":                RSI,
    "sma_50":             SMA_50,
    "sma_200":            SMA_200,
    "macd":               MACD,
    "adx":                ADX,
    "bollinger":          BOLLINGER,
    "pe_ratio":           PE_RATIO,
    "eps":                EPS,
    "div_yield":          DIV_YIELD,
    "beta":               BETA,
    "var_95":             VAR_95,
    "var_99":             VAR_99,
    "cvar":               CVAR,
    "max_drawdown":       MAX_DRAWDOWN,
    "sharpe":             SHARPE,
    "sortino":            SORTINO,
    "annual_vol":         ANNUAL_VOL,
    "confidence":         CONFIDENCE,
    "quant_score":        QUANT_SCORE,
    "quant_factors":      QUANT_FACTORS,
    "prediction":         PREDICTION,
    "confidence_regime":  CONFIDENCE_REGIME,
    "transition_risk":    TRANSITION_RISK,
    "hot_entity":         HOT_ENTITY,
    "data_freshness":     DATA_FRESHNESS,
    "dxy":                DXY,
    "eurusd":             EURUSD,
    "usdjpy":             USDJPY,
    "stop_pct":           STOP_PCT,
    "position_size":      POSITION_SIZE,
    "r_multiple":         R_MULTIPLE,
}


def help_for(key: str) -> str:
    return ALL.get(key, "")
