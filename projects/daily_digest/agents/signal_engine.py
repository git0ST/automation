"""
Signal Engine v2 — multi-market, adaptive, prediction-tracking.

Changes from v1:
  ─ Multi-market routing: equity / crypto / forex / commodity / index / bond
    Each market type has distinct source weights, vol profiles, and position caps.
  ─ Adaptive weights: loads learned weights from model_weights table (learning_loop).
    Falls back to market-profile defaults when insufficient data.
  ─ Cross-market dampening: VIX spike, DXY surge, extreme F&G all modulate signals.
  ─ Prediction records: every fired signal writes to `predictions` table so the
    learning loop can correlate outcomes and improve the model over time.
  ─ Vol-normalized sizing: position sizes scaled to equal vol contribution
    (50%-vol crypto gets half the size of 25%-vol equity at same signal strength).

Confluence scoring (0–100):
    Weights come from model_weights table (regime-specific if available).
    Default weights per market profile in intelligence/market_router.py.

Signal fires when confluence ≥ market_profile.min_confluence.
"""
from __future__ import annotations

import asyncio
import math
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional


# ── Constants ─────────────────────────────────────────────────────────────────

R_TARGET_1 = 1.5
R_TARGET_2 = 2.5


# ── ATR helpers ───────────────────────────────────────────────────────────────

def _atr14_from_daily(prices: list[float]) -> Optional[float]:
    if len(prices) < 15:
        return None
    changes = [abs(prices[i] - prices[i - 1]) for i in range(1, len(prices))]
    return sum(changes[-14:]) / 14


# ── Adaptive weight loader ─────────────────────────────────────────────────────

def _load_weights(market_type: str, regime: Optional[str]) -> dict:
    """
    Load signal weights from learning_loop model_weights table.
    Returns market-profile defaults if no learned weights exist.

    Key: we map model_weights (technical/sentiment/analyst/vol) to our
    5-layer system (technical/options/sentiment/fundamental/regime).
    Options roughly corresponds to the 'analyst' weight.
    """
    from intelligence.market_router import MARKET_PROFILES
    profile = MARKET_PROFILES.get(market_type, MARKET_PROFILES["equity"])

    try:
        from shared.learning_loop import load_active_weights
        mw = load_active_weights(regime=regime)
        # Map learning_loop weights to our layers
        # learning_loop has: technical_w, sentiment_w, analyst_w, vol_w
        # We have:           w_technical, w_options, w_sentiment, w_fundamental, w_regime
        total_base = (mw.get("technical_w", 0.35) + mw.get("sentiment_w", 0.25) +
                      mw.get("analyst_w", 0.25))
        if total_base > 0:
            return {
                "w_technical":   mw.get("technical_w", profile["w_technical"]),
                "w_options":     mw.get("analyst_w",   profile["w_options"]),
                "w_sentiment":   mw.get("sentiment_w", profile["w_sentiment"]),
                "w_fundamental": profile["w_fundamental"],
                "w_regime":      profile["w_regime"],
                "conf_mult":     mw.get("conf_multiplier", 1.0),
                "source":        mw.get("version", "baseline"),
            }
    except Exception:
        pass

    return {
        "w_technical":   profile["w_technical"],
        "w_options":     profile["w_options"],
        "w_sentiment":   profile["w_sentiment"],
        "w_fundamental": profile["w_fundamental"],
        "w_regime":      profile["w_regime"],
        "conf_mult":     1.0,
        "source":        "market_profile_defaults",
    }


# ── Confluence layer evaluators ───────────────────────────────────────────────

