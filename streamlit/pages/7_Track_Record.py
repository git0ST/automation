"""Track Record — backtest of our predictions.

Shows hit rate, average forward returns, calibration chart — so the user
knows whether to trust the system's confidence.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for p in (ROOT, ROOT / "projects" / "daily_digest"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import streamlit as st

st.set_page_config(page_title="Track Record · INTL", page_icon="📈", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _theme import apply_theme, COLORS, status_pill
apply_theme()


@st.cache_data(ttl=300, show_spinner=False)
def fetch_track(days: int):
    from shared.prediction_tracker import fetch_track_record, fetch_stats
    return fetch_track_record(days=days), fetch_stats()


def main():
    col_t, col_r = st.columns([6, 1])
    with col_t:
        st.title("📈 Prediction Track Record")
        st.caption("Honest backtest of every prediction this system has made. "
                   "Helps you calibrate trust in the confidence scores.")
    with col_r:
        st.write("")
        if st.button("🔄 Refresh", use_container_width=True):
            fetch_track.clear()
            st.rerun()

    days = st.slider("Lookback window (days)", 7, 365, 90, step=7,
                     help="How far back to evaluate. Min 7d for outcomes to settle.")
    predictions, stats = fetch_track(days)

    if not predictions:
        st.info(
            "📭 **No predictions logged yet.**\n\n"
            "The track record starts populating once you run the **🎯 Opportunity Scanner** "
            "or view a stock on **🔍 Stock Detail**. Outcomes (forward returns) are filled "
            "after 1 day, 3 days, 7 days, and 30 days.\n\n"
            "Once you have ≥10 predictions with completed outcomes, this page shows hit rate "
            "by confidence band — so you'll know whether 80%-confidence calls actually beat "
            "60%-confidence calls."
        )
        st.divider()
        st.markdown("##### Run migration 009 if you haven't:")
        st.link_button(
            "Open Supabase SQL editor",
            "https://supabase.com/dashboard/project/jptwbvigtgiffjqnctic/sql/new",
            use_container_width=True,
        )
        st.markdown("Then trigger the **Opportunity Scanner** to start logging predictions.")
        return

    correlated = [p for p in predictions if p.get("return_1d") is not None]

    # ── KPI strip ────────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total predictions", len(predictions),
              help="All predictions logged in the window")
    c2.metric("Outcomes settled", len(correlated),
              delta=f"{len(correlated) / max(len(predictions), 1) * 100:.0f}%",
              delta_color="off",
              help="Predictions with 1+ day of forward return data")
    if correlated:
        avg_1d  = sum(p["return_1d"]  for p in correlated) / len(correlated)
        avg_7d  = sum(p["return_7d"]  or 0 for p in correlated) / max(sum(1 for p in correlated if p["return_7d"] is not None), 1)
        c3.metric("Avg 1d return", f"{avg_1d:+.2f}%",
                  delta_color="normal" if avg_1d >= 0 else "inverse",
                  help="Average return 1 trading day after each prediction")
        c4.metric("Avg 7d return", f"{avg_7d:+.2f}%",
                  delta_color="normal" if avg_7d >= 0 else "inverse",
                  help="Average return 7 trading days after each prediction")

        bull = [p for p in correlated if p["direction"] == "bullish"]
        bull_wins = sum(1 for p in bull if p.get("return_7d") and p["return_7d"] > 0)
        hit_rate = bull_wins / max(len(bull), 1) * 100 if bull else 0
        c5.metric("Bullish hit rate", f"{hit_rate:.0f}%",
                  delta=f"{bull_wins}/{len(bull)} calls",
                  delta_color="off",
                  help="% of bullish calls that gained at the 7-day mark")
    else:
        c3.metric("Avg 1d return", "—")
        c4.metric("Avg 7d return", "—")
        c5.metric("Bullish hit rate", "—")

    st.divider()

    # ── Hit rate by confidence band ──────────────────────────────────────────
    st.markdown("#### 🎯 Calibration: do high-confidence calls actually beat low ones?")
    st.caption("If our model is calibrated, average return should grow monotonically "
               "with confidence band.")
    if stats:
        import pandas as pd
        df = pd.DataFrame(stats)
        st.dataframe(df, use_container_width=True,
                     column_config={
                         "n_predictions":  st.column_config.NumberColumn("Predictions"),
                         "avg_return_1d":  st.column_config.NumberColumn("Avg 1d %", format="%+.2f%%"),
                         "avg_return_7d":  st.column_config.NumberColumn("Avg 7d %", format="%+.2f%%"),
                         "avg_return_30d": st.column_config.NumberColumn("Avg 30d %", format="%+.2f%%"),
                         "hit_rate_7d":    st.column_config.NumberColumn("7d hit rate",
                                                                          format="%.2f"),
                     })
    else:
        st.caption("Statistics view not populated yet — needs ≥1 prediction with settled outcome.")

    st.divider()

    # ── Recent predictions log ───────────────────────────────────────────────
    st.markdown("#### 🕒 Recent predictions")
    st.caption("Latest predictions with their outcomes. Pending = forward return not yet computed.")

    import pandas as pd
    rows = []
    for p in predictions[:50]:
        ret_1d = p.get("return_1d")
        ret_7d = p.get("return_7d")
        # Outcome correctness
        if ret_7d is not None:
            won = ((p["direction"] == "bullish" and ret_7d > 0) or
                   (p["direction"] == "bearish" and ret_7d < 0))
            outcome = "✓ Win" if won else "✗ Loss"
        else:
            outcome = "⏳ Pending"
        rows.append({
            "Ticker":     p["ticker"],
            "Direction":  p["direction"].upper(),
            "Confidence": p["confidence_pct"],
            "Price@Pred": p.get("price_at_pred"),
            "1d %":       ret_1d,
            "7d %":       ret_7d,
            "30d %":      p.get("return_30d"),
            "Outcome":    outcome,
            "Made":       p["predicted_at"][:16].replace("T", " "),
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True,
                 column_config={
                     "Confidence": st.column_config.ProgressColumn(format="%.0f%%",
                                                                    min_value=0, max_value=100),
                     "Price@Pred": st.column_config.NumberColumn(format="$%.2f"),
                     "1d %":       st.column_config.NumberColumn(format="%+.2f%%"),
                     "7d %":       st.column_config.NumberColumn(format="%+.2f%%"),
                     "30d %":      st.column_config.NumberColumn(format="%+.2f%%"),
                 },
                 height=400)

    st.caption(
        "**How outcomes are computed**: Each prediction's `price_at_pred` is stored at "
        "the moment it's made. The daily correlation job pulls forward yfinance "
        "closes at +1d, +3d, +7d, +30d and computes the % move. A bullish call counts as "
        "a Win if the 7d return is positive."
    )


main()
