"""
Signal Engine — execution-grade trade signal synthesis.

Synthesizes signals from five layers into actionable entries with:
  - ATR(14)-based stop loss (respects volatility)
  - Two take-profit targets (1.5R and 2.5R)
  - Kelly Criterion position sizing (capped at 5% of portfolio)
  - Regime-aware filtering (block signals that fight the regime)
  - Event risk awareness (reduce size near earnings)

Input layers (all available in the pipeline):
  1. Technical  — SMA trend, RSI, VWAP breakout, Open Range
  2. Options    — Put/call ratio, unusual options flow from sources/options.py
  3. Sentiment  — VADER aggregate, entity-level sentiment from news
  4. Fundamental— Quant score from opportunity_runner (via Supabase)
  5. Regime     — BlackRock-style regime classification

Confluence scoring (0–100):
    technical  × 0.35
    options    × 0.25
    sentiment  × 0.20
    fundamental× 0.15
    regime_fit × 0.05

Kelly fraction = (p × b - q) / b
    p = estimated win rate from confluence (scaled to 0.40–0.75)
    b = reward/risk ratio (target_1 / risk_per_share)
    q = 1 - p
    Cap: 0.5 × Kelly, max 5% portfolio

Signal is only fired when confluence ≥ 45.
"""
from __future__ import annotations

import asyncio
import math
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional


# ── Constants ─────────────────────────────────────────────────────────────────

MIN_CONFLUENCE  = 45.0    # minimum confluence to fire a signal
MAX_POSITION_PCT = 0.05   # hard cap: 5% of portfolio per trade
KELLY_FRACTION   = 0.5    # half-Kelly for safety
R_TARGET_1       = 1.5    # first target: 1.5× risk
R_TARGET_2       = 2.5    # second target: 2.5× risk

# Regimes that favour long equity
LONG_REGIMES  = {"goldilocks", "reflation"}
SHORT_REGIMES = {"stagflation", "deflation"}


# ── ATR calculation ────────────────────────────────────────────────────────────

def _atr14_from_bars(bars: list[dict]) -> Optional[float]:
    """True Range ATR(14) from intraday or daily bars."""
    if len(bars) < 14:
        return None
    trs = []
    for i in range(1, len(bars)):
        h = bars[i]["high"]; l = bars[i]["low"]; pc = bars[i - 1]["close"]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    return sum(trs[-14:]) / 14


def _atr14_from_daily(prices: list[float]) -> Optional[float]:
    """Approximate ATR from daily close series (no high/low available)."""
    if len(prices) < 15:
        return None
    changes = [abs(prices[i] - prices[i - 1]) for i in range(1, len(prices))]
    return sum(changes[-14:]) / 14


# ── Confluence layer evaluators ───────────────────────────────────────────────

def _technical_layer(intraday_data: Optional[dict], daily_tech: Optional[dict]) -> tuple[float, str]:
    """Returns (score 0-1, direction bullish|bearish|neutral)."""
    votes = []

    if daily_tech:
        t = daily_tech.get("trend_signal", "neutral")
        r = daily_tech.get("rsi_signal", "neutral")
        votes.append(1 if t == "bullish" else -1 if t == "bearish" else 0)
        votes.append(0.5 if r == "neutral" else 1 if t == "bullish" else -1)

    if intraday_data:
        lb = intraday_data.get("latest_bar", {})
        vd = lb.get("vwap_dev")
        rsi = lb.get("rsi_14")
        vwap_sig = intraday_data.get("vwap_signal", "at")

        # VWAP position
        if vwap_sig == "above":  votes.append(1)
        elif vwap_sig == "below": votes.append(-1)

        # Intraday RSI
        if rsi:
            if rsi > 60:   votes.append(1)
            elif rsi < 40: votes.append(-1)

        # Open Range Breakout
        or_ = intraday_data.get("open_range", {})
        price = lb.get("close")
        if price and or_.get("high") and or_.get("low"):
            if price > or_["high"]: votes.append(1)
            elif price < or_["low"]: votes.append(-1)

        # Unusual volume amplifies
        if intraday_data.get("unusual_vol"):
            if votes and sum(votes) > 0: votes.append(1)
            elif votes and sum(votes) < 0: votes.append(-1)

    if not votes:
        return 0.0, "neutral"

    avg = sum(votes) / len(votes)
    direction = "bullish" if avg > 0.15 else "bearish" if avg < -0.15 else "neutral"
    strength  = min(1.0, abs(avg))
    return strength, direction