def _technical_layer(intraday_data: Optional[dict], daily_tech: Optional[dict],
                     market_type: str) -> tuple[float, str]:
    """Returns (strength 0-1, direction)."""
    votes = []

    if daily_tech and "error" not in daily_tech:
        t_sig = daily_tech.get("trend_signal", "neutral")
        r_sig = daily_tech.get("rsi_signal", "neutral")
        votes.append(1 if t_sig == "bullish" else -1 if t_sig == "bearish" else 0)
        # RSI contributes independently
        rsi = daily_tech.get("rsi14")
        if rsi:
            if rsi > 70:   votes.append(-0.5)   # overbought — reduce bullish
            elif rsi < 30: votes.append(1)       # oversold — mean reversion
            elif rsi > 55: votes.append(0.5)
            elif rsi < 45: votes.append(-0.5)

    if intraday_data and market_type != "forex":
        lb       = intraday_data.get("latest_bar", {})
        vwap_sig = intraday_data.get("vwap_signal", "at")
        rsi      = lb.get("rsi_14")

        if vwap_sig == "above": votes.append(1)
        elif vwap_sig == "below": votes.append(-1)

        if rsi:
            if rsi > 60:   votes.append(0.5)
            elif rsi < 40: votes.append(-0.5)

        # Open Range Breakout — highest-confidence intraday pattern
        or_ = intraday_data.get("open_range", {})
        price = lb.get("close")
        if price and or_.get("high") and or_.get("low"):
            if price > or_["high"]:   votes.append(1.5)   # ORB long
            elif price < or_["low"]:  votes.append(-1.5)  # ORB short

        # Unusual volume amplifies existing directional votes
        if intraday_data.get("unusual_vol") and votes:
            dominant = 1 if sum(votes) > 0 else -1
            votes.append(dominant * 0.5)

    if not votes:
        return 0.0, "neutral"

    avg       = sum(votes) / len(votes)
    direction = "bullish" if avg > 0.15 else "bearish" if avg < -0.15 else "neutral"
    strength  = min(1.0, abs(avg))
    return round(strength, 4), direction


def _options_layer(signals: list[dict], ticker: str,
                   market_type: str) -> tuple[float, str]:
    """Relevant only for equity/index/commodity. Returns (strength, direction)."""
    if market_type in ("crypto", "forex"):
        return 0.0, "neutral"  # no options data for these markets

    relevant = [
        s for s in signals
        if s.get("source") == "options"
        and ticker.upper() in (s.get("title") or "").upper()
    ]
    if not relevant:
        return 0.0, "neutral"

    bull_s = bear_s = 0.0
    for s in relevant:
        title   = (s.get("title") or "").lower()
        payload = s.get("option_data") or s.get("payload") or {}
        sent    = s.get("sentiment_label", "neutral")
        is_call = "call" in title or payload.get("type") == "call"
        is_put  = "put"  in title or payload.get("type") == "put"
        is_block = any(k in title for k in ("sweep", "block", "unusual", "large"))
        mult    = 1.6 if is_block else 1.0
        base    = abs(float(s.get("sentiment_score") or 0.3))
        if is_call or sent == "bullish": bull_s += base * mult
        elif is_put or sent == "bearish": bear_s += base * mult

    total = bull_s + bear_s
    if total < 0.05:
        return 0.0, "neutral"
    if bull_s > bear_s:
        return round(min(1.0, bull_s / total), 4), "bullish"
    return round(min(1.0, bear_s / total), 4), "bearish"


def _sentiment_layer(items: list[dict], ticker: str,
                     market_type: str) -> tuple[float, str]:
    """VADER aggregate sentiment for items mentioning this ticker."""
    relevant = [
        it for it in items
        if ticker.upper() in " ".join(it.get("entities") or []).upper()
        or ticker.upper() in (it.get("title") or "").upper()
    ]

    # For crypto, also pick up items tagged with 'crypto' sector
    if market_type == "crypto" and not relevant:
        relevant = [
            it for it in items
            if it.get("sector") == "crypto"
            and it.get("sentiment_label") != "neutral"
        ][:5]

    if not relevant:
        return 0.0, "neutral"

    scores = [float(it.get("sentiment_score") or 0) for it in relevant]
    avg    = sum(scores) / len(scores)
    n      = len(relevant)

    direction = "bullish" if avg > 0.08 else "bearish" if avg < -0.08 else "neutral"
    # Conviction scales with item count (log-damped after 5)
    conviction = min(1.0, abs(avg) * math.log(min(n, 10) + 1) / 1.8)
    return round(conviction, 4), direction


