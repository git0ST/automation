"""KPI tooltips — plain English, action-first, 2 lines max.

Every tip answers: what does the current reading mean, and what should
I do about it? Skip definitions — assume the reader is a trader who
wants the trade.
"""
from __future__ import annotations


# ── Market structure ───────────────────────────────────────────────────────
MARKET_REGIME = (
    "What kind of market we're in. **Goldilocks/Reflation = buy stocks**. "
    "Stagflation/Deflation = move to bonds + gold. Confidence under 50% → cut position sizes in half."
)

SYSTEMIC_RISK = (
    "Overall stress level, 0-100. Below 26 = safe to load up. 26-50 = normal. "
    "Above 50 = trim leverage. Above 75 = move to cash."
)

NEWS_SENTIMENT = (
    "How bullish the news flow is. **Bull% minus Bear% above 25** = tailwind for longs. "
    "Below -25 = stop buying. Always check article count — wider spreads on more articles is stronger signal."
)

ALPHA_SIGNALS = (
    "Quiet money moves: insiders buying, big options trades, Congress filings. "
    "**3+ signals on the same name in a week = front-run institutions**, position before crowd notices."
)


# ── Price & momentum ───────────────────────────────────────────────────────
PRICE = (
    "Real-time when Finnhub configured, else 15-min delayed. "
    "Compare 1D to sector — outperforming +2% = relative strength, ride the leader."
)

CHANGE_1D = (
    "Today's move. **Above 3% on high volume = institutions buying** — usually continues. "
    "Solo moves without sector support tend to reverse next day."
)

CHANGE_1W = (
    "Best signal for swing trades. Compare to peer average in same sector — "
    "wide divergence means company-specific news, dig deeper."
)

CHANGE_1Y = (
    "Beat S&P 500 (~10%/year) with rising margins = compounder, hold long. "
    "Beat with shrinking margins = late cycle, take profits."
)

MARKET_CAP = (
    "Total company value. **Mid caps ($2-10B) historically best risk/reward**. "
    "Mega caps (>$200B) are stable but slow; small caps (<$2B) are volatile and illiquid."
)


# ── Technical ──────────────────────────────────────────────────────────────
RSI = (
    "Momentum gauge, 0-100. **Below 30 in an uptrend = buy zone**. Above 70 = take profits or hedge. "
    "55-65 = healthy momentum, hold."
)

SMA_50 = (
    "50-day average — medium-term trend. Price above = uptrend (hold/buy dips). "
    "Sharp break below on volume = trend over, exit."
)

SMA_200 = (
    "200-day average — long-term trend. **Above SMA200 + SMA50 above SMA200 = full uptrend**, hold. "
    "Below SMA200 = avoid going long without strong catalyst."
)

MACD = (
    "Momentum direction. **Bullish cross above zero = entry signal**. "
    "Histogram growing = trend strengthening. Histogram shrinking = trend ending."
)

ADX = (
    "Trend strength, 0-100. **Above 25 = trade with the trend** (follow direction). "
    "Below 15 = market ranging, use oversold/overbought reversal trades instead."
)

BOLLINGER = (
    "Volatility envelope. **Tag of lower band = oversold bounce zone**. "
    "Tag of upper band = take profits. Band squeeze (tight) = big move coming, watch for breakout."
)


# ── Fundamentals ───────────────────────────────────────────────────────────
PE_RATIO = (
    "Price relative to earnings. **Compare to the stock's own 5-year average**, not other stocks. "
    "Above average + slowing growth = overpriced. Below average + accelerating = entry."
)

EPS = (
    "Annual profit per share. **Two consecutive quarters of growing EPS = upgrade candidate**. "
    "Watch for big gap between adjusted EPS and GAAP EPS — bigger gap = lower quality earnings."
)

DIV_YIELD = (
    "Annual dividend ÷ price. **2-4% = healthy income stock**. "
    "0% = growth stock (no payout, all reinvested). Above 5% = check sustainability, often a red flag."
)

BETA = (
    "Sensitivity to S&P 500. **Beta 1 = moves with market. Above 1 = amplified moves both ways**. "
    "Below 0.7 = defensive (use to lower portfolio risk). Below 0 = inverse (hedge holding)."
)


# ── Risk ───────────────────────────────────────────────────────────────────
VAR_95 = (
    "Your typical worst day. **If VaR shows 3%, $10K invested can lose ~$300 on a bad day**. "
    "Expect this 1-2 days a month. Size positions so 2x VaR < what you can stomach losing."
)

