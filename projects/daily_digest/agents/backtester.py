"""
Backtester — lightweight replay of local data-lake snapshots.

Simulates what signals would have fired on historical snapshots, then
correlates them against actual price moves to measure:
  • Per-strategy hit rate and expectancy
  • Per-regime signal quality
  • Per-market-type accuracy
  • Calibration: does a 70% confluence signal actually hit 70%?

Uses local ~/.intl_snapshots/*.json.gz files — no Supabase needed.
Loads market prices from yfinance for outcome measurement.

Typical use:
    from agents.backtester import run_backtest
    report = await run_backtest(days=14, min_confluence=50)
"""
from __future__ import annotations

import asyncio
import gzip
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

_SNAP_DIR = Path.home() / ".intl_snapshots"


# ── Load historical snapshots ─────────────────────────────────────────────────

def load_snapshots(days: int = 30) -> list[dict]:
    """
    Load full decompressed pipeline snapshots from the last N days.
    Skips corrupt or partial files silently.
    """
    if not _SNAP_DIR.exists():
        return []

    cutoff   = datetime.now(timezone.utc) - timedelta(days=days)
    snaps: list[dict] = []

    for path in sorted(_SNAP_DIR.glob("*.json.gz"), reverse=True):
        try:
            # Filename: YYYYMMDD_HHMMSS.json.gz
            stem = path.stem.replace(".json", "")
            ts   = datetime.strptime(stem, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if ts < cutoff:
            break
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                raw = json.load(f)
            # Decompressed snapshots may be either the full payload (list/dict)
            # or the metadata envelope written by write_snapshot
            payload = raw.get("payload", raw) if isinstance(raw, dict) else {}
            payload["_snapshot_ts"] = ts.isoformat()
            snaps.append(payload)
        except Exception:
            continue

    return snaps


def load_feature_snapshots(days: int = 30) -> list[dict]:
    """Load per-ticker feature rows from the feature store."""
    from shared.data_lake import load_feature_store
    return load_feature_store(days=days)


# ── Fetch outcome prices ──────────────────────────────────────────────────────

def fetch_price_history(tickers: list[str], period: str = "3mo") -> dict[str, list[float]]:
    """
    Return {ticker: [close0, close1, ...]} for the last N months.
    Used to compute returns after a hypothetical signal entry.
    Fails gracefully — missing tickers just excluded from the dict.
    """
    try:
        import yfinance as yf
        result: dict[str, list[float]] = {}
        for ticker in set(tickers):
            try:
                df = yf.download(ticker, period=period, interval="1d",
                                 auto_adjust=True, progress=False)
                if df.empty:
                    continue
                closes = df["Close"].dropna().tolist()
                # flatten list-of-list if yfinance returns multi-level
                if closes and isinstance(closes[0], (list, tuple)):
                    closes = [c[0] for c in closes]
                result[ticker] = [float(c) for c in closes if c]
            except Exception:
                continue
        return result
    except ImportError:
        return {}


def _calc_return(prices: list[float], entry_idx: int, horizon_bars: int) -> Optional[float]:
    """Return % gain from prices[entry_idx] over the next horizon_bars closes."""
    if entry_idx >= len(prices) - 1:
        return None
    exit_idx = min(entry_idx + horizon_bars, len(prices) - 1)
    entry    = prices[entry_idx]
    if entry <= 0:
        return None
    return (prices[exit_idx] - entry) / entry


# ── Signal replay ─────────────────────────────────────────────────────────────

def replay_signals_from_features(
    feature_rows: list[dict],
    price_history: dict[str, list[float]],
    min_confluence: float = 45.0,
) -> list[dict]:
    """
    Walk through feature rows in time order and compute outcomes.

    Each feature row represents one ticker at one point in time.
    We build a synthetic signal from chg_1d + sent_avg + vwap_dev + rsi_intra
    and measure 7-day return from entry.

    Returns a list of signal outcome records.
    """
    from intelligence.market_router import classify_ticker, MARKET_PROFILES

    outcomes: list[dict] = []

    # Group by (date, ticker)
    rows_by_ts: dict[str, list[dict]] = defaultdict(list)
    for row in feature_rows:
        ts_key = (row.get("ts") or "")[:10]  # YYYY-MM-DD
        rows_by_ts[ts_key].append(row)

    # Build date → price index for quick lookups
    # For each ticker, find its position in the price_history list by date
    # We use a simple approximation: prices[-n] ≈ n trading days ago
    TRADING_DAYS_PER_WEEK = 5

    for date_str in sorted(rows_by_ts.keys()):
        for row in rows_by_ts[date_str]:
            ticker  = row.get("ticker")
            mtype   = row.get("market_type") or classify_ticker(ticker or "")
            prices  = price_history.get(ticker or "", [])
            regime  = row.get("regime") or "unknown"

            if not ticker or len(prices) < 10:
                continue

            # ── Build a synthetic signal score from feature columns ────────
            # Think of this as a replay of what the signal engine would have done
            # given only the feature vector — not a re-run of the full engine.

            score = 0.0
            n_votes = 0

            # Momentum: strong 1d move in direction
            chg = row.get("chg_1d") or 0
            if abs(chg) > 0.5:
                score  += 15.0 * (1 if chg > 0 else -1)
                n_votes += 1

            # Intraday VWAP premium / discount
            vwap_dev = row.get("vwap_dev") or 0
            if abs(vwap_dev) > 0.002:
                score  += 10.0 * (1 if vwap_dev > 0 else -1)
                n_votes += 1

            # RSI condition
            rsi = row.get("rsi_intra")
            if rsi is not None:
                if rsi > 60:
                    score += 8.0; n_votes += 1
                elif rsi < 40:
                    score -= 8.0; n_votes += 1

            # Sentiment
            sent = row.get("sent_avg")
            if sent is not None and abs(sent) > 0.1:
                score  += 12.0 * sent / abs(sent)
                n_votes += 1

            # VIX dampener
            vix = row.get("vix") or 0
            if vix > 30:
                score *= 0.65
            elif vix > 40:
                score *= 0.40

            if n_votes < 2:
                continue  # insufficient signal

            # Map to confluence-like score: scale so ±60 ~ ±60% confluence
            profile     = MARKET_PROFILES.get(mtype, MARKET_PROFILES["equity"])
            min_conf    = profile.get("min_confluence", min_confluence)
            abs_score   = abs(score)
            confluence  = min(99, 50 + abs_score)

            if confluence < min_conf:
                continue

            direction = "long" if score > 0 else "short"

            # ── Measure actual 7-day return ────────────────────────────────
            # Approximate: how many bars ago was this date?
            days_ago = max(1, (datetime.now(timezone.utc) -
                               datetime.fromisoformat(date_str + "T00:00:00+00:00")).days)
            entry_idx = max(0, len(prices) - days_ago - 1)
            ret_7d    = _calc_return(prices, entry_idx, TRADING_DAYS_PER_WEEK)
            ret_1d    = _calc_return(prices, entry_idx, 1)

            hit = None
            if ret_7d is not None:
                hit = (direction == "long" and ret_7d > 0) or \
                      (direction == "short" and ret_7d < 0)

            outcomes.append({
                "ticker":      ticker,
                "market_type": mtype,
                "regime":      regime,
                "date":        date_str,
                "direction":   direction,
                "confluence":  round(confluence, 1),
                "ret_1d":      round(ret_1d, 4) if ret_1d is not None else None,
                "ret_7d":      round(ret_7d, 4) if ret_7d is not None else None,
                "hit":         hit,
                "vix":         row.get("vix"),
                "n_mentions":  row.get("n_mentions", 0),
            })

    return outcomes


# ── Aggregate metrics ─────────────────────────────────────────────────────────

def aggregate_outcomes(outcomes: list[dict]) -> dict:
    """
    Compute hit rates, expectancy, profit factor, and calibration
    broken down by: overall, per-market-type, per-regime, per-direction.
    """
    if not outcomes:
        return {"error": "no outcomes to aggregate"}

    settled = [o for o in outcomes if o.get("ret_7d") is not None]
    if not settled:
        return {"error": "no settled outcomes (data too recent)", "total_signals": len(outcomes)}

    def _stats(records: list[dict]) -> dict:
        n      = len(records)
        wins   = [r for r in records if r.get("hit")]
        losses = [r for r in records if r.get("hit") is False]
        n_hit  = len(wins)

        returns = [r["ret_7d"] for r in records if r.get("ret_7d") is not None]
        avg_ret = sum(returns) / len(returns) if returns else 0

        win_rets  = [r["ret_7d"] for r in wins  if r.get("ret_7d") is not None]
        loss_rets = [r["ret_7d"] for r in losses if r.get("ret_7d") is not None]

        avg_win  = sum(win_rets)  / len(win_rets)  if win_rets  else 0
        avg_loss = sum(loss_rets) / len(loss_rets) if loss_rets else 0

        hit_rate = round(n_hit / n, 3) if n else 0
        expectancy = round(hit_rate * avg_win + (1 - hit_rate) * avg_loss, 4)
        profit_factor = round(
            (sum(w for w in win_rets if w > 0)) /
            max(abs(sum(l for l in loss_rets if l < 0)), 1e-8), 2
        ) if win_rets and loss_rets else None

        return {
            "n":             n,
            "n_hit":         n_hit,
            "hit_rate":      hit_rate,
            "avg_return_7d": round(avg_ret, 4),
            "avg_win":       round(avg_win, 4),
            "avg_loss":      round(avg_loss, 4),
            "expectancy":    expectancy,
            "profit_factor": profit_factor,
        }

    # Overall
    summary = {"overall": _stats(settled), "total_signals": len(outcomes)}

    # Per market type
    by_mtype: dict[str, list] = defaultdict(list)
    for o in settled:
        by_mtype[o.get("market_type", "equity")].append(o)
    summary["by_market_type"] = {k: _stats(v) for k, v in sorted(by_mtype.items())}

    # Per regime
    by_regime: dict[str, list] = defaultdict(list)
    for o in settled:
        by_regime[o.get("regime", "unknown")].append(o)
    summary["by_regime"] = {k: _stats(v) for k, v in sorted(by_regime.items())}

    # Per direction
    by_dir: dict[str, list] = defaultdict(list)
    for o in settled:
        by_dir[o.get("direction", "long")].append(o)
    summary["by_direction"] = {k: _stats(v) for k, v in sorted(by_dir.items())}

    # Calibration: confluence band → hit rate
    bands = {"45-55": [], "55-65": [], "65-75": [], "75+": []}
    for o in settled:
        c = o.get("confluence", 50)
        if c < 55:    bands["45-55"].append(o)
        elif c < 65:  bands["55-65"].append(o)
        elif c < 75:  bands["65-75"].append(o)
        else:         bands["75+"].append(o)
    summary["calibration"] = {
        band: {"n": len(v), "hit_rate": round(sum(1 for o in v if o.get("hit")) / len(v), 3)}
        for band, v in bands.items() if v
    }

    # Top 5 tickers by expectancy
    by_ticker: dict[str, list] = defaultdict(list)
    for o in settled:
        by_ticker[o.get("ticker", "")].append(o)
    ticker_stats = []
    for ticker, records in by_ticker.items():
        s = _stats(records)
        s["ticker"] = ticker
        ticker_stats.append(s)
    ticker_stats.sort(key=lambda x: x["expectancy"], reverse=True)
    summary["top_tickers"] = ticker_stats[:10]

    return summary


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_backtest(
    days:            int   = 14,
    min_confluence:  float = 45.0,
    max_tickers:     int   = 51,
) -> dict:
    """
    Full backtest pipeline:
      1. Load local feature store
      2. Fetch yfinance outcome prices for all tickers seen
      3. Replay signals
      4. Aggregate metrics

    Returns a comprehensive performance report dict.
    """
    from shared.data_lake import load_feature_store

    print(f"[backtester] Loading {days}d feature store…")
    feature_rows = load_feature_store(days=days)
    if not feature_rows:
        return {"error": "No feature data found. Run the pipeline at least once first.",
                "hint": "Features are stored in ~/.intl_snapshots/features_YYYYMMDD.jsonl.gz"}

    tickers = list({r["ticker"] for r in feature_rows if r.get("ticker")})[:max_tickers]
    print(f"[backtester] {len(feature_rows)} feature rows across {len(tickers)} tickers")

    # Fetch price history in a thread (yfinance is sync)
    print(f"[backtester] Fetching price history for {len(tickers)} tickers…")
    price_history = await asyncio.get_event_loop().run_in_executor(
        None, fetch_price_history, tickers, "3mo"
    )
    print(f"[backtester] Price history loaded for {len(price_history)} tickers")

    outcomes = replay_signals_from_features(feature_rows, price_history, min_confluence)
    print(f"[backtester] {len(outcomes)} signals replayed, "
          f"{sum(1 for o in outcomes if o.get('ret_7d') is not None)} settled")

    report = aggregate_outcomes(outcomes)
    report["meta"] = {
        "days":           days,
        "min_confluence": min_confluence,
        "feature_rows":   len(feature_rows),
        "tickers":        len(tickers),
        "price_series":   len(price_history),
        "run_at":         datetime.now(timezone.utc).isoformat(),
    }
    return report