def _fundamental_layer(quant_score: Optional[float],
                       market_type: str) -> tuple[float, str]:
    """Quant score signal. Only meaningful for equity/index."""
    if market_type in ("crypto", "forex", "bond"):
        return 0.0, "neutral"
    if quant_score is None:
        return 0.0, "neutral"
    if quant_score >= 72:
        return round(min(1.0, (quant_score - 50) / 45), 4), "bullish"
    if quant_score <= 32:
        return round(min(1.0, (50 - quant_score) / 45), 4), "bearish"
    return 0.15, "neutral"


def _crypto_fg_layer(fg_crypto: Optional[int]) -> tuple[float, str]:
    """
    Crypto-specific Fear & Greed layer.
    Extreme Fear → contrarian long; Extreme Greed → caution / short.
    """
    if fg_crypto is None:
        return 0.0, "neutral"
    if fg_crypto <= 15:
        return 0.8, "bullish"   # extreme fear = capitulation, bounce likely
    if fg_crypto <= 30:
        return 0.5, "bullish"
    if fg_crypto >= 85:
        return 0.7, "bearish"   # extreme greed = overextension
    if fg_crypto >= 70:
        return 0.35, "bearish"
    return 0.0, "neutral"


def _macro_layer(macro_dict: dict, market_type: str,
                 regime: Optional[str]) -> tuple[float, str]:
    """
    Macro signal for forex/bond/commodity where macro dominates.
    For equity, macro is already captured in regime_fit.
    """
    if market_type in ("equity", "index"):
        return 0.0, "neutral"

    from intelligence.market_router import regime_bias
    bias = regime_bias(market_type, regime)
    if not bias:
        return 0.0, "neutral"

    # Confidence based on regime signal strength
    vix = macro_dict.get("VIXCLS")
    ffr = macro_dict.get("FEDFUNDS")
    t10 = macro_dict.get("T10Y2Y")

    strength = 0.3  # base
    if vix and vix > 25:  strength += 0.15  # elevated vol = clearer macro signal
    if t10 and t10 < 0:   strength += 0.10  # inverted curve amplifies deflation/stagflation
    if ffr and ffr > 4.5: strength += 0.10  # restrictive policy

    direction = "bullish" if bias in ("long",) else "bearish" if bias in ("short", "long_dxy") else "neutral"
    return round(min(1.0, strength), 4), direction


# ── Confluence aggregation ────────────────────────────────────────────────────

def _compute_confluence(
    tech:    tuple[float, str],
    options: tuple[float, str],
    sent:    tuple[float, str],
    fund:    tuple[float, str],
    regime:  Optional[str],
    market_type: str,
    weights: dict,
    cross_factor: float = 1.0,
    macro_layer: tuple[float, str] = (0.0, "neutral"),
) -> tuple[float, str]:
    """
    Weighted confluence score (0–100) and net direction.
    Cross_factor from market_router.cross_market_factor() modulates final score.
    """
    def sign(d): return 1 if d in ("bullish", "long") else -1 if d in ("bearish", "short") else 0

    layers = {
        "technical":   (tech[0],    sign(tech[1]),    weights["w_technical"]),
        "options":     (options[0], sign(options[1]), weights["w_options"]),
        "sentiment":   (sent[0],    sign(sent[1]),    weights["w_sentiment"]),
        "fundamental": (fund[0],    sign(fund[1]),    weights["w_fundamental"]),
        "macro":       (macro_layer[0], sign(macro_layer[1]), weights["w_regime"] * 0.5),
    }

    from intelligence.market_router import get_profile, regime_bias
    bias = regime_bias(market_type, regime)

    # Add regime fit as a soft vote
    if bias in ("long", "short"):
        regime_vote = 1.0 if bias == "long" else -1.0
        layers["regime_fit"] = (weights["w_regime"], regime_vote, weights["w_regime"])

    # Weighted signed score
    w_sum = sum(s * v * w for _, (s, v, w) in layers.items() if s > 0)
    total_w = sum(w for s, v, w in layers.values() if s > 0)

    if total_w < 1e-6:
        return 0.0, "neutral"

    net = w_sum / total_w
    direction = "bullish" if net > 0.08 else "bearish" if net < -0.08 else "neutral"

    # Raw confluence = |net| × 100, then dampen/amplify by cross-market factor
    raw = abs(net) * 100
    conf_mult = weights.get("conf_mult", 1.0)
    confluence = min(100.0, raw * conf_mult * cross_factor)

    return round(confluence, 1), direction