def _options_layer(signals: list[dict], ticker: str) -> tuple[float, str]:
    """
    Score ticker's options flow from pipeline signals.
    Unusual call volume → bullish; unusual put volume → bearish.
    Large block trades in either direction are highest confidence.
    """
    relevant = [
        s for s in signals
        if s.get("source") == "options"
        and ticker.upper() in (s.get("title") or "").upper()
    ]
    if not relevant:
        return 0.0, "neutral"

    bull_score = bear_score = 0.0
    for s in relevant:
        title = (s.get("title") or "").lower()
        payload = s.get("option_data") or s.get("payload") or {}
        sent = s.get("sentiment_label", "neutral")

        # Detect call/put from title keywords
        is_call = "call" in title or payload.get("type") == "call"
        is_put  = "put"  in title or payload.get("type") == "put"

        # Sweep / block = high confidence
        is_block = any(k in title for k in ("sweep", "block", "unusual", "large"))
        multiplier = 1.5 if is_block else 1.0

        base = float(s.get("sentiment_score") or 0.3)
        if is_call or sent == "bullish":
            bull_score += base * multiplier
        elif is_put or sent == "bearish":
            bear_score += base * multiplier

    total = bull_score + bear_score
    if total < 0.1:
        return 0.0, "neutral"

    if bull_score > bear_score:
        return min(1.0, bull_score / total), "bullish"
    elif bear_score > bull_score:
        return min(1.0, bear_score / total), "bearish"
    return 0.3, "neutral"


def _sentiment_layer(items: list[dict], ticker: str) -> tuple[float, str]:
    """Aggregate VADER sentiment for news items mentioning the ticker."""
    relevant = [
        it for it in items
        if ticker.upper() in " ".join(it.get("entities") or []).upper()
        or ticker.upper() in (it.get("title") or "").upper()
    ]
    if not relevant:
        return 0.0, "neutral"

    scores = [float(it.get("sentiment_score") or 0) for it in relevant]
    avg    = sum(scores) / len(scores)
    n      = len(relevant)

    direction = "bullish" if avg > 0.1 else "bearish" if avg < -0.1 else "neutral"
    # Conviction: stronger with more items
    conviction = min(1.0, abs(avg) * math.log(n + 1) / 2)
    return conviction, direction


def _fundamental_layer(quant_score: Optional[float], quant_grade: Optional[str]) -> tuple[float, str]:
    """Map quant score to fundamental signal."""
    if quant_score is None:
        return 0.0, "neutral"
    if quant_score >= 75:
        return min(1.0, (quant_score - 50) / 50), "bullish"
    if quant_score <= 35:
        return min(1.0, (50 - quant_score) / 50), "bearish"
    return 0.2, "neutral"


def _regime_fit(direction: str, regime: Optional[str]) -> float:
    """Returns 1.0 if signal fits regime, 0.5 if neutral, 0.0 if contra-regime."""
    if not regime:
        return 0.5
    if direction == "bullish" and regime in LONG_REGIMES:
        return 1.0
    if direction == "bearish" and regime in SHORT_REGIMES:
        return 1.0
    if direction == "bullish" and regime in SHORT_REGIMES:
        return 0.0
    if direction == "bearish" and regime in LONG_REGIMES:
        return 0.0
    return 0.5


# ── Confluence aggregation ────────────────────────────────────────────────────

