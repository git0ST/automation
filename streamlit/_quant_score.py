"""Multi-factor quant scoring — Seeking Alpha-inspired 5-factor model.

Each stock scored on 5 factors (0-100), composite is weighted average.
Each factor has a letter grade A+/A/B+/B/C+/C/D/F based on percentile.

Backtest evidence: Seeking Alpha's similar Quant model has beaten S&P 500
~4× over 10+ years for "Strong Buy" rated stocks.

Factors (academic provenance):
  - Value          (Fama-French value factor)
  - Growth         (revenue + EPS growth)
  - Profitability  (Novy-Marx 2013)
  - Momentum       (Jegadeesh-Titman 1993)
  - Revisions      (analyst earnings revision factor)
"""
from __future__ import annotations


# Grade boundaries: percentile thresholds → letter
def _percentile_to_grade(pct: float) -> str:
    if pct >= 95: return "A+"
    if pct >= 85: return "A"
    if pct >= 75: return "B+"
    if pct >= 60: return "B"
    if pct >= 45: return "C+"
    if pct >= 30: return "C"
    if pct >= 15: return "D"
    return "F"


# Each factor has a target range — values in target → high score
# Penalties for being outside range based on direction
def _score_value(pe: float | None, pb: float | None) -> tuple[float, str]:
    """Lower P/E + P/B = better value. Tech baseline ~25/5, value ~10/2."""
    score = 50.0
    if pe is not None and pe > 0:
        if pe < 10:    score += 25
        elif pe < 15:  score += 15
        elif pe < 20:  score += 8
        elif pe < 30:  score += 0
        elif pe < 50:  score -= 10
        else:          score -= 20
    if pb is not None and pb > 0:
        if pb < 1.5:   score += 15
        elif pb < 3:   score += 8
        elif pb < 5:   score += 0
        elif pb < 10:  score -= 8
        else:          score -= 15
    score = max(0, min(100, score))
    return score, _percentile_to_grade(score)


def _score_growth(rev_growth: float | None, eps_growth: float | None) -> tuple[float, str]:
    """Higher growth = better. >20% revenue or EPS YoY = strong."""
    score = 50.0
    if rev_growth is not None:
        if rev_growth > 30:    score += 25
        elif rev_growth > 20:  score += 18
        elif rev_growth > 10:  score += 10
        elif rev_growth > 5:   score += 5
        elif rev_growth < 0:   score -= 15
        elif rev_growth < -10: score -= 25
    if eps_growth is not None:
        if eps_growth > 30:    score += 20
        elif eps_growth > 15:  score += 12
        elif eps_growth > 0:   score += 5
        elif eps_growth < -10: score -= 15
        elif eps_growth < -25: score -= 25
    score = max(0, min(100, score))
    return score, _percentile_to_grade(score)


def _score_profitability(roe: float | None, gross_margin: float | None,
                          op_margin: float | None) -> tuple[float, str]:
    """ROE + margins. ROE >15% = good, >25% = excellent."""
    score = 50.0
    if roe is not None:
        if roe > 30:    score += 25
        elif roe > 20:  score += 18
        elif roe > 15:  score += 12
        elif roe > 10:  score += 6
        elif roe < 0:   score -= 20
    if gross_margin is not None:
        if gross_margin > 60:    score += 12
        elif gross_margin > 40:  score += 8
        elif gross_margin > 25:  score += 4
        elif gross_margin < 15:  score -= 8
    if op_margin is not None:
        if op_margin > 25:   score += 13
        elif op_margin > 15: score += 8
        elif op_margin > 5:  score += 3
        elif op_margin < 0:  score -= 15
    score = max(0, min(100, score))
    return score, _percentile_to_grade(score)


def _score_momentum(ret_3m: float | None, ret_6m: float | None,
                     ret_12m: float | None) -> tuple[float, str]:
    """Jegadeesh-Titman momentum: 3M + 6M + 12M returns weighted."""
    score = 50.0
    weights = [(ret_12m, 0.30, "12M"), (ret_6m, 0.40, "6M"), (ret_3m, 0.30, "3M")]
    for ret, w, _ in weights:
        if ret is None:
            continue
        # Each return contributes scaled by weight
        contrib = 0
        if ret > 50:    contrib = 30
        elif ret > 25:  contrib = 22
        elif ret > 10:  contrib = 12
        elif ret > 0:   contrib = 4
        elif ret > -10: contrib = -8
        elif ret > -25: contrib = -18
        else:           contrib = -30
        score += contrib * w
    score = max(0, min(100, score))
    return score, _percentile_to_grade(score)


