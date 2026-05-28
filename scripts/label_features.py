#!/usr/bin/env python3
"""Offline labeling job — turn the scan feature corpus into trainable (X, y).

Run this WEEKLY (after the pipeline cron has accumulated feature rows). It joins
strictly-future forward returns onto each point-in-time feature row and writes a
labeled dataset ready for sklearn/pandas.

    python scripts/label_features.py
    python scripts/label_features.py --min-age 7      # only fully-settled-ish rows
    python scripts/label_features.py --benchmark QQQ

No look-ahead by construction: features were frozen when the scan ran; labels
come only from closes AFTER that date. Safe to run as often as you like — it
rebuilds the labeled file each time, so 30-day labels fill in as rows age.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Best-effort .env load so SUPABASE_* etc. are present if anything needs them
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Label the scan feature corpus for ML.")
    ap.add_argument("--min-age", type=int, default=1,
                    help="Only label rows at least this many days old (default 1).")
    ap.add_argument("--benchmark", default="SPY",
                    help="Benchmark ticker for the excess-return (alpha) label.")
    ap.add_argument("--lookback", type=int, default=180,
                    help="How many days of feature files to load (default 180).")
    args = ap.parse_args()

    from shared.data_lake import build_labeled_dataset, feature_store_stats

    print("── INTL feature labeling ─────────────────────────────────────────")
    before = feature_store_stats()
    print(f"Corpus: {before['feature_rows']} feature rows · "
          f"{before['unique_tickers']} tickers · "
          f"{before['first_ts']} → {before['last_ts']}")

    if before["feature_rows"] == 0:
        print("\nNo feature rows yet. Let the pipeline cron run for a few days "
              "(each run captures ~99 ticker rows), then re-run this.")
        return 0

    res = build_labeled_dataset(benchmark=args.benchmark,
                                lookback_days=args.lookback,
                                min_age_days=args.min_age)
    if res.get("error"):
        print(f"\n❌ {res['error']}")
        return 1

    after = feature_store_stats()
    print(f"\n✅ Labeled {res.get('labeled', 0)} rows "
          f"({res.get('tickers', 0)} tickers, {res.get('errors', 0)} errors)")
    print(f"   7-day outcomes settled: {after['settled_7d']}")
    print(f"   Output: {res.get('out_path')}")
    print("\nTrain with:  from shared.data_lake import load_labeled_dataset")
    print("             import pandas as pd; df = pd.DataFrame(load_labeled_dataset())")
    print("             # features = numeric cols; y = df['label_up_7d'] (or fwd_ret_7d)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
