"""Advanced technical indicators — MACD, Bollinger Bands, ATR, ADX.

Used to enrich the technical_signal layer beyond simple SMA + RSI,
so confidence isn't artificially low when only technicals fire.
"""
from __future__ import annotations
import numpy as np


def ema(values: np.ndarray, period: int) -> np.ndarray:
    """Exponential moving average."""
    alpha = 2 / (period + 1)
    out = np.zeros_like(values, dtype=float)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i-1]
    return out


def macd(closes: np.ndarray, fast: int = 12, slow: int = 26,
         signal_period: int = 9) -> dict:
    """MACD line, signal line, histogram.

    Crossover above signal = bullish momentum acceleration.
    Histogram expansion = trend strengthening.
    """
    if len(closes) < slow + signal_period:
        return {"macd": None, "signal": None, "histogram": None, "cross": "neutral"}
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal_period)
    histogram = macd_line - signal_line

    # Crossover detection (last 2 bars)
    cross = "neutral"
    if len(histogram) >= 2:
        if histogram[-2] < 0 and histogram[-1] > 0:
            cross = "bullish_cross"
        elif histogram[-2] > 0 and histogram[-1] < 0:
            cross = "bearish_cross"
        elif histogram[-1] > 0 and histogram[-1] > histogram[-2]:
            cross = "bullish_expanding"
        elif histogram[-1] < 0 and histogram[-1] < histogram[-2]:
            cross = "bearish_expanding"

    return {
        "macd":      float(macd_line[-1]),
        "signal":    float(signal_line[-1]),
        "histogram": float(histogram[-1]),
        "cross":     cross,
    }


def bollinger_bands(closes: np.ndarray, period: int = 20, std_dev: float = 2.0) -> dict:
    """Bollinger Bands — mean + 2σ envelope.

    Price near upper band = overbought tendency.
    Price near lower band = oversold tendency.
    Width contraction (squeeze) = volatility compression, often precedes breakout.
    """
    if len(closes) < period:
        return {"upper": None, "middle": None, "lower": None,
                "pct_b": None, "width": None, "signal": "neutral"}
    window = closes[-period:]
    middle = float(window.mean())
    std = float(window.std(ddof=1))
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    last = float(closes[-1])
    # %B: 0 = at lower, 1 = at upper
    pct_b = (last - lower) / (upper - lower) if upper > lower else 0.5
    # Bandwidth — relative
    width = (upper - lower) / middle if middle else 0

    if pct_b > 1.0:
        signal = "above_upper_band"   # overbought
    elif pct_b > 0.8:
        signal = "near_upper_band"
    elif pct_b < 0:
        signal = "below_lower_band"   # oversold
    elif pct_b < 0.2:
        signal = "near_lower_band"
    else:
        signal = "neutral"

    return {
        "upper":  upper, "middle": middle, "lower": lower,
        "pct_b":  round(pct_b, 3), "width":  round(width, 4),
        "signal": signal,
    }


def atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
        period: int = 14) -> float | None:
    """Average True Range — vol estimator used for position sizing + stops.

    ATR-based stop: place stop = N × ATR below entry. Common N: 1.5-2.5.
    """
    if len(closes) < period + 1:
        return None
    prev_close = np.roll(closes, 1)
    prev_close[0] = closes[0]
    tr1 = highs - lows
    tr2 = np.abs(highs - prev_close)
    tr3 = np.abs(lows - prev_close)
    true_range = np.maximum(np.maximum(tr1, tr2), tr3)
    return float(true_range[-period:].mean())


def adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
        period: int = 14) -> dict:
    """Average Directional Index — trend strength.

    ADX > 25 = trending; > 40 = strong trend.
    +DI > -DI = uptrend; vice versa for downtrend.
    """
    if len(closes) < period + 1:
        return {"adx": None, "plus_di": None, "minus_di": None, "trend": "unknown"}

    up_move   = highs[1:] - highs[:-1]
    down_move = lows[:-1]  - lows[1:]
    plus_dm   = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm  = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    prev_close = closes[:-1]
    tr = np.maximum(np.maximum(highs[1:] - lows[1:],
                                np.abs(highs[1:] - prev_close)),
                    np.abs(lows[1:] - prev_close))
    tr_smooth   = tr[-period:].mean()
    plus_di     = 100 * plus_dm[-period:].mean()  / max(tr_smooth, 1e-9)
    minus_di    = 100 * minus_dm[-period:].mean() / max(tr_smooth, 1e-9)
    dx          = 100 * abs(plus_di - minus_di) / max(plus_di + minus_di, 1e-9)
    adx_value   = float(dx)

    if adx_value > 40:
        trend_strength = "very_strong"
    elif adx_value > 25:
        trend_strength = "strong"
    elif adx_value > 15:
        trend_strength = "weak"
    else:
        trend_strength = "ranging"

    return {
        "adx":      round(adx_value, 1),
        "plus_di":  round(float(plus_di), 1),
        "minus_di": round(float(minus_di), 1),
        "trend":    trend_strength,
        "direction": "up" if plus_di > minus_di else "down",
    }


def vwap_distance(closes: np.ndarray, volumes: np.ndarray, period: int = 20) -> dict:
    """Distance from rolling-period VWAP. >+2% = extended; <-2% = stretched."""
    if len(closes) < period:
        return {"vwap": None, "pct_from_vwap": None, "signal": "neutral"}
    pv = closes[-period:] * volumes[-period:]
    v  = volumes[-period:].sum()
    vwap_val = float(pv.sum() / v) if v > 0 else float(closes[-1])
    last = float(closes[-1])
    pct = (last / vwap_val - 1) * 100 if vwap_val else 0

    if pct > 5:    signal = "very_extended_above"
    elif pct > 2:  signal = "extended_above"
    elif pct < -5: signal = "very_extended_below"
    elif pct < -2: signal = "extended_below"
    else:           signal = "neutral"

    return {"vwap": vwap_val, "pct_from_vwap": round(pct, 2), "signal": signal}


def compute_all_technicals(highs: np.ndarray, lows: np.ndarray,
                           closes: np.ndarray, volumes: np.ndarray) -> dict:
    """One-shot compute of all advanced technicals."""
    return {
        "macd":    macd(closes),
        "bbands":  bollinger_bands(closes),
        "atr":     atr(highs, lows, closes),
        "adx":     adx(highs, lows, closes),
        "vwap":    vwap_distance(closes, volumes),
    }


