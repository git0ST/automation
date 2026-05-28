"""Strategy engine — map composite signals to named investment playbooks.

Each strategy maps a setup to:
  - Time horizon (short / medium / long)
  - Entry criteria (signals required)
  - Position sizing guidance (% portfolio + Kelly-adjusted)
  - Stop loss (ATR-based)
  - Take profit (R-multiple based)

Strategies are evaluated against current setup; matching strategies bubble
up to the user with confidence + risk parameters.
"""
from __future__ import annotations
import math


# ── Strategy definitions ────────────────────────────────────────────────────

STRATEGIES = [
    {
        "name":        "Quality Momentum",
        "horizon":     "medium",        # 2-8 weeks
        "direction":   "long",
        "summary":     "High-quality fundamentals (A/A+ Profit + Growth) combined with "
                       "bullish technical momentum. Buy quality on strength — works in "
                       "Reflation + Goldilocks regimes.",
        "criteria": {
            "quant_grade_in":     ["A+", "A", "B+"],
            "technical_direction": "bullish",
            "profit_grade_in":    ["A+", "A"],
            "confidence_min":     55,
        },
        "expected_return":   "8-15%",
        "expected_duration": "4-6 weeks",
        "stop_atr_mult":     2.0,
        "target_atr_mult":   4.0,        # 2:1 R/R
        "position_pct":      0.05,        # 5% of portfolio
    },
    {
        "name":        "Value Reversal",
        "horizon":     "medium",
        "direction":   "long",
        "summary":     "Beaten-down value names showing improving sentiment. "
                       "Catch falling knives only when momentum starts turning. "
                       "Higher risk, higher reward — limit position size.",
        "criteria": {
            "value_grade_in":     ["A+", "A", "B+"],
            "technical_direction": "bullish",
            "confidence_min":     50,
            "rsi_max":            45,
        },
        "expected_return":   "12-25%",
        "expected_duration": "6-12 weeks",
        "stop_atr_mult":     2.5,
        "target_atr_mult":   5.0,
        "position_pct":      0.03,
    },
    {
        "name":        "Momentum Pullback",
        "horizon":     "short",          # 1-3 weeks
        "direction":   "long",
        "summary":     "Buy the dip in an established uptrend. Price above SMA200, "
                       "RSI cooled to 35-50. Stop tight — if trend breaks, exit fast.",
        "criteria": {
            "above_sma_200":      True,
            "rsi_min":            30,
            "rsi_max":            50,
            "confidence_min":     45,
        },
        "expected_return":   "5-10%",
        "expected_duration": "1-3 weeks",
        "stop_atr_mult":     1.5,
        "target_atr_mult":   3.0,
        "position_pct":      0.04,
    },
    {
        "name":        "Breakout",
        "horizon":     "short",
        "direction":   "long",
        "summary":     "Price breaking above Bollinger upper band with MACD bullish "
                       "cross, ADX > 25. High-conviction trend continuation.",
        "criteria": {
            "bb_signal_in":       ["above_upper_band", "near_upper_band"],
            "macd_cross_in":      ["bullish_cross", "bullish_expanding"],
            "adx_min":            25,
            "confidence_min":     55,
        },
        "expected_return":   "6-12%",
        "expected_duration": "2-4 weeks",
        "stop_atr_mult":     1.5,
        "target_atr_mult":   3.5,
        "position_pct":      0.04,
    },
    {
        "name":        "Mean Reversion (Long)",
        "horizon":     "short",
        "direction":   "long",
        "summary":     "Oversold bounce — RSI < 30 + at/below Bollinger lower band. "
                       "Counter-trend; works best in ranging markets (ADX < 25).",
        "criteria": {
            "rsi_max":            32,
            "bb_signal_in":       ["below_lower_band", "near_lower_band"],
            "adx_max":            25,
        },
        "expected_return":   "3-7%",
        "expected_duration": "3-10 days",
        "stop_atr_mult":     1.2,
        "target_atr_mult":   2.5,
        "position_pct":      0.03,
    },
    {
        "name":        "Defensive Rotation",
        "horizon":     "long",            # 2-6 months
        "direction":   "long",
        "summary":     "Risk-off regime → favor defensive sectors (Healthcare, Utilities, "
                       "Consumer Staples) with low beta. Lower return, lower drawdown.",
        "criteria": {
            "regime_in":          ["stagflation", "deflation"],
            "sector_in":          ["Health", "Pharma", "Utilities", "Cons Stap"],
            "confidence_min":     40,
        },
        "expected_return":   "5-10%",
        "expected_duration": "2-6 months",
        "stop_atr_mult":     3.0,
        "target_atr_mult":   4.0,
        "position_pct":      0.05,
    },
    {
        "name":        "Trend Short",
        "horizon":     "medium",
        "direction":   "short",
        "summary":     "Established downtrend (Death Cross + price below SMA200) + "
                       "weak fundamentals. Use option-puts or inverse ETF on this signal.",
        "criteria": {
            "technical_direction": "bearish",
            "below_sma_200":      True,
            "quant_grade_in":     ["C", "D", "F"],
            "confidence_min":     55,
        },
        "expected_return":   "8-15% (downside)",
        "expected_duration": "4-8 weeks",
        "stop_atr_mult":     2.0,
        "target_atr_mult":   4.0,
        "position_pct":      0.03,
    },
    {
        "name":        "Long-term Compounder",
        "horizon":     "long",
        "direction":   "long",
        "summary":     "Quality factor across the board (A+ Profit + A Growth + B+ Value). "
                       "Buy and hold 6-24 months. Lower portfolio turnover, lower tax drag.",
        "criteria": {
            "composite_quant_min": 75,
            "profit_grade_in":     ["A+", "A"],
            "growth_grade_in":     ["A+", "A", "B+"],
        },
        "expected_return":   "20-40% / year",
        "expected_duration": "6-24 months",
        "stop_atr_mult":     3.5,        # wider stops for long-term
        "target_atr_mult":   8.0,
        "position_pct":      0.08,        # larger position for highest-conviction
    },
]


