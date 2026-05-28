"""
Data Lake v2 — compressed pipeline snapshots + per-ticker feature store.

Two storage layers:
  1. Full snapshots (zlib-compressed JSON):
       Supabase pipeline_snapshots → metadata queryable in SQL
       ~/.intl_snapshots/YYYYMMDD_HHMMSS.json.gz → offline ML training

  2. Per-ticker feature store (append-only JSONL):
       ~/.intl_snapshots/features_YYYYMMDD.jsonl.gz
       One JSON line per ticker per run — directly usable in pandas/sklearn.
       Captures: price, momentum, VWAP, RSI, sentiment, options flow, regime, SRS.
       This file grows daily and is the primary ML training input.

As runs accumulate (weeks → months), the feature store becomes a time-series
dataset of ~51 tickers × 3 daily runs × 30 days = ~4,500 rows/month — enough
to start training simple regime-aware classifiers.
"""
from __future__ import annotations

import base64
import gzip
import json
import math
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


_SNAP_DIR = Path.home() / ".intl_snapshots"

# Normalize indicator aliases → canonical FRED series_id keys
_MACRO_ALIASES: dict[str, str] = {
    "VIX": "VIXCLS", "FFR": "FEDFUNDS", "CPI": "CPIAUCSL",
    "10YR": "DGS10", "10Y2Y": "T10Y2Y", "UNEMP": "UNRATE",
    "SPREAD": "T10Y2Y",
}


def _macro_dict(macro_list: list) -> dict:
    """Build a {series_id: value} dict from a macro list that may use
    either 'series_id' or 'indicator' as the key field."""
    out: dict = {}
    for m in macro_list:
        k = m.get("series_id") or m.get("indicator") or ""
        k = _MACRO_ALIASES.get(k, k)
        if k and m.get("value") is not None:
            out[k] = m["value"]
    return out


def _regime_str(regime_field) -> str:
    """Extract regime string from either a dict {'regime': 'goldilocks', ...}
    or a plain string 'goldilocks'. Returns '' when unknown."""
    if isinstance(regime_field, dict):
        return regime_field.get("regime") or ""
    if isinstance(regime_field, str):
        return regime_field
    return ""


# ── Compression ───────────────────────────────────────────────────────────────

def _compress(obj: dict) -> str:
    raw = json.dumps(obj, default=str).encode("utf-8")
    return base64.b64encode(gzip.compress(raw, compresslevel=6)).decode("ascii")


def _decompress(data: str) -> dict:
    return json.loads(gzip.decompress(base64.b64decode(data.encode("ascii"))).decode("utf-8"))


# ── Snapshot metadata ─────────────────────────────────────────────────────────

def _build_metadata(payload: dict) -> dict:
    regime_raw = payload.get("regime") or {}
    risk     = payload.get("risk")   or {}
    sent     = payload.get("sentiment") or {}
    items    = payload.get("items", [])
    signals  = payload.get("signals", [])
    alerts   = payload.get("alerts", [])
    market   = payload.get("market", [])
    macro    = payload.get("macro", [])

    top_items = [
        {
            "title":     it.get("title", "")[:120],
            "source":    it.get("source"),
            "score":     it.get("terminal_score"),
            "sentiment": it.get("sentiment_label"),
            "entities":  it.get("entities", [])[:5],
        }
        for it in sorted(items, key=lambda x: x.get("terminal_score", 0), reverse=True)[:20]
    ]

    market_summary = {
        m["ticker"]: {"price": m.get("price"), "chg": m.get("change_pct")}
        for m in market if m.get("ticker")
    }

    _srs_from_risk = risk.get("srs") if isinstance(risk, dict) else None
    srs_val        = _srs_from_risk if _srs_from_risk is not None else payload.get("srs")

    return {
        "regime":         _regime_str(regime_raw),
        "srs":            srs_val,
        "sentiment_bull": sent.get("bullish_pct") or sent.get("bull_pct"),
        "sentiment_bear": sent.get("bearish_pct") or sent.get("bear_pct"),
        "item_count":     len(items),
        "signal_count":   len(signals),
        "alert_count":    len(alerts),
        "top_items":      top_items,
        "market_summary": market_summary,
        "macro_snapshot": _macro_dict(macro),
    }


