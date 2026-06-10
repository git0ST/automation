#!/usr/bin/env python3
"""Train the first supervised model on the system's own labeled outcomes.

    python scripts/train_model.py            # train + evaluate + save

Method (deliberately conservative):
  * Data: the labeled scan-feature corpus (44 features/row, settled 7d labels).
  * Split: STRICTLY time-ordered — train on the earliest ~75% of timestamps,
    test on the latest ~25%. No shuffling, no look-ahead.
  * Model: HistGradientBoostingClassifier (handles missing values natively —
    fundamentals are sparse pre-Finnhub; no extra dependencies).
  * Metrics that matter for trading: AUC, accuracy vs base rate, and
    precision@top-decile (of the model's most-confident longs, how many rose).

Artifacts → ~/.intl_snapshots/models/ (model .pkl + metrics .json).

GATE: the model is NOT wired into the live engine until the corpus spans
≥ 30 distinct trading days — a model trained on a few days memorizes that
week's tape. This script is meant to be re-run weekly as data accumulates.
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NUMERIC = [
    "chg_1d", "ret_3m", "ret_6m", "ret_12m", "rsi_14",
    "vs_sma_20", "vs_sma_50", "vs_sma_200", "realized_vol", "adx",
    "pe", "pb", "roe", "rev_growth", "eps_growth", "gross_margin", "op_margin",
    "quant_score", "f_value", "f_growth", "f_profit", "f_momentum", "f_revisions",
    "pred_confidence", "pred_raw_confidence", "pred_agreement",
    "pred_srs_mult", "pred_vol_mult", "srs", "avoid_severity",
]
CATEGORICAL = ["regime", "macd_cross", "bb_signal", "adx_dir", "vwap_signal",
               "pred_direction", "pred_horizon", "pred_vol_regime",
               "avoid_level", "sector"]
MIN_DISTINCT_DAYS = 30   # gate for wiring into the live engine


def main() -> int:
    import pandas as pd
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score, accuracy_score

    from shared.data_lake import load_labeled_dataset

    rows = load_labeled_dataset()
    df = pd.DataFrame(rows)
    df = df[df["label_up_7d"].notna()].copy()
    if len(df) < 200:
        print(f"Only {len(df)} labeled rows — need ≥200. Let the crons run longer.")
        return 0

    df["ts"] = pd.to_datetime(df["ts"], format="ISO8601")
    df = df.sort_values("ts").reset_index(drop=True)
    n_days = df["ts"].dt.date.nunique()

    X_num = df[[c for c in NUMERIC if c in df.columns]].apply(pd.to_numeric, errors="coerce")
    X_cat = pd.get_dummies(df[[c for c in CATEGORICAL if c in df.columns]].astype(str),
                           dummy_na=False)
    X = pd.concat([X_num, X_cat], axis=1)
    y = df["label_up_7d"].astype(int)

    # Time-ordered split with a 7-DAY EMBARGO (= the label horizon) between
    # train and test. Without the embargo, train/test rows of the same ticker
    # share overlapping 7d outcome windows → the model memorizes which names
    # rose that week and scores a fake AUC≈1 (label leakage, López de Prado).
    cut_ts = df["ts"].quantile(0.6)
    embargo = pd.Timedelta(days=7)
    tr, te = df["ts"] <= cut_ts, df["ts"] > cut_ts + embargo
    purged = True
    if te.sum() < 50:
        # Corpus too young for an embargoed test set — fall back to a plain
        # time split but FLAG the eval as leaky/diagnostic-only.
        purged = False
        tr, te = df["ts"] <= cut_ts, df["ts"] > cut_ts

    clf = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.06, max_depth=4,
        min_samples_leaf=25, l2_regularization=1.0, random_state=42)
    clf.fit(X[tr], y[tr])

    proba = clf.predict_proba(X[te])[:, 1]
    auc = roc_auc_score(y[te], proba) if y[te].nunique() > 1 else float("nan")
    acc = accuracy_score(y[te], proba > 0.5)
    base = y[te].mean()

    # Precision @ top decile — the trading metric
    k = max(5, int(len(proba) * 0.10))
    top = np.argsort(proba)[-k:]
    p_at_top = y[te].to_numpy()[top].mean()

    print("── First supervised model — honest evaluation ─────────────────")
    print(f"  rows: {len(df)}  ·  distinct days: {n_days}  ·  features: {X.shape[1]}")
    print(f"  train: {int(tr.sum())} rows (≤ {cut_ts:%m-%d %H:%M})  ·  "
          f"test: {int(te.sum())} rows (after{' +7d embargo' if purged else ''})")
    if not purged:
        print("  ⚠ NON-PURGED eval (corpus < ~3 weeks): overlapping 7d label "
              "windows leak — treat any high AUC below as MEMORIZATION, not skill.")
    print(f"  test base rate (P(up 7d)):   {base*100:5.1f}%")
    print(f"  AUC:                          {auc:.3f}   (0.5 = no skill)")
    print(f"  accuracy @0.5:                {acc*100:5.1f}%")
    print(f"  precision @ top decile:       {p_at_top*100:5.1f}%  "
          f"(edge {(p_at_top-base)*100:+.1f}pp vs base)")

    # Permutation importance (top 10) on the test slice
    try:
        from sklearn.inspection import permutation_importance
        imp = permutation_importance(clf, X[te], y[te], n_repeats=5,
                                     random_state=42, scoring="roc_auc")
        order = np.argsort(imp.importances_mean)[::-1][:10]
        print("  top features (permutation importance on test):")
        for i in order:
            if imp.importances_mean[i] > 0:
                print(f"    {X.columns[i]:24} {imp.importances_mean[i]:+.4f}")
    except Exception as e:
        print(f"  (importance skipped: {e})")

    # Persist artifacts
    out_dir = Path.home() / ".intl_snapshots" / "models"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    import pickle
    with open(out_dir / f"model_7d_{stamp}.pkl", "wb") as f:
        pickle.dump({"model": clf, "columns": list(X.columns)}, f)
    metrics = {"trained_at": datetime.now(timezone.utc).isoformat(),
               "rows": len(df), "distinct_days": n_days, "auc": float(auc),
               "accuracy": float(acc), "base_rate": float(base),
               "precision_top_decile": float(p_at_top),
               "purged_eval": purged,
               "live_eligible": n_days >= MIN_DISTINCT_DAYS and purged}
    (out_dir / f"metrics_{stamp}.json").write_text(json.dumps(metrics, indent=2))
    print(f"\n  saved → {out_dir}/model_7d_{stamp}.pkl + metrics_{stamp}.json")

    if n_days < MIN_DISTINCT_DAYS:
        print(f"\n  ⛔ LIVE-WIRING GATE: corpus spans {n_days} distinct days "
              f"(< {MIN_DISTINCT_DAYS}). A model trained on this can memorize "
              f"one week's tape — keep collecting, re-run weekly.")
    else:
        print(f"\n  ✅ Corpus spans {n_days} days — eligible to wire the model's "
              f"probability in as a sixth signal layer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