def _grade_to_int(g: str | None) -> int:
    order = ["F", "D", "C", "C+", "B", "B+", "A", "A+"]
    return order.index(g) if g in order else 0


def _check_criterion(setup: dict, key: str, value) -> bool:
    """Apply a single criterion to a setup. Returns True if it matches.

    Criterion keys use suffixes (_in / _min / _max) to encode the comparison;
    the setup dict uses bare keys (quant_grade, rsi, etc.). Strip the suffix
    before lookup.
    """
    # Strip suffix to find the underlying setup field
    if key.endswith("_in"):
        setup_key = key[:-3]
        setup_val = setup.get(setup_key)
        if setup_val is None or value is None:
            return False
        return setup_val in value

    if key.endswith("_min"):
        setup_key = key[:-4]
        setup_val = setup.get(setup_key)
        if setup_val is None or value is None:
            return False
        return setup_val >= value

    if key.endswith("_max"):
        setup_key = key[:-4]
        setup_val = setup.get(setup_key)
        if setup_val is None or value is None:
            return False
        return setup_val <= value

    # Bare keys
    setup_val = setup.get(key)
    if value is None or setup_val is None:
        return False
    if isinstance(value, bool):
        return bool(setup_val) is value
    return setup_val == value


def _strategy_matches(strategy: dict, setup: dict) -> tuple[bool, list[str]]:
    """Returns (match, list_of_failed_criteria)."""
    failed = []
    for key, value in strategy["criteria"].items():
        if not _check_criterion(setup, key, value):
            failed.append(key)
    return (len(failed) == 0, failed)


def find_strategies(setup: dict) -> list[dict]:
    """Find all matching strategies for a setup. Returns ranked list.

    setup must contain (any of):
      composite_quant, quant_grade, value_grade, growth_grade, profit_grade,
      technical_direction, rsi, above_sma_200, below_sma_200, regime,
      bb_signal, macd_cross, adx, sector, confidence
    """
    matched = []
    for s in STRATEGIES:
        ok, failed = _strategy_matches(s, setup)
        if ok:
            matched.append(s)
    # Rank: higher position_pct first (higher conviction strategies)
    return sorted(matched, key=lambda x: -x["position_pct"])