# ── Per-ticker feature extraction ─────────────────────────────────────────────

def _ticker_feature_row(
    ticker:       str,
    market_data:  dict,        # {price, change_pct, type, market_cap, change_7d, volume_usd}
    intraday_data: Optional[dict],  # from sources/intraday.py intraday_data dict
    items:        list[dict],  # all pipeline items (for sentiment)
    signals:      list[dict],  # all pipeline signals (for options flow)
    macro:        dict,        # {series_id: value}
    sentiment:    dict,        # global sentiment summary
    regime:       Optional[str],
    srs:          Optional[float],
    ts:           str,
) -> dict:
    """
    Build a flat feature row for one ticker at one point in time.

    All features are numeric or binary — ready for sklearn/pandas without
    further preprocessing. Missing values are None (caller should impute).
    """
    from intelligence.market_router import classify_ticker
    mtype = classify_ticker(ticker)

    # ── Calendar features (cheap seasonality signals) ─────────────────────────
    dow = hour_utc = None
    try:
        _dt = datetime.fromisoformat(ts)
        dow = _dt.weekday()          # 0=Mon … 6=Sun
        hour_utc = _dt.hour
    except Exception:
        pass

    # ── Price momentum ────────────────────────────────────────────────────────
    price    = market_data.get("price")
    chg_1d   = market_data.get("change_pct")
    chg_7d   = market_data.get("change_7d")

    # ── Intraday features ──────────────────────────────────────────────────────
    vwap_dev = rsi_intra = vol_ratio = None
    if intraday_data:
        lb = intraday_data.get("latest_bar", {})
        vwap_dev  = lb.get("vwap_dev")
        rsi_intra = lb.get("rsi_14")
        vol_ratio = lb.get("vol_ratio")

    # ── Sentiment from news items mentioning this ticker ─────────────────────
    relevant = [
        it for it in items
        if ticker.upper() in " ".join(it.get("entities") or []).upper()
        or ticker.upper() in (it.get("title") or "").upper()
    ]
    n_mentions  = len(relevant)
    sent_scores = [float(it.get("sentiment_score") or 0) for it in relevant]
    sent_avg    = sum(sent_scores) / len(sent_scores) if sent_scores else None
    n_bull_news = sum(1 for it in relevant if it.get("sentiment_label") == "bullish")
    n_bear_news = sum(1 for it in relevant if it.get("sentiment_label") == "bearish")

    # ── Options signals for this ticker ───────────────────────────────────────
    opt_items = [
        s for s in signals
        if s.get("source") == "options"
        and ticker.upper() in (s.get("title") or "").upper()
    ]
    n_calls = sum(1 for s in opt_items if "call" in (s.get("title") or "").lower())
    n_puts  = sum(1 for s in opt_items if "put"  in (s.get("title") or "").lower())
    put_call = round(n_puts / max(n_calls, 1), 3)

    # ── Insider / EDGAR signals ───────────────────────────────────────────────
    insider_items = [
        s for s in signals
        if s.get("source") == "edgar"
        and ticker.upper() in (s.get("title") or "").upper()
    ]
    n_insider_buy  = sum(1 for s in insider_items if s.get("sentiment_label") == "bullish")
    n_insider_sell = sum(1 for s in insider_items if s.get("sentiment_label") == "bearish")

    # ── Regime encoding ───────────────────────────────────────────────────────
    regime_map = {"goldilocks": 0, "reflation": 1, "stagflation": 2, "deflation": 3}
    mtype_map  = {"equity": 0, "crypto": 1, "forex": 2, "commodity": 3, "index": 4, "bond": 5}

    return {
        # Identity
        "ts":           ts,
        "ticker":       ticker,
        "market_type":  mtype,
        # Calendar
        "dow":          dow,
        "hour_utc":     hour_utc,
        # Price
        "price":        price,
        "chg_1d":       chg_1d,
        "chg_7d":       chg_7d,
        # Intraday
        "vwap_dev":     vwap_dev,
        "rsi_intra":    rsi_intra,
        "vol_ratio":    vol_ratio,
        # News sentiment
        "n_mentions":   n_mentions,
        "sent_avg":     round(sent_avg, 4) if sent_avg is not None else None,
        "n_bull_news":  n_bull_news,
        "n_bear_news":  n_bear_news,
        # Options
        "n_calls":      n_calls,
        "n_puts":       n_puts,
        "put_call":     put_call,
        # Insider
        "n_insider_buy":  n_insider_buy,
        "n_insider_sell": n_insider_sell,
        # Macro context
        "vix":          macro.get("VIXCLS"),
        "t10y2y":       macro.get("T10Y2Y"),
        "ffr":          macro.get("FEDFUNDS"),
        "dgs10":        macro.get("DGS10"),
        "unrate":       macro.get("UNRATE"),
        # Global sentiment
        "global_bull_pct": sentiment.get("bullish_pct"),
        "global_bear_pct": sentiment.get("bearish_pct"),
        "global_srs":   srs,
        # Regime (encoded)
        "regime":       regime,
        "regime_idx":   regime_map.get(regime, -1) if regime else -1,
        "mtype_idx":    mtype_map.get(mtype, 0),
    }