# ── Entry / stop / target ─────────────────────────────────────────────────────

def _calc_levels(price: float, direction: str,
                 atr: Optional[float], atr_stop_mult: float) -> dict:
    if not atr or atr <= 0:
        atr = price * 0.012   # 1.2% fallback

    stop_dist = atr * atr_stop_mult

    if direction in ("bullish", "long"):
        entry    = price
        stop     = round(entry - stop_dist, 6)
        risk     = entry - stop
        target_1 = round(entry + risk * R_TARGET_1, 6)
        target_2 = round(entry + risk * R_TARGET_2, 6)
        trade_dir = "long"
    else:
        entry    = price
        stop     = round(entry + stop_dist, 6)
        risk     = stop - entry
        target_1 = round(entry - risk * R_TARGET_1, 6)
        target_2 = round(entry - risk * R_TARGET_2, 6)
        trade_dir = "short"

    return {
        "entry_price":    round(entry, 6),
        "stop_loss":      stop,
        "target_1":       target_1,
        "target_2":       target_2,
        "risk_per_share": round(max(risk, 1e-8), 6),
        "atr_14":         round(atr, 6),
        "direction":      trade_dir,
    }


# ── Kelly sizing ──────────────────────────────────────────────────────────────

def _kelly_size(confluence: float, r_ratio: float,
                market_type: str, annualised_vol: Optional[float],
                event_risk: bool = False) -> dict:
    """Half-Kelly, vol-normalized, market-type-capped position size."""
    from intelligence.market_router import MARKET_PROFILES, normalize_position_for_vol

    profile   = MARKET_PROFILES.get(market_type, MARKET_PROFILES["equity"])
    cap       = profile["max_position_pct"]
    kelly_cap = profile["kelly_cap"]

    p = 0.40 + (confluence / 100.0) * 0.33
    p = max(0.35, min(0.78, p))
    q = 1.0 - p
    b = max(r_ratio, 1.0)

    raw_kelly  = (p * b - q) / b
    half_kelly = raw_kelly * kelly_cap
    if event_risk:
        half_kelly *= 0.5

    pos_pct = max(0.005, min(cap, half_kelly))

    # Vol-normalize: equal risk contribution across markets
    vol_adj = normalize_position_for_vol(pos_pct, market_type, annualised_vol)

    return {
        "kelly_fraction": round(raw_kelly, 4),
        "position_pct":   vol_adj,
        "win_rate_est":   round(p, 3),
        "r_ratio":        round(b, 2),
    }


# ── Signal type classifier ────────────────────────────────────────────────────

def _classify_type(intraday_data: Optional[dict], direction: str,
                   rsi: Optional[float], options_strength: float,
                   market_type: str) -> str:
    if intraday_data and market_type != "forex":
        lb  = intraday_data.get("latest_bar", {})
        or_ = intraday_data.get("open_range", {})
        px  = lb.get("close")
        if px and or_.get("high") and px > or_["high"]: return "orb_breakout"
        if px and or_.get("low")  and px < or_["low"]:  return "orb_breakout"
        if intraday_data.get("unusual_vol"):             return "volume_spike"
        vwap_sig = intraday_data.get("vwap_signal", "at")
        if vwap_sig in ("above", "below"):               return "vwap_deviation"
    if rsi and rsi <= 28:  return "mean_reversion_long"
    if rsi and rsi >= 72:  return "mean_reversion_short"
    if options_strength > 0.55: return "options_flow"
    if market_type == "crypto": return "crypto_momentum"
    if market_type == "forex":  return "macro_forex"
    if market_type == "commodity": return "commodity_macro"
    return "momentum"