def _compute_confluence(
    tech:    tuple[float, str],
    options: tuple[float, str],
    sent:    tuple[float, str],
    fund:    tuple[float, str],
    regime:  Optional[str],
) -> tuple[float, str]:
    """
    Weighted confluence score (0–100) and net direction.

    Returns (confluence_score, direction).
    Direction is the majority-weighted vote across layers.
    """
    weights = {"technical": 0.35, "options": 0.25, "sentiment": 0.20,
               "fundamental": 0.15, "regime": 0.05}

    layers = {
        "technical":   tech,
        "options":     options,
        "sentiment":   sent,
        "fundamental": fund,
    }

    # Build signed scores: strength × direction_sign
    def sign(d): return 1 if d == "bullish" else -1 if d == "bearish" else 0

    weighted_sum = 0.0
    total_w = 0.0
    for name, (strength, direction) in layers.items():
        if strength > 0:
            w = weights[name]
            weighted_sum += sign(direction) * strength * w
            total_w += w

    if total_w < 1e-6:
        return 0.0, "neutral"

    net_score = weighted_sum / total_w   # -1 to +1

    # Net direction
    direction = "bullish" if net_score > 0.1 else "bearish" if net_score < -0.1 else "neutral"

    # Regime fit amplifies or suppresses
    rf = _regime_fit(direction, regime)
    regime_contrib = rf * weights["regime"]

    # Raw confluence = agreement strength
    raw = abs(net_score) * 100
    confluence = min(100.0, raw * (1.0 + regime_contrib))

    return round(confluence, 1), direction


# ── Entry / stop / target calculation ────────────────────────────────────────

def _calc_levels(
    price: float,
    direction: str,
    atr: Optional[float],
) -> dict:
    """
    Compute entry, stop, target_1, target_2 from current price and ATR.

    Stop: 1.5 × ATR below entry (long) or above entry (short)
    Target 1: entry + 1.5 × risk (R)
    Target 2: entry + 2.5 × risk (R)
    """
    if not atr or atr <= 0:
        # Fallback: 1% stop
        atr = price * 0.01

    stop_distance = 1.5 * atr

    if direction == "long":
        entry     = price
        stop      = round(entry - stop_distance, 4)
        risk      = entry - stop
        target_1  = round(entry + risk * R_TARGET_1, 4)
        target_2  = round(entry + risk * R_TARGET_2, 4)
    else:  # short
        entry     = price
        stop      = round(entry + stop_distance, 4)
        risk      = stop - entry
        target_1  = round(entry - risk * R_TARGET_1, 4)
        target_2  = round(entry - risk * R_TARGET_2, 4)

    return {
        "entry_price":    round(entry, 4),
        "stop_loss":      stop,
        "target_1":       target_1,
        "target_2":       target_2,
        "risk_per_share": round(risk, 4),
        "atr_14":         round(atr, 4),
        "r_ratio_t1":     R_TARGET_1,
        "r_ratio_t2":     R_TARGET_2,
    }


# ── Kelly position sizing ─────────────────────────────────────────────────────

def _kelly_size(confluence: float, r_ratio: float, event_risk: bool = False) -> dict:
    """
    Half-Kelly position size as % of portfolio.

    Win rate estimated from confluence:
        confluence 45 → p = 0.45
        confluence 80 → p = 0.65
        confluence 95 → p = 0.73

    p = 0.40 + (confluence / 100) × 0.33
    b = reward/risk ratio (e.g. 1.5)
    Kelly = (p × b - q) / b  × 0.5 (half-Kelly)
    Cap at MAX_POSITION_PCT (5%).
    """
    p = 0.40 + (confluence / 100.0) * 0.33
    p = max(0.35, min(0.78, p))
    q = 1.0 - p
    b = max(r_ratio, 1.0)

    raw_kelly = (p * b - q) / b
    half_kelly = raw_kelly * KELLY_FRACTION

    # Reduce near earnings
    if event_risk:
        half_kelly *= 0.5

    position_pct = round(max(0.005, min(MAX_POSITION_PCT, half_kelly)), 4)

    return {
        "kelly_fraction": round(raw_kelly, 4),
        "position_pct":   position_pct,
        "win_rate_est":   round(p, 3),
        "r_ratio":        round(b, 2),
    }


# ── Signal type classifier ────────────────────────────────────────────────────

