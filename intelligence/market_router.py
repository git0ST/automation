"""
Market Router — multi-market signal routing and cross-asset dampening.

Classifies every ticker into a market type and applies market-specific
signal parameters. Each market type has a distinct volatility profile,
relevant signal sources, regime sensitivity, and position sizing rules.

Also computes cross-market correlation factors that dampen or amplify
signals based on macro state (VIX, DXY, credit spreads, Fear & Greed).

Market types:
  equity     — S&P 500, NASDAQ, individual stocks
  crypto     — BTC, ETH, altcoins (24/7, higher vol, no options/earnings)
  forex      — Currency pairs (carry-driven, macro-dominant)
  commodity  — Oil, gold, copper (inflation regime-sensitive)
  index      — ^SPX, ^NDX, ^VIX (broad market)
  bond       — TLT, HYG, AGG (duration/credit sensitive)
"""
from __future__ import annotations

import math
from typing import Optional


# ── Ticker classification ──────────────────────────────────────────────────────

# Crypto tickers as they appear in the system (CoinGecko symbols)
_CRYPTO = {
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", "MATIC",
    "LINK", "LTC", "UNI", "ATOM", "FIL", "NEAR", "APT", "ARB", "OP", "INJ",
}

# Forex pairs (Yahoo Finance symbols)
_FOREX = {
    "DX-Y.NYB", "EURUSD=X", "USDJPY=X", "GBPUSD=X", "USDCHF=X",
    "AUDUSD=X", "USDCAD=X", "USDCNY=X", "NZDUSD=X", "EURJPY=X",
    "DXY",
}

# Commodity tickers
_COMMODITY = {
    "GC=F", "SI=F", "CL=F", "BZ=F", "NG=F", "HG=F", "ZC=F", "ZS=F",
    "GOLD", "OIL", "GLD", "SLV", "USO", "UNG",
}

# Index tickers
_INDEX = {
    "^GSPC", "^NDX", "^DJI", "^RUT", "^VIX", "^TNX", "^TYX",
    "SPY", "QQQ", "IWM", "DIA",
}

# Bond ETFs / tickers
_BOND = {
    "TLT", "IEF", "SHY", "AGG", "BND", "LQD", "HYG", "JNK", "TBT", "TMF",
}


def classify_ticker(ticker: str) -> str:
    """
    Return market type for a ticker.

    equity | crypto | forex | commodity | index | bond
    Defaults to 'equity' for unknown tickers.
    """
    t = ticker.upper().strip()
    if t in _CRYPTO:         return "crypto"
    if t in _FOREX:          return "forex"
    if t in _COMMODITY:      return "commodity"
    if t in _INDEX:          return "index"
    if t in _BOND:           return "bond"
    # Heuristics
    if t.endswith("=X"):     return "forex"
    if t.endswith("=F"):     return "commodity"
    if t.startswith("^"):    return "index"
    return "equity"


# ── Market profiles ────────────────────────────────────────────────────────────