VAR_99 = (
    "Tail-loss estimate. Roughly 2-3 days per year you lose this much or more. "
    "**If your stop loss is tighter than VaR 99%, normal volatility will hit your stop**."
)

CVAR = (
    "Average loss on your worst days (not the threshold — the actual loss). "
    "**Always larger than VaR**. Use this to size positions: risk = position × CVaR."
)

MAX_DRAWDOWN = (
    "Worst historical peak-to-trough drop. **Above 35% = cyclical stock** (cars, banks, energy). "
    "Below 20% = quality compounder (Apple, Microsoft type). Expect 2-3x worse in a real bear market."
)

SHARPE = (
    "Return per unit of risk. **Above 1 = good** (better than cash + risk premium). "
    "Above 2 = excellent (rare, usually short-lived). Negative = stop trading this stock."
)

SORTINO = (
    "Like Sharpe but only counts the downside. **Better gauge for stocks with big winners and small losers**. "
    "Above 2 = strong asymmetric edge, position size up."
)

ANNUAL_VOL = (
    "How much the stock swings yearly. **Tech 30-50% · Banks 25-35% · Utilities 15-20% · S&P 15%**. "
    "Higher vol = wider stops needed, smaller position size."
)


# ── Composite / AI ─────────────────────────────────────────────────────────
CONFIDENCE = (
    "How sure the model is. **Above 70% = high conviction, full position size**. "
    "55-70% = scale in gradually. Below 50% = wait for better setup."
)

QUANT_SCORE = (
    "Fundamental quality grade. **A/A+ = core holding** (longer holds, lower turnover). "
    "B = solid swing trade. C/D = avoid or short candidate. F = stay out."
)

QUANT_FACTORS = (
    "Five factors graded A+ to F. **A in Profit + A in Growth + B+ Momentum = compounder**, hold months. "
    "A in Value + bullish technical = reversal play, swing trade. F in Profit + bearish = short candidate."
)

PREDICTION = (
    "AI's call combining technical + sentiment + analyst + sector + volatility. "
    "**Bullish 70%+ = enter this week**. Bearish 70%+ = exit or short. Check signal breakdown — same direction across 3+ signals = trust it."
)


# ── Regime / cycle ─────────────────────────────────────────────────────────
CONFIDENCE_REGIME = (
    "How strongly the macro signals agree on regime. **Above 70% = trust the playbook for 3-8 weeks**. "
    "40-70% = reduce concentration, regime transitioning. Below 40% = stay in index ETFs until clear."
)

TRANSITION_RISK = (
    "Probability of regime change soon. **Low = current playbook good for weeks**. "
    "Medium = start shifting toward defensives. High = regime shift imminent, reduce risk now."
)


# ── Cross-source / data ────────────────────────────────────────────────────
HOT_ENTITY = (
    "Same name mentioned across 3+ sources in 24h. **Follow within 1-3 days** before the crowd notices. "
    "Combined with bullish sentiment = front-run institutional positioning."
)

DATA_FRESHNESS = (
    "When the pipeline last updated. **Under 30 min = use real-time signals**. "
    "30 min - 2h = trust prices, skip news-driven trades. Over 2h = trigger pipeline before acting."
)


# ── Forex ──────────────────────────────────────────────────────────────────
DXY = (
    "Dollar Index. **Rising DXY = bad for emerging markets, commodities, and big exporters** (Apple, Microsoft - half their revenue is international). "
    "DXY breaking 105 = sell emerging market positions."
)

EURUSD = (
    "Euro to dollar rate. **Rising = dollar weakening = supports gold and emerging markets**. "
    "Below 1.05 = strong dollar regime, avoid non-US assets."
)

USDJPY = (
    "Dollar to yen rate. **Rising = yen weakening = supports Japanese exporters** (Toyota, Sony). "
    "Above 150 = Bank of Japan may intervene, watch for sudden reversal."
)


# ── Strategy / sizing ──────────────────────────────────────────────────────
STOP_PCT = (
    "Distance from entry to stop loss. **Must be wider than your VaR 95%**. "
    "Too tight = normal volatility hits your stop. Too wide = position size needs to drop."
)

POSITION_SIZE = (
    "How much to invest, sized so a stop-loss hit costs no more than 1% of portfolio. "
    "**Drops automatically when volatility is high or confidence is low**. Capped at 15% of portfolio."
)

R_MULTIPLE = (
    "Reward-to-risk ratio. **2:1 minimum** (target is 2x bigger than stop distance). "
    "3:1+ for trend follows. Below 1.5:1 = bad trade, skip."
)


# ── Aggregator ─────────────────────────────────────────────────────────────
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