# ── Feature store writer ───────────────────────────────────────────────────────

def write_per_ticker_features(
    market_items:   list[dict],
    intraday_items: Optional[list[dict]],
    pipeline_payload: dict,
) -> int:
    """
    Append per-ticker feature rows to today's feature store file.

    Format: ~/.intl_snapshots/features_YYYYMMDD.jsonl.gz
    One JSON line per ticker. Append-mode — safe for multiple daily writes.

    Returns count of tickers written.
    """
    _SNAP_DIR.mkdir(parents=True, exist_ok=True)
    ts       = datetime.now(timezone.utc).isoformat()
    regime   = _regime_str(pipeline_payload.get("regime")) or None
    risk     = pipeline_payload.get("risk") or {}
    srs      = risk.get("srs") if isinstance(risk, dict) else pipeline_payload.get("srs")
    items    = pipeline_payload.get("items", [])
    signals  = pipeline_payload.get("signals", [])
    sent     = pipeline_payload.get("sentiment") or {}
    macro_l  = pipeline_payload.get("macro", [])
    macro    = _macro_dict(macro_l)

    # Build intraday index
    intra_idx: dict[str, dict] = {}
    if intraday_items:
        for it in intraday_items:
            if it.get("intraday_data"):
                intra_idx[it["intraday_data"]["ticker"]] = it["intraday_data"]

    today     = datetime.now().strftime("%Y%m%d")
    feat_path = _SNAP_DIR / f"features_{today}.jsonl.gz"

    rows_written = 0
    try:
        with gzip.open(feat_path, "at", encoding="utf-8") as f:
            for m in market_items:
                ticker = m.get("ticker")
                if not ticker:
                    continue
                row = _ticker_feature_row(
                    ticker       = ticker,
                    market_data  = m,
                    intraday_data= intra_idx.get(ticker),
                    items        = items,
                    signals      = signals,
                    macro        = macro,
                    sentiment    = sent,
                    regime       = regime,
                    srs          = srs,
                    ts           = ts,
                )
                f.write(json.dumps(row, default=str) + "\n")
                rows_written += 1
    except Exception as e:
        print(f"[data_lake] feature store write failed: {e}")

    return rows_written


def load_feature_store(days: int = 30) -> list[dict]:
    """
    Load per-ticker feature rows from the last N days of feature store files.
    Returns list of dicts ready for pandas.DataFrame(rows).
    """
    if not _SNAP_DIR.exists():
        return []
    rows = []
    files = sorted(_SNAP_DIR.glob("features_*.jsonl.gz"), reverse=True)[:days]
    for f in files:
        try:
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
        except Exception:
            continue
    return rows