# ── Prediction record writer ──────────────────────────────────────────────────

def _write_prediction(sig: dict, quant_score: Optional[float],
                      quant_grade: Optional[str], vix: Optional[float],
                      srs: Optional[float]) -> None:
    """
    Write prediction record for learning_loop outcome correlation.
    This is the bridge between signal_engine and the self-improvement loop.
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        return
    try:
        from supabase import create_client
        from intelligence.market_router import vix_regime
        client = create_client(url, key)
        rat    = sig.get("rationale", {})
        layers = rat.get("layers", {})

        client.table("predictions").insert({
            "ticker":           sig["ticker"],
            "direction":        "bullish" if sig["direction"] == "long" else "bearish",
            "confidence_pct":   sig["confluence"],
            "source_page":      "signal_engine_v2",
            "price_at_pred":    sig["entry_price"],
            # Component signals
            "tech_signal":      layers.get("technical", {}).get("direction"),
            "tech_strength":    layers.get("technical", {}).get("strength"),
            "sent_signal":      layers.get("sentiment", {}).get("direction"),
            "sent_strength":    layers.get("sentiment", {}).get("strength"),
            "analyst_signal":   layers.get("options", {}).get("direction"),
            "analyst_strength": layers.get("options", {}).get("strength"),
            "vol_regime":       vix_regime(vix),
            "quant_score":      quant_score,
            "quant_grade":      quant_grade,
            # Learning columns (from migration 010)
            "strategy_name":    sig["signal_type"],
            "regime_at_pred":   sig.get("regime"),
            "srs_at_pred":      srs,
            "market_type":      sig.get("market_type", "equity"),
            "horizon":          sig.get("horizon", "short"),
        }).execute()
    except Exception as e:
        print(f"[signal_engine] prediction write failed: {e}")


# ── Supabase trade signal persistence ────────────────────────────────────────

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
        print(f"[signal_engine] save trade signals failed: {e}")


# ── Main synthesis function ────────────────────────────────────────────────────

async def generate_trade_signals(
    pipeline_cache: dict,
    intraday_items: Optional[list[dict]] = None,
    regime:         Optional[str]        = None,
    max_signals:    int                  = 15,
) -> list[dict]:
    """
    Synthesize execution-grade trade signals from pipeline data.

    Multi-market: processes equities, crypto, forex, commodities in one pass.
    Adaptive: loads learned weights from model_weights for current regime.
    Prediction-tracking: every signal → predictions record for learning loop.

    Returns list of signal dicts sorted by confluence descending.
    """
    from intelligence.market_router import (
        classify_ticker, get_profile, cross_market_factor,
        vix_regime, MARKET_PROFILES,
    )

    items      = pipeline_cache.get("items", [])
    pipe_sigs  = pipeline_cache.get("signals", [])
    market     = pipeline_cache.get("market", [])
    macro_list = pipeline_cache.get("macro", [])

    # Build macro dict {series_id: value}
    macro_dict: dict[str, float] = {
        m.get("series_id"): m.get("value")
        for m in macro_list if m.get("series_id") and m.get("value") is not None
    }

    # Extract cross-market state
    vix        = macro_dict.get("VIXCLS")
    ffr        = macro_dict.get("FEDFUNDS")
    t10y2y     = macro_dict.get("T10Y2Y")

    # DXY 1d change from forex macro
    dxy_chg = None
    for m in macro_list:
        if m.get("series_id") == "DX-Y.NYB" and m.get("change_pct"):
            dxy_chg = float(m["change_pct"])
            break

    # Fear & Greed (stocks + crypto)
    fg_stocks = fg_crypto = None
    for fg in pipeline_cache.get("fear_greed", []):
        if isinstance(fg, dict):
            if fg.get("source") == "stocks" and fg_stocks is None:
                fg_stocks = fg.get("value")
            elif fg.get("source") == "crypto" and fg_crypto is None:
                fg_crypto = fg.get("value")

    # SRS for prediction logging
    risk = pipeline_cache.get("risk") or {}
    srs  = risk.get("srs") if isinstance(risk, dict) else None

    # Build intraday index: ticker → intraday_data
    intra_index: dict[str, dict] = {}
    if intraday_items:
        for it in intraday_items:
            if it.get("intraday_data"):
                intra_index[it["intraday_data"]["ticker"]] = it["intraday_data"]

    # Build price index from market data (equities + crypto)
    price_index: dict[str, float] = {
        m["ticker"]: m["price"]
        for m in market if m.get("ticker") and m.get("price")
    }

    # Load quant scores (most recent opportunity scan)
    quant_index: dict[str, dict] = {}
    try:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
        if url and key:
            from supabase import create_client
            client = create_client(url, key)
            rows = (client.table("opportunity_snapshots")
                    .select("ticker,quant_score,quant_grade,direction,confidence")
                    .order("scanned_at", desc=True)
                    .limit(150)
                    .execute()).data or []
            seen: set[str] = set()
            for r in rows:
                t = r.get("ticker", "")
                if t and t not in seen:
                    quant_index[t] = r
                    seen.add(t)
    except Exception:
        pass

    # Event risk
    try:
        from sources.earnings_calendar import get_event_risk_tickers
        event_risk_set = get_event_risk_tickers(days=3)
    except Exception:
        event_risk_set = set()

    # Fetch daily technicals (batch for all candidates)
    candidates = list(set(list(intra_index.keys()) + list(price_index.keys())))[:40]
    from agents.math_agent import compute_technical, _fetch_prices

    tech_results = await asyncio.gather(
        *[compute_technical(t, period="3mo") for t in candidates],
        return_exceptions=True,
    )
    tech_index: dict[str, dict] = {
        t: r for t, r in zip(candidates, tech_results)
        if isinstance(r, dict) and "error" not in r
    }

    # Fetch daily prices for ATR + vol
    price_results = await asyncio.gather(
        *[_fetch_prices(t, "3mo") for t in candidates],
        return_exceptions=True,
    )
    prices_index: dict[str, list[float]] = {
        t: r for t, r in zip(candidates, price_results)
        if isinstance(r, list) and r and len(r) >= 15
    }

    # Expiry: next 4pm ET close
    now_utc    = datetime.now(timezone.utc)
    day_close  = now_utc.replace(hour=21, minute=0, second=0, microsecond=0)
    if now_utc > day_close:
        day_close = (now_utc + timedelta(days=1)).replace(
            hour=21, minute=0, second=0, microsecond=0)

    signals_out = []

    for ticker in candidates:
        price = price_index.get(ticker)
        if not price or price <= 0:
            continue

        # Classify market + load profile + adaptive weights
        profile    = get_profile(ticker)
        mtype      = profile["market_type"]
        weights    = _load_weights(mtype, regime)

        # Get per-market inputs
        intra      = intra_index.get(ticker)
        tech       = tech_index.get(ticker)
        qrow       = quant_index.get(ticker, {})
        prices     = prices_index.get(ticker, [])
        atr        = _atr14_from_daily(prices) if prices else None
        ev_risk    = ticker in event_risk_set

        # Annualised vol for position sizing
        ann_vol = None
        if prices and len(prices) >= 20:
            import math as _m
            rets = [_m.log(prices[i] / prices[i-1]) for i in range(1, len(prices))]
            mean = sum(rets) / len(rets)
            var  = sum((r - mean)**2 for r in rets) / max(len(rets)-1, 1)
            ann_vol = _m.sqrt(var * 252)

        # Score all layers
        tech_l  = _technical_layer(intra, tech, mtype)
        opts_l  = _options_layer(pipe_sigs, ticker, mtype)
        sent_l  = _sentiment_layer(items, ticker, mtype)
        fund_l  = _fundamental_layer(qrow.get("quant_score"), mtype)
        macro_l = _macro_layer(macro_dict, mtype, regime)

        # Crypto: override sentiment with F&G if stronger
        if mtype == "crypto":
            fg_l = _crypto_fg_layer(fg_crypto)
            if fg_l[0] > sent_l[0]:
                sent_l = fg_l

        # Cross-market dampen/amplify
        cross_f = cross_market_factor(
            mtype,
            direction=None,   # direction unknown yet — will apply after
            vix=vix,
            dxy_chg_1d=dxy_chg,
            fg_stocks=fg_stocks,
            regime=regime,
        )

        confluence, direction = _compute_confluence(
            tech_l, opts_l, sent_l, fund_l,
            regime=regime, market_type=mtype, weights=weights,
            cross_factor=cross_f, macro_layer=macro_l,
        )

        # Now re-run cross_market_factor with known direction
        cross_f = cross_market_factor(
            mtype, direction=direction,
            vix=vix, dxy_chg_1d=dxy_chg, fg_stocks=fg_stocks, regime=regime,
        )
        confluence = round(min(100.0, confluence * cross_f), 1)

        if confluence < profile["min_confluence"] or direction == "neutral":
            continue

        # Entry / stop / target
        levels = _calc_levels(price, direction, atr, profile["atr_stop_mult"])
        sizing = _kelly_size(confluence, R_TARGET_1, mtype, ann_vol, event_risk=ev_risk)

        # RSI for logging
        rsi_val = (intra["latest_bar"]["rsi_14"] if intra else None) or (tech.get("rsi14") if tech else None)

        signal_type = _classify_type(intra, direction, rsi_val, opts_l[0], mtype)
        horizon     = profile.get("horizon_default", "short")

        sig = {
            "id":             str(uuid.uuid4()),
            "ticker":         ticker,
            "market_type":    mtype,
            "signal_type":    signal_type,
            "direction":      levels["direction"],
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
            "horizon":        horizon,
            "fired_at":       now_utc.isoformat(),
            "expires_at":     day_close.isoformat(),
            "event_risk":     ev_risk,
            "cross_factor":   cross_f,
            "rationale": {
                "layers": {
                    "technical":   {"strength": round(tech_l[0], 3), "direction": tech_l[1]},
                    "options":     {"strength": round(opts_l[0], 3), "direction": opts_l[1]},
                    "sentiment":   {"strength": round(sent_l[0], 3), "direction": sent_l[1]},
                    "fundamental": {"strength": round(fund_l[0], 3), "direction": fund_l[1]},
                    "macro":       {"strength": round(macro_l[0], 3), "direction": macro_l[1]},
                },
                "weights_source": weights["source"],
                "cross_factor":  cross_f,
                "vix":           vix,
                "dxy_chg":       dxy_chg,
                "fg_stocks":     fg_stocks,
                "fg_crypto":     fg_crypto if mtype == "crypto" else None,
                "quant_score":   qrow.get("quant_score"),
                "quant_grade":   qrow.get("quant_grade"),
                "rsi":           rsi_val,
                "ann_vol_pct":   round(ann_vol * 100, 1) if ann_vol else None,
                "vwap_signal":   intra.get("vwap_signal") if intra else None,
                "unusual_vol":   intra.get("unusual_vol") if intra else None,
                "event_risk":    ev_risk,
                "win_rate_est":  sizing["win_rate_est"],
            },
        }
        signals_out.append(sig)

    # Rank by confluence, limit
    signals_out.sort(key=lambda x: x["confluence"], reverse=True)
    signals_out = signals_out[:max_signals]

    # Persist trade signals + write prediction records (non-blocking)
    if signals_out:
        _save_trade_signals(signals_out)
        for sig in signals_out:
            _write_prediction(
                sig,
                quant_score=sig["rationale"].get("quant_score"),
                quant_grade=sig["rationale"].get("quant_grade"),
                vix=vix, srs=srs,
            )

    return signals_out