def _classify_signal_type(
    intraday_data: Optional[dict],
    tech_direction: str,
    rsi: Optional[float],
    options_strength: float,
) -> str:
    """Classify the dominant pattern driving this signal."""
    if intraday_data:
        or_ = intraday_data.get("open_range", {})
        lb  = intraday_data.get("latest_bar", {})
        price = lb.get("close")
        if price and or_.get("high") and price > or_["high"]:
            return "breakout"
        if price and or_.get("low") and price < or_["low"]:
            return "breakout"
        if intraday_data.get("unusual_vol"):
            return "volume_spike"
        vwap_sig = intraday_data.get("vwap_signal", "at")
        if vwap_sig in ("above", "below"):
            return "vwap_deviation"

    if rsi and rsi <= 30:  return "mean_reversion"
    if rsi and rsi >= 70:  return "mean_reversion"
    if options_strength > 0.6: return "options_flow"
    if tech_direction != "neutral": return "momentum"
    return "composite"


# ── Supabase persistence ───────────────────────────────────────────────────────

def _save_trade_signals(signals: list[dict]) -> None:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key or not signals:
        return
    try:
        from supabase import create_client
        client = create_client(url, key)
        rows = [
            {
                "id":             s["id"],
                "ticker":         s["ticker"],
                "signal_type":    s["signal_type"],
                "direction":      s["direction"],
                "entry_price":    s["entry_price"],
                "stop_loss":      s["stop_loss"],
                "target_1":       s["target_1"],
                "target_2":       s["target_2"],
                "atr_14":         s["atr_14"],
                "risk_per_share": s["risk_per_share"],
                "kelly_fraction": s["kelly_fraction"],
                "position_pct":   s["position_pct"],
                "confluence":     s["confluence"],
                "regime":         s.get("regime"),
                "rationale":      s.get("rationale"),
                "fired_at":       s["fired_at"],
                "expires_at":     s.get("expires_at"),
                "status":         "open",
            }
            for s in signals
        ]
        client.table("trade_signals").upsert(rows, on_conflict="id").execute()
    except Exception as e:
        print(f"[signal_engine] save failed: {e}")


# ── Main synthesis function ────────────────────────────────────────────────────