# ── Rich scan feature store (the model's FULL per-ticker view) ────────────────
# The opportunity scan computes the richest per-ticker view in the system —
# full technicals, 5-factor quant scores, raw fundamentals, the model's own
# calibrated prediction + horizon + avoidance, and the macro/regime context.
# Capturing it (with entry price + timestamp) turns the data lake into a proper
# supervised dataset: features now, forward-return labels joined later.

# Bump when build_scan_feature_row's columns change — stored on every row so a
# future schema change can be filtered/migrated instead of silently breaking ML.
_SCAN_SCHEMA_VERSION = 1


def _num(x):
    """Coerce to float or None — keeps the store clean for pandas/sklearn."""
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def build_scan_feature_row(ticker: str, sector: str | None,
                           price: float, chg_1d: float,
                           ret_3m, ret_6m, ret_12m, rsi_14,
                           sma_20, sma_50, sma_200,
                           realized_vol_annual,
                           advanced: dict, fundamentals: dict,
                           quant: dict, prediction: dict,
                           avoidance: dict,
                           regime, srs, ts: str) -> dict:
    """Flatten the scan's full per-ticker computation into one ML-ready row.

    Every field is numeric, categorical, or null. `ts`+`ticker`+`price` let a
    later job join forward returns as labels (see learning_loop.correlate_outcomes
    for the same date-anchored approach).
    """
    adv  = advanced or {}
    macd = adv.get("macd") or {}
    bb   = adv.get("bbands") or {}
    adx  = adv.get("adx") or {}
    vwap = adv.get("vwap") or {}
    fin  = fundamentals or {}
    fac  = (quant or {}).get("factors") or {}

    def fscore(name):
        return _num((fac.get(name) or {}).get("score"))

    return {
        # ── Schema version (lets the corpus evolve without corrupting training)
        "_v":            _SCAN_SCHEMA_VERSION,
        # ── Identity / context ───────────────────────────────────────────────
        "ts":            ts,
        "ticker":        ticker,
        "sector":        sector or "",
        "regime":        regime,
        "srs":           _num(srs),
        # ── Price / momentum ─────────────────────────────────────────────────
        "price":         _num(price),
        "chg_1d":        _num(chg_1d),
        "ret_3m":        _num(ret_3m),
        "ret_6m":        _num(ret_6m),
        "ret_12m":       _num(ret_12m),
        "rsi_14":        _num(rsi_14),
        "vs_sma_20":     _num((price / sma_20 - 1) * 100) if sma_20 else None,
        "vs_sma_50":     _num((price / sma_50 - 1) * 100) if sma_50 else None,
        "vs_sma_200":    _num((price / sma_200 - 1) * 100) if sma_200 else None,
        "realized_vol":  _num(realized_vol_annual),
        # ── Advanced technicals ──────────────────────────────────────────────
        "macd_cross":    macd.get("cross"),
        "bb_signal":     bb.get("signal"),
        "adx":           _num(adx.get("adx")),
        "adx_dir":       adx.get("direction"),
        "vwap_signal":   vwap.get("signal"),
        # ── Raw fundamentals ─────────────────────────────────────────────────
        "pe":            _num(fin.get("peExclExtraAnnual") or fin.get("peNormalizedAnnual")),
        "pb":            _num(fin.get("pbAnnual")),
        "roe":           _num(fin.get("roeTTM") or fin.get("roeRfy")),
        "rev_growth":    _num(fin.get("revenueGrowthTTMYoy") or fin.get("revenueGrowth5Y")),
        "eps_growth":    _num(fin.get("epsGrowthTTMYoy") or fin.get("epsGrowth5Y")),
        "gross_margin":  _num(fin.get("grossMarginTTM") or fin.get("grossMarginAnnual")),
        "op_margin":     _num(fin.get("operatingMarginTTM") or fin.get("operatingMarginAnnual")),
        # ── 5-factor quant scores ────────────────────────────────────────────
        "quant_score":   _num((quant or {}).get("composite_score")),
        "quant_grade":   (quant or {}).get("composite_grade"),
        "f_value":       fscore("value"),
        "f_growth":      fscore("growth"),
        "f_profit":      fscore("profit"),
        "f_momentum":    fscore("momentum"),
        "f_revisions":   fscore("revisions"),
        # ── Model's own calibrated view (meta-features) ──────────────────────
        "pred_direction":      (prediction or {}).get("direction"),
        "pred_confidence":     _num((prediction or {}).get("confidence")),
        "pred_raw_confidence": _num((prediction or {}).get("raw_confidence")),
        "pred_agreement":      _num((prediction or {}).get("agreement")),
        "pred_horizon":        (prediction or {}).get("horizon"),
        "pred_vol_regime":     (prediction or {}).get("vol_regime"),
        "pred_srs_mult":       _num((prediction or {}).get("srs_mult")),
        "pred_vol_mult":       _num((prediction or {}).get("vol_mult")),
        # ── Avoidance (don't-invest screen) ──────────────────────────────────
        "avoid_level":    (avoidance or {}).get("level"),
        "avoid_severity": _num((avoidance or {}).get("severity")),
    }