def position_sizing(stop_pct: float, conviction: float = 0.5,
                    portfolio_value: float = 100_000,
                    max_risk_pct: float = 0.01) -> dict:
    """Position-sizing calc combining fixed-fractional + Kelly.

    Args:
        stop_pct: distance to stop as % of entry price (e.g. 0.04 = 4% stop)
        conviction: 0-1 confidence multiplier (from composite confidence)
        portfolio_value: total portfolio $
        max_risk_pct: max % of portfolio to risk on single trade (default 1%)

    Returns:
        dict with $ at risk, $ position size, share count guide
    """
    # Fractional Kelly: cap at half of full Kelly to reduce ruin risk
    kelly_fraction = min(0.5, conviction * 0.5)
    # Risk per trade scales with conviction
    risk_amount = portfolio_value * max_risk_pct * (0.5 + conviction)
    if stop_pct <= 0:
        return {"position_value": 0, "risk_amount": 0, "kelly_pct": 0,
                "warning": "Invalid stop_pct"}
    position_value = risk_amount / stop_pct
    # Cap at 15% of portfolio regardless of Kelly suggestion
    position_value = min(position_value, portfolio_value * 0.15)
    return {
        "position_value":  round(position_value, 2),
        "risk_amount":     round(risk_amount, 2),
        "kelly_pct":       round(kelly_fraction * 100, 1),
        "position_pct":    round(position_value / portfolio_value * 100, 2),
    }


def kelly_position_sizing(win_prob: float, payoff_ratio: float = 2.0,
                          portfolio_value: float = 100_000,
                          stop_pct: float = 0.04,
                          kelly_fraction: float = 0.5,
                          max_position_pct: float = 0.15) -> dict:
    """Size a position from EDGE using fractional Kelly.

    The growth-optimal bet size given a win probability and payoff. We feed it
    the model's *calibrated* win probability so size tracks real, measured edge
    rather than a flat rule.

    Args:
        win_prob:       calibrated P(trade correct), 0-1 (confidence/100).
        payoff_ratio:   b = reward/risk (e.g. 2.0 for a 2:1 target/stop).
        kelly_fraction: fraction of full Kelly to bet (0.5 = half-Kelly — the
                        standard professional haircut to cut drawdown/ruin risk).
        max_position_pct: hard cap on single-name exposure.

    Full Kelly fraction of capital: f* = (p·b − q) / b, q = 1−p.
    When edge ≤ 0 (p ≤ 1/(1+b)) Kelly returns 0 → NO TRADE: the math itself
    tells you not to invest. Returns sizing + edge + a no_trade flag.
    """
    p = max(0.0, min(1.0, win_prob))
    q = 1.0 - p
    b = max(payoff_ratio, 0.01)
    full_kelly = (p * b - q) / b
    sized = max(0.0, full_kelly) * kelly_fraction
    position_pct = min(sized, max_position_pct)
    position_value = portfolio_value * position_pct
    risk_amount = position_value * stop_pct if stop_pct > 0 else 0.0
    edge = p * b - q                       # expected units won per unit risked
    breakeven = 1.0 / (1.0 + b)            # win-rate needed just to break even
    return {
        "position_value":  round(position_value, 2),
        "position_pct":    round(position_pct * 100, 2),
        "risk_amount":     round(risk_amount, 2),
        "full_kelly_pct":  round(full_kelly * 100, 1),
        "sized_kelly_pct": round(sized * 100, 1),
        "win_prob":        round(p * 100, 1),
        "breakeven_pct":   round(breakeven * 100, 1),
        "payoff_ratio":    round(b, 2),
        "edge":            round(edge, 3),
        "no_trade":        sized <= 0,
    }


def compute_levels(price: float, atr_val: float,
                   stop_mult: float, target_mult: float,
                   direction: str = "long") -> dict:
    """Compute ATR-based entry/stop/target levels for a strategy."""
    if not atr_val or atr_val <= 0:
        return {"entry": price, "stop": None, "target": None,
                "r_multiple": None, "stop_pct": None}

    if direction == "long":
        stop   = price - stop_mult   * atr_val
        target = price + target_mult * atr_val
    else:  # short
        stop   = price + stop_mult   * atr_val
        target = price - target_mult * atr_val

    risk = abs(price - stop)
    reward = abs(target - price)
    r_multiple = reward / risk if risk > 0 else 0
    stop_pct = abs(price - stop) / price

    return {
        "entry":      round(price, 2),
        "stop":       round(stop, 2),
        "target":     round(target, 2),
        "r_multiple": round(r_multiple, 2),
        "stop_pct":   round(stop_pct * 100, 2),
    }
