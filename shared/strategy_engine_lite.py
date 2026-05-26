"""Strategy engine — pipeline-safe version (no Streamlit imports).

Mirrors streamlit/_strategy_engine.py STRATEGIES + matching logic, so
the headless opportunity_runner can tag predictions with strategies.
"""
from __future__ import annotations


STRATEGIES = [
    {"name": "Quality Momentum", "horizon": "medium", "direction": "long",
     "criteria": {"quant_grade_in": ["A+", "A", "B+"],
                   "technical_direction": "bullish",
                   "profit_grade_in": ["A+", "A"],
                   "confidence_min": 55}},
    {"name": "Value Reversal", "horizon": "medium", "direction": "long",
     "criteria": {"value_grade_in": ["A+", "A", "B+"],
                   "technical_direction": "bullish",
                   "confidence_min": 50, "rsi_max": 45}},
    {"name": "Momentum Pullback", "horizon": "short", "direction": "long",
     "criteria": {"above_sma_200": True, "rsi_min": 30, "rsi_max": 50,
                   "confidence_min": 45}},
    {"name": "Mean Reversion", "horizon": "short", "direction": "long",
     "criteria": {"rsi_max": 32}},
    {"name": "Trend Short", "horizon": "medium", "direction": "short",
     "criteria": {"technical_direction": "bearish", "below_sma_200": True,
                   "quant_grade_in": ["C", "D", "F"], "confidence_min": 55}},
    {"name": "Long-term Compounder", "horizon": "long", "direction": "long",
     "criteria": {"composite_quant_min": 75,
                   "profit_grade_in": ["A+", "A"],
                   "growth_grade_in": ["A+", "A", "B+"]}},
]


def _check(setup: dict, key: str, value) -> bool:
    if key.endswith("_in"):
        k = key[:-3]
        sv = setup.get(k)
        return sv in value if sv is not None and value is not None else False
    if key.endswith("_min"):
        k = key[:-4]
        sv = setup.get(k)
        return sv >= value if sv is not None and value is not None else False
    if key.endswith("_max"):
        k = key[:-4]
        sv = setup.get(k)
        return sv <= value if sv is not None and value is not None else False
    sv = setup.get(key)
    if value is None or sv is None: return False
    if isinstance(value, bool): return bool(sv) is value
    return sv == value


def find_strategies_for_setup(setup: dict) -> list[dict]:
    matched = []
    for s in STRATEGIES:
        if all(_check(setup, k, v) for k, v in s["criteria"].items()):
            matched.append(s)
    return matched