def write_scan_features(rows: list[dict]) -> int:
    """Append rich scan feature rows to today's scan feature store.

    Format: ~/.intl_snapshots/scan_features_YYYYMMDD.jsonl.gz (append-only).
    Grows ~99 tickers × 3 runs/day into a labeled-able ML training corpus.
    """
    if not rows:
        return 0
    _SNAP_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    path = _SNAP_DIR / f"scan_features_{today}.jsonl.gz"
    n = 0
    try:
        with gzip.open(path, "at", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, default=str) + "\n")
                n += 1
    except Exception as e:
        print(f"[data_lake] scan feature write failed: {e}")
    return n


def load_scan_features(days: int = 60) -> list[dict]:
    """Load rich scan feature rows from the last N daily files (pandas-ready)."""
    if not _SNAP_DIR.exists():
        return []
    rows = []
    for f in sorted(_SNAP_DIR.glob("scan_features_*.jsonl.gz"), reverse=True)[:days]:
        try:
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
        except Exception:
            continue
    return rows


# ── Offline labeling job — turn features into trainable (X, y) ────────────────
# Joins strictly-FUTURE forward returns onto each point-in-time feature row, so
# there is no look-ahead: features were frozen at row['ts']; labels come only
# from closes after that date. Rebuilds the labeled file from scratch each run
# (idempotent; 30d labels fill in as rows age). This is what converts the
# growing feature corpus into a supervised dataset for predictive models.

_LABELED_PATH = _SNAP_DIR / "labeled_features.jsonl.gz"