MARKET_PROFILES: dict[str, dict] = {
    "equity": {
        "min_confluence":    45.0,
        "max_position_pct":  0.05,
        "atr_stop_mult":     1.5,   # stop = 1.5 × ATR
        "vol_lookback":      "3mo",
        "kelly_cap":         0.5,    # half-Kelly
        "regime_weight":     0.05,
        "needs_mkt_hours":   True,
        # Source layer weights
        "w_technical":       0.35,
        "w_options":         0.25,
        "w_sentiment":       0.20,
        "w_fundamental":     0.15,
        "w_regime":          0.05,
        "horizon_default":   "short",  # 1-5 days
    },
    "crypto": {
        "min_confluence":    52.0,   # noisier market — higher bar
        "max_position_pct":  0.03,   # smaller due to tail risk
        "atr_stop_mult":     2.0,    # wider stops for crypto volatility
        "vol_lookback":      "3mo",
        "kelly_cap":         0.35,   # more conservative Kelly
        "regime_weight":     0.10,
        "needs_mkt_hours":   False,  # 24/7
        # No options flow, no fundamental analyst data
        "w_technical":       0.45,
        "w_options":         0.00,
        "w_sentiment":       0.35,   # social sentiment more predictive for crypto
        "w_fundamental":     0.00,
        "w_regime":          0.20,   # macro regime matters (risk-on/risk-off)
        "fg_crypto_weight":  0.15,   # crypto F&G specifically
        "horizon_default":   "short",
    },
    "forex": {
        "min_confluence":    55.0,
        "max_position_pct":  0.04,
        "atr_stop_mult":     1.5,
        "vol_lookback":      "3mo",
        "kelly_cap":         0.40,
        "regime_weight":     0.25,   # macro regime dominates forex
        "needs_mkt_hours":   False,
        # No options, limited fundamentals
        "w_technical":       0.30,
        "w_options":         0.00,
        "w_sentiment":       0.15,
        "w_fundamental":     0.05,
        "w_regime":          0.50,   # regime is everything for forex
        "horizon_default":   "medium",  # hold for days-weeks
    },
    "commodity": {
        "min_confluence":    50.0,
        "max_position_pct":  0.04,
        "atr_stop_mult":     1.8,
        "vol_lookback":      "3mo",
        "kelly_cap":         0.40,
        "regime_weight":     0.15,
        "needs_mkt_hours":   True,
        "w_technical":       0.35,
        "w_options":         0.10,
        "w_sentiment":       0.20,
        "w_fundamental":     0.10,
        "w_regime":          0.25,
        "horizon_default":   "medium",
    },
    "index": {
        "min_confluence":    50.0,
        "max_position_pct":  0.08,   # more diversified → larger size OK
        "atr_stop_mult":     1.5,
        "vol_lookback":      "6mo",
        "kelly_cap":         0.45,
        "regime_weight":     0.20,
        "needs_mkt_hours":   True,
        "w_technical":       0.40,
        "w_options":         0.15,
        "w_sentiment":       0.20,
        "w_fundamental":     0.00,
        "w_regime":          0.25,
        "horizon_default":   "medium",
    },
    "bond": {
        "min_confluence":    55.0,
        "max_position_pct":  0.06,
        "atr_stop_mult":     1.5,
        "vol_lookback":      "6mo",
        "kelly_cap":         0.40,
        "regime_weight":     0.30,
        "needs_mkt_hours":   True,
        "w_technical":       0.25,
        "w_options":         0.10,
        "w_sentiment":       0.10,
        "w_fundamental":     0.00,
        "w_regime":          0.55,   # almost entirely macro-driven
        "horizon_default":   "long",
    },
}


def get_profile(ticker: str) -> dict:
    """Return the market profile for a ticker."""
    mtype = classify_ticker(ticker)
    return {**MARKET_PROFILES.get(mtype, MARKET_PROFILES["equity"]), "market_type": mtype}


# ── Regime-to-market directional bias ─────────────────────────────────────────

REGIME_MARKET_BIAS: dict[str, dict[str, str]] = {
    #                   equity       crypto    forex(USD)  commodity   bond
    "goldilocks":  {"equity": "long", "crypto": "long",   "forex": "short_dxy",
                    "commodity": "neutral", "bond": "short",   "index": "long"},
    "reflation":   {"equity": "long", "crypto": "long",   "forex": "short_dxy",
                    "commodity": "long",    "bond": "short",   "index": "long"},
    "stagflation": {"equity": "short","crypto": "short",  "forex": "long_dxy",
                    "commodity": "long",    "bond": "short",   "index": "short"},
    "deflation":   {"equity": "short","crypto": "short",  "forex": "long_dxy",
                    "commodity": "short",   "bond": "long",    "index": "short"},
}


def regime_bias(market_type: str, regime: Optional[str]) -> Optional[str]:
    """
    Return the macro-favoured direction for a market type in the current regime.
    None if regime unknown.
    """
    if not regime:
        return None
    return REGIME_MARKET_BIAS.get(regime, {}).get(market_type)


# ── Cross-market dampening ─────────────────────────────────────────────────────