def _score_revisions(eps_revision_up: int | None, eps_revision_down: int | None,
                      target_upside_pct: float | None) -> tuple[float, str]:
    """Analyst EPS revisions + price-target upside."""
    score = 50.0
    if eps_revision_up is not None and eps_revision_down is not None:
        net = eps_revision_up - eps_revision_down
        total = max(eps_revision_up + eps_revision_down, 1)
        revision_ratio = net / total
        if revision_ratio > 0.5:    score += 25
        elif revision_ratio > 0.2:  score += 15
        elif revision_ratio > 0:    score += 8
        elif revision_ratio > -0.2: score -= 8
        else:                        score -= 20
    if target_upside_pct is not None:
        if target_upside_pct > 30:    score += 20
        elif target_upside_pct > 15:  score += 12
        elif target_upside_pct > 5:   score += 6
        elif target_upside_pct < -10: score -= 15
        elif target_upside_pct < -25: score -= 25
    score = max(0, min(100, score))
    return score, _percentile_to_grade(score)


def compute_quant_score(fundamentals: dict, momentum_data: dict,
                        analyst_data: dict) -> dict:
    """Composite multi-factor score.

    Args:
        fundamentals: from Finnhub basic_financials (P/E, EPS growth, ROE...)
        momentum_data: {ret_3m, ret_6m, ret_12m}
        analyst_data: {eps_revisions_up, eps_revisions_down, target_upside_pct}

    Returns:
        {composite_score, composite_grade, factors: {value, growth, profit, momentum, revisions}}
    """
    fin = fundamentals or {}

    value_score, value_grade = _score_value(
        fin.get("peNormalizedAnnual") or fin.get("peExclExtraAnnual"),
        fin.get("pbAnnual"),
    )

    growth_score, growth_grade = _score_growth(
        fin.get("revenueGrowthTTMYoy") or fin.get("revenueGrowth5Y"),
        fin.get("epsGrowthTTMYoy") or fin.get("epsGrowth5Y"),
    )

    profit_score, profit_grade = _score_profitability(
        fin.get("roeTTM") or fin.get("roeRfy"),
        fin.get("grossMarginTTM") or fin.get("grossMarginAnnual"),
        fin.get("operatingMarginTTM") or fin.get("operatingMarginAnnual"),
    )

    momentum_score, momentum_grade = _score_momentum(
        momentum_data.get("ret_3m"),
        momentum_data.get("ret_6m"),
        momentum_data.get("ret_12m"),
    )

    revisions_score, revisions_grade = _score_revisions(
        analyst_data.get("eps_revisions_up"),
        analyst_data.get("eps_revisions_down"),
        analyst_data.get("target_upside_pct"),
    )

    # Composite: weighted average. Momentum + Profitability emphasized
    # (academic evidence: these have strongest forward returns)
    weights = {"value": 0.20, "growth": 0.20, "profit": 0.20,
               "momentum": 0.25, "revisions": 0.15}
    composite = (value_score    * weights["value"] +
                 growth_score   * weights["growth"] +
                 profit_score   * weights["profit"] +
                 momentum_score * weights["momentum"] +
                 revisions_score * weights["revisions"])
    composite_grade = _percentile_to_grade(composite)

    return {
        "composite_score": round(composite, 1),
        "composite_grade": composite_grade,
        "factors": {
            "value":     {"score": round(value_score, 1),     "grade": value_grade},
            "growth":    {"score": round(growth_score, 1),    "grade": growth_grade},
            "profit":    {"score": round(profit_score, 1),    "grade": profit_grade},
            "momentum":  {"score": round(momentum_score, 1),  "grade": momentum_grade},
            "revisions": {"score": round(revisions_score, 1), "grade": revisions_grade},
        },
        "weights": weights,
    }