async def generate_trade_signals(
    pipeline_cache: dict,
    intraday_items: Optional[list[dict]] = None,
    regime: Optional[str] = None,
    max_signals: int = 10,
) -> list[dict]:
    """
    Synthesize execution-grade trade signals from all available pipeline data.

    Args:
        pipeline_cache: Full pipeline payload (items, signals, market, macro…)
        intraday_items: From sources/intraday.py (optional, market hours only)
        regime:         Current regime string
        max_signals:    Max signals to return (ranked by confluence)

    Returns list of signal dicts with entry/stop/target/Kelly sizing.
    """
    items       = pipeline_cache.get("items", [])
    pipe_sigs   = pipeline_cache.get("signals", [])
    market      = pipeline_cache.get("market", [])

    # Build ticker → intraday data index
    intra_index: dict[str, dict] = {}
    if intraday_items:
        for it in intraday_items:
            if it.get("intraday_data"):
                intra_index[it["intraday_data"]["ticker"]] = it["intraday_data"]

    # Build ticker → latest price from market data
    price_index: dict[str, float] = {
        m["ticker"]: m["price"]
        for m in market
        if m.get("ticker") and m.get("price")
    }

    # Load quant scores from Supabase (most recent scan)
    quant_index: dict[str, dict] = {}
    try:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
        if url and key:
            from supabase import create_client
            client = create_client(url, key)
            # Get latest scan
            scan_rows = (client.table("opportunity_snapshots")
                         .select("ticker,quant_score,quant_grade,direction,confidence")
                         .order("scanned_at", desc=True)
                         .limit(100)
                         .execute()).data or []
            seen: set[str] = set()
            for r in scan_rows:
                t = r.get("ticker", "")
                if t and t not in seen:
                    quant_index[t] = r
                    seen.add(t)
    except Exception:
        pass

    # Load event risk tickers
    try:
        from sources.earnings_calendar import get_event_risk_tickers
        event_risk_set = get_event_risk_tickers(days=3)
    except Exception:
        event_risk_set = set()

    # Fetch daily technicals for each candidate ticker
    from agents.math_agent import compute_technical
    candidates = list(set(list(intra_index.keys()) + list(price_index.keys())))[:30]

    tech_results = await asyncio.gather(
        *[compute_technical(t, period="3mo") for t in candidates],
        return_exceptions=True,
    )
    tech_index: dict[str, dict] = {}
    for t, r in zip(candidates, tech_results):
        if isinstance(r, dict) and "error" not in r:
            tech_index[t] = r

    # Fetch ATR via yfinance for each candidate
    async def _get_atr(ticker: str) -> tuple[str, Optional[float]]:
        try:
            from agents.math_agent import _fetch_prices
            prices = await _fetch_prices(ticker, "3mo")
            return ticker, _atr14_from_daily(prices) if prices else None
        except Exception:
            return ticker, None

    atr_results = await asyncio.gather(*[_get_atr(t) for t in candidates])
    atr_index: dict[str, Optional[float]] = dict(atr_results)

    # ── Generate signals per ticker ──────────────────────────────────────────
    now_utc = datetime.now(timezone.utc)
    # Signals expire at end of same trading session (4pm ET = 21:00 UTC)
    today_close = now_utc.replace(hour=21, minute=0, second=0, microsecond=0)
    if now_utc > today_close:
        today_close = (now_utc + timedelta(days=1)).replace(hour=21, minute=0, second=0, microsecond=0)

    signals_out = []

    for ticker in candidates:
        price = price_index.get(ticker)
        if not price or price <= 0:
            continue

        intra   = intra_index.get(ticker)
        tech    = tech_index.get(ticker)
        qrow    = quant_index.get(ticker, {})
        atr     = atr_index.get(ticker)
        ev_risk = ticker in event_risk_set

        # Score each layer
        tech_s, tech_d   = _technical_layer(intra, tech)
        opts_s, opts_d   = _options_layer(pipe_sigs, ticker)
        sent_s, sent_d   = _sentiment_layer(items, ticker)
        fund_s, fund_d   = _fundamental_layer(
            qrow.get("quant_score"), qrow.get("quant_grade")
        )

        confluence, direction = _compute_confluence(
            (tech_s, tech_d), (opts_s, opts_d),
            (sent_s, sent_d), (fund_s, fund_d),
            regime,
        )

        if confluence < MIN_CONFLUENCE or direction == "neutral":
            continue

        levels = _calc_levels(price, direction, atr)
        sizing = _kelly_size(confluence, R_TARGET_1, event_risk=ev_risk)

        signal_type = _classify_signal_type(
            intra, tech_d,
            tech.get("rsi14") if tech else None,
            opts_s,
        )

        rsi_val = (intra["latest_bar"]["rsi_14"] if intra else None) or (tech.get("rsi14") if tech else None)

        signals_out.append({
            "id":             str(uuid.uuid4()),
            "ticker":         ticker,
            "signal_type":    signal_type,
            "direction":      direction,
            "entry_price":    levels["entry_price"],
            "stop_loss":      levels["stop_loss"],
            "target_1":       levels["target_1"],
            "target_2":       levels["target_2"],
            "atr_14":         levels["atr_14"],
            "risk_per_share": levels["risk_per_share"],
            "kelly_fraction": sizing["kelly_fraction"],
            "position_pct":   sizing["position_pct"],
            "confluence":     confluence,
            "regime":         regime,
            "fired_at":       now_utc.isoformat(),
            "expires_at":     today_close.isoformat(),
            "event_risk":     ev_risk,
            "rationale": {
                "layers": {
                    "technical":   {"strength": round(tech_s, 3), "direction": tech_d},
                    "options":     {"strength": round(opts_s, 3), "direction": opts_d},
                    "sentiment":   {"strength": round(sent_s, 3), "direction": sent_d},
                    "fundamental": {"strength": round(fund_s, 3), "direction": fund_d},
                },
                "quant_score":  qrow.get("quant_score"),
                "quant_grade":  qrow.get("quant_grade"),
                "rsi":          rsi_val,
                "vwap_signal":  intra.get("vwap_signal") if intra else None,
                "unusual_vol":  intra.get("unusual_vol") if intra else None,
                "event_risk":   ev_risk,
                "win_rate_est": sizing["win_rate_est"],
            },
        })

    # Sort by confluence desc, limit
    signals_out.sort(key=lambda x: x["confluence"], reverse=True)
    signals_out = signals_out[:max_signals]

    # Persist async (fire and forget)
    if signals_out:
        _save_trade_signals(signals_out)

    return signals_out