def cross_market_factor(
    market_type: str,
    direction:   str,
    vix:         Optional[float] = None,
    dxy_chg_1d:  Optional[float] = None,   # DXY 1-day % change
    fg_stocks:   Optional[int]   = None,   # 0-100
    credit_spread: Optional[float] = None, # IG spread in bps
    regime:      Optional[str]   = None,
) -> float:
    """
    Compute a dampening/amplification factor (0–1.5) for a signal.

    < 1.0 = dampen (unfavourable macro environment for this signal)
    = 1.0 = neutral
    > 1.0 = amplify (macro tailwind behind the signal)

    Rules:
      VIX > 30 → long equity signals dampened (0.65)
      VIX > 40 → all long signals dampened (0.40) — crisis mode
      DXY +1d > +0.8% → commodity/crypto/EM long dampened (0.70)
      DXY +1d < -0.8% → commodity/crypto long amplified (1.20)
      F&G stocks < 20 + direction=long + equity → contrarian amplify (1.15)
      F&G stocks > 80 + direction=long + equity → complacency dampen (0.80)
      Regime aligns with signal → amplify (1.10)
      Regime opposes signal → dampen (0.60)
    """
    factor = 1.0

    # ── VIX stress dampening ──────────────────────────────────────────────────
    if vix is not None:
        if vix > 40:
            # Full crisis — dampen all longs sharply
            if direction == "long":
                factor *= 0.40
            # Shorts actually benefit — amplify slightly
            else:
                factor *= 1.10
        elif vix > 30:
            if direction == "long" and market_type in ("equity", "crypto", "commodity"):
                factor *= 0.65
        elif vix < 14 and direction == "long":
            # Low VIX = complacency — mild dampen
            factor *= 0.92

    # ── DXY strength/weakness ─────────────────────────────────────────────────
    if dxy_chg_1d is not None:
        dxy_abs = abs(dxy_chg_1d)
        if dxy_abs > 0.3:
            dxy_risk_off = dxy_chg_1d > 0   # rising DXY = risk-off
            if dxy_risk_off and direction == "long" and market_type in ("crypto", "commodity", "forex"):
                dampening = max(0.55, 1.0 - dxy_abs * 0.25)
                factor *= dampening
            elif not dxy_risk_off and direction == "long" and market_type in ("crypto", "commodity"):
                amplify = min(1.30, 1.0 + dxy_abs * 0.20)
                factor *= amplify

    # ── Fear & Greed contrarian signal ───────────────────────────────────────
    if fg_stocks is not None and market_type in ("equity", "index"):
        if fg_stocks <= 20 and direction == "long":
            # Extreme Fear — historically excellent long entry for equities
            factor *= 1.15
        elif fg_stocks >= 80 and direction == "long":
            # Extreme Greed — likely overextension
            factor *= 0.80
        elif fg_stocks <= 20 and direction == "short":
            # Shorting into extreme fear — risky, dampen
            factor *= 0.75

    # ── Regime alignment ──────────────────────────────────────────────────────
    if regime:
        rb = regime_bias(market_type, regime)
        if rb in ("long", "short"):
            signal_dir = "long" if direction in ("long", "bullish") else "short"
            if rb == signal_dir:
                factor *= 1.10   # regime tailwind
            else:
                factor *= 0.60   # contra-regime — strong dampen

    return round(min(1.5, max(0.0, factor)), 4)


# ── Volatility-normalized position sizing ─────────────────────────────────────

def normalize_position_for_vol(
    position_pct: float,
    market_type:  str,
    annualised_vol: Optional[float],
) -> float:
    """
    Scale position size so each position has equal vol contribution.
    Target vol = 15% annualised (typical equity target for a diversified portfolio).

    For a 50%-vol crypto position, halve the size vs a 25%-vol equity.
    """
    TARGET_VOL = 0.15

    if annualised_vol is None or annualised_vol <= 0:
        # Use default vol estimates by market type
        defaults = {"equity": 0.30, "crypto": 0.75, "forex": 0.10,
                    "commodity": 0.30, "index": 0.20, "bond": 0.10}
        annualised_vol = defaults.get(market_type, 0.30)

    # Vol-scaled size
    profile = MARKET_PROFILES.get(market_type, MARKET_PROFILES["equity"])
    cap = profile["max_position_pct"]

    vol_adj = TARGET_VOL / annualised_vol
    adjusted = round(min(cap, position_pct * vol_adj), 4)
    return max(0.005, adjusted)  # minimum 0.5% position


# ── VIX vol regime classification ─────────────────────────────────────────────

def vix_regime(vix: Optional[float]) -> str:
    """Classify current VIX into vol regime for prediction logging."""
    if vix is None:   return "unknown"
    if vix >= 35:     return "extreme"
    if vix >= 25:     return "elevated"
    if vix >= 18:     return "normal"
    return "compressed"