def build_labeled_dataset(horizons: tuple = (1, 3, 7, 30),
                          benchmark: str = "SPY",
                          lookback_days: int = 180,
                          min_age_days: int = 1) -> dict:
    """Build/refresh the labeled training dataset from the scan feature store.

    For each feature row, computes calendar-anchored forward returns at each
    horizon, the excess return vs `benchmark` (alpha — top players label vs a
    benchmark so the model learns edge, not just market beta), MFE/MAE over 30d
    (enables triple-barrier-style labels), and binary up/down labels.

    Returns {feature_rows, labeled, tickers, errors, out_path}.
    """
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        return {"error": "yfinance + pandas required"}

    feats = load_scan_features(days=lookback_days)
    if not feats:
        return {"feature_rows": 0, "labeled": 0, "msg": "no feature rows yet"}

    now = datetime.now(timezone.utc)

    # Keep rows old enough that at least the shortest horizon has elapsed
    pending = []
    for r in feats:
        try:
            ts = datetime.fromisoformat(r["ts"])
        except Exception:
            continue
        if (now - ts).days >= min_age_days and r.get("price"):
            pending.append((r, ts))
    if not pending:
        return {"feature_rows": len(feats), "labeled": 0,
                "msg": "no rows old enough to label yet"}

    # Batch-fetch price history per unique ticker (+ benchmark) once
    tickers = sorted({r["ticker"] for r, _ in pending} | {benchmark})
    earliest = min(ts for _, ts in pending)
    start = (earliest - timedelta(days=3)).strftime("%Y-%m-%d")

    def _series(tk):
        try:
            h = yf.Ticker(tk).history(start=start, auto_adjust=True)
            if h.empty:
                return None
            idx = h.index
            if getattr(idx, "tz", None) is not None:
                idx = idx.tz_convert("UTC").tz_localize(None)
            return pd.Series(h["Close"].values,
                             index=pd.DatetimeIndex(idx).normalize()).sort_index()
        except Exception:
            return None

    hist = {tk: _series(tk) for tk in tickers}
    bench = hist.get(benchmark)

    def _fwd(series, base, pred_date, days):
        sub = series[series.index >= pred_date + pd.Timedelta(days=days)]
        return (float(sub.iloc[0]) / base - 1) * 100 if len(sub) else None

    labeled, errors = [], 0
    for r, ts in pending:
        try:
            s = hist.get(r["ticker"])
            base = float(r["price"])
            if s is None or base <= 0:
                continue
            pred_date = pd.Timestamp(ts.date())
            row = dict(r)
            for h in horizons:
                v = _fwd(s, base, pred_date, h)
                row[f"fwd_ret_{h}d"] = round(v, 4) if v is not None else None

            # Excess vs benchmark at 7d (alpha label)
            row["fwd_ret_7d_excess"] = None
            if bench is not None and row.get("fwd_ret_7d") is not None:
                bret = _fwd(bench, float(bench[bench.index <= pred_date].iloc[-1])
                            if len(bench[bench.index <= pred_date]) else base,
                            pred_date, 7)
                if bret is not None:
                    row["fwd_ret_7d_excess"] = round(row["fwd_ret_7d"] - bret, 4)

            # MFE / MAE over the first 30 calendar days (triple-barrier inputs)
            window = s[(s.index >= pred_date) &
                       (s.index <= pred_date + pd.Timedelta(days=30))].values
            row["mfe_30d"] = round((float(window.max()) / base - 1) * 100, 4) if len(window) else None
            row["mae_30d"] = round((float(window.min()) / base - 1) * 100, 4) if len(window) else None

            # Binary direction labels (the simplest y to start with)
            row["label_up_7d"]  = (int(row["fwd_ret_7d"]  > 0) if row.get("fwd_ret_7d")  is not None else None)
            row["label_up_30d"] = (int(row["fwd_ret_30d"] > 0) if row.get("fwd_ret_30d") is not None else None)
            row["labeled_at"] = now.isoformat()
            labeled.append(row)
        except Exception:
            errors += 1
            continue

    # Rebuild the labeled file fresh (idempotent)
    _SNAP_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with gzip.open(_LABELED_PATH, "wt", encoding="utf-8") as f:
            for row in labeled:
                f.write(json.dumps(row, default=str) + "\n")
    except Exception as e:
        return {"feature_rows": len(feats), "labeled": len(labeled),
                "error": f"write failed: {e}"}

    return {
        "feature_rows": len(feats),
        "labeled":      len(labeled),
        "tickers":      len([t for t in tickers if hist.get(t) is not None]),
        "errors":       errors,
        "out_path":     str(_LABELED_PATH),
    }


def load_labeled_dataset() -> list[dict]:
    """Load the labeled training dataset (features + forward-return labels)."""
    if not _LABELED_PATH.exists():
        return []
    rows = []
    try:
        with gzip.open(_LABELED_PATH, "rt", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except Exception:
        pass
    return rows


def feature_store_stats() -> dict:
    """At-a-glance corpus health: row counts, date span, ticker + label coverage."""
    feats = load_scan_features(days=365)
    labeled = load_labeled_dataset()
    ts_vals = sorted(r.get("ts") for r in feats if r.get("ts"))
    n_settled_7d = sum(1 for r in labeled if r.get("fwd_ret_7d") is not None)
    return {
        "feature_rows":   len(feats),
        "labeled_rows":   len(labeled),
        "settled_7d":     n_settled_7d,
        "unique_tickers": len({r.get("ticker") for r in feats}),
        "first_ts":       ts_vals[0] if ts_vals else None,
        "last_ts":        ts_vals[-1] if ts_vals else None,
    }


# ── Full snapshot write ────────────────────────────────────────────────────────

def write_snapshot(
    payload:        dict,
    intraday_items: Optional[list[dict]] = None,
) -> dict:
    """
    Compress and persist a full pipeline payload.

    Also writes per-ticker feature rows to the feature store.
    Returns {"local": path|None, "supabase": bool, "size_kb": float,
             "features_written": int}.
    """
    ts     = datetime.now(timezone.utc)
    ts_str = ts.strftime("%Y%m%d_%H%M%S")
    meta   = _build_metadata(payload)
    compressed = _compress(payload)
    size_kb    = round(len(compressed) * 0.75 / 1024, 1)

    # ── Per-ticker feature store ──────────────────────────────────────────────
    market_flat = payload.get("market", [])
    n_features  = write_per_ticker_features(market_flat, intraday_items, payload)

    # ── Local full snapshot ───────────────────────────────────────────────────
    local_path = None
    try:
        _SNAP_DIR.mkdir(parents=True, exist_ok=True)
        local_path = str(_SNAP_DIR / f"{ts_str}.json.gz")
        raw = json.dumps(payload, default=str).encode("utf-8")
        with gzip.open(local_path, "wb", compresslevel=6) as fh:
            fh.write(raw)
    except Exception as e:
        print(f"[data_lake] local write failed: {e}")
        local_path = None

    # ── Supabase ──────────────────────────────────────────────────────────────
    sb_ok = False
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    if url and key:
        try:
            from supabase import create_client
            client = create_client(url, key)
            client.table("pipeline_snapshots").insert({
                "snapshot_at":     ts.isoformat(),
                "regime":          meta["regime"],
                "srs":             meta["srs"],
                "sentiment_bull":  meta["sentiment_bull"],
                "sentiment_bear":  meta["sentiment_bear"],
                "item_count":      meta["item_count"],
                "signal_count":    meta["signal_count"],
                "alert_count":     meta["alert_count"],
                "top_items":       meta["top_items"],
                "market_summary":  meta["market_summary"],
                "macro_snapshot":  meta["macro_snapshot"],
                "compressed_data": compressed,
            }).execute()
            sb_ok = True
        except Exception as e:
            print(f"[data_lake] supabase write failed: {e}")

    print(f"  [data_lake] {size_kb}KB snap | {n_features} ticker features | "
          f"local={'Y' if local_path else 'N'} sb={'Y' if sb_ok else 'N'}")
    return {
        "local":            local_path,
        "supabase":         sb_ok,
        "size_kb":          size_kb,
        "features_written": n_features,
    }


# ── Read (metadata index) ─────────────────────────────────────────────────────

def read_snapshot_index(limit: int = 100, regime: Optional[str] = None) -> list[dict]:
    """Snapshot metadata rows from Supabase — no decompression needed."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        return []
    try:
        from supabase import create_client
        client = create_client(url, key)
        q = (client.table("pipeline_snapshots")
             .select("id,snapshot_at,regime,srs,sentiment_bull,sentiment_bear,"
                     "item_count,signal_count,alert_count,market_summary,macro_snapshot")
             .order("snapshot_at", desc=True)
             .limit(limit))
        if regime:
            q = q.eq("regime", regime)
        return q.execute().data or []
    except Exception as e:
        print(f"[data_lake] read index failed: {e}")
        return []


def load_snapshot(snapshot_id: str) -> Optional[dict]:
    """Load and decompress a single snapshot from Supabase by ID."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        client = create_client(url, key)
        rows = (client.table("pipeline_snapshots")
                .select("compressed_data,snapshot_at")
                .eq("id", snapshot_id)
                .limit(1)
                .execute()).data or []
        if not rows or not rows[0].get("compressed_data"):
            return None
        payload = _decompress(rows[0]["compressed_data"])
        payload["_snapshot_at"] = rows[0]["snapshot_at"]
        return payload
    except Exception as e:
        print(f"[data_lake] load snapshot failed: {e}")
        return None


def load_local_snapshots(n: int = 30) -> list[dict]:
    """Load last N local .json.gz snapshots, newest first."""
    if not _SNAP_DIR.exists():
        return []
    files = sorted(_SNAP_DIR.glob("*.json.gz"), reverse=True)[:n]
    out = []
    for f in files:
        try:
            with gzip.open(f, "rb") as fh:
                out.append(json.loads(fh.read().decode("utf-8")))
        except Exception:
            continue
    return out


# ── ML feature extraction (global, for snapshot-level models) ─────────────────

def extract_feature_vector(snapshot: dict) -> dict:
    """
    Global (market-wide) feature vector from one pipeline snapshot.
    For ticker-level ML, use load_feature_store() instead.
    """
    regime_map = {"goldilocks": 0, "reflation": 1, "stagflation": 2, "deflation": 3}
    raw_regime = snapshot.get("regime")
    r          = raw_regime if isinstance(raw_regime, dict) else {}
    regime_s   = _regime_str(raw_regime)
    macro      = _macro_dict(snapshot.get("macro", []))
    fg         = next((f.get("value") for f in snapshot.get("fear_greed", [])
                       if f.get("source") == "stocks"), None)
    items   = snapshot.get("items", [])
    signals = snapshot.get("signals", [])
    sent    = snapshot.get("sentiment") or {}
    risk    = snapshot.get("risk") or {}

    s_labels = [it.get("sentiment_label") for it in items[:50]]
    n_bull   = sum(1 for s in s_labels if s == "bullish")
    n_bear   = sum(1 for s in s_labels if s == "bearish")
    n_call   = sum(1 for s in signals if "call" in (s.get("title") or "").lower())
    n_put    = sum(1 for s in signals if "put"  in (s.get("title") or "").lower())
    avg_sc   = sum(it.get("terminal_score", 0) for it in items[:20]) / 20 if items else 0

    return {k: v for k, v in {
        "regime":            regime_s,
        "regime_idx":        regime_map.get(regime_s, -1),
        "regime_goldilocks": int(regime_s == "goldilocks"),
        "regime_reflation":  int(regime_s == "reflation"),
        "regime_stagflation":int(regime_s == "stagflation"),
        "regime_deflation":  int(regime_s == "deflation"),
        "regime_confidence": r.get("confidence_pct", 0) if r else 0,
        "growth_score":      r.get("growth_score", 0) if r else 0,
        "inflation_score":   r.get("inflation_score", 0) if r else 0,
        "srs":               risk.get("srs", 0) if isinstance(risk, dict) else snapshot.get("srs", 0),
        "bull_pct":          sent.get("bullish_pct") or sent.get("bull_pct", 0),
        "bear_pct":          sent.get("bearish_pct") or sent.get("bear_pct", 0),
        "n_bull_items":      n_bull,
        "n_bear_items":      n_bear,
        "vix":               macro.get("VIXCLS"),
        "ffr":               macro.get("FEDFUNDS"),
        "t10y2y":            macro.get("T10Y2Y"),
        "cpi":               macro.get("CPIAUCSL"),
        "unrate":            macro.get("UNRATE"),
        "dgs10":             macro.get("DGS10"),
        "fg_stocks":         fg,
        "n_signal_bull":     sum(1 for s in signals if s.get("sentiment_label") == "bullish"),
        "n_signal_bear":     sum(1 for s in signals if s.get("sentiment_label") == "bearish"),
        "put_call_ratio":    round(n_put / max(n_call, 1), 3),
        "avg_terminal_score":round(avg_sc, 2),
        "total_items":       len(items),
        "total_signals":     len(signals),
    }.items() if v is not None}
