"""Track Record + Model Evolution.

4 tabs:
  - Overall stats: hit rate, avg return, calibration
  - By Strategy: which playbooks actually work
  - By Regime: which playbooks work in which regimes
  - Model Evolution: history of learned weights + activate-new-weights UI
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
def fetch_all():
    from shared.prediction_tracker import fetch_track_record
    from shared.learning_loop      import (strategy_performance, regime_performance,
                                            calibration_table, load_active_weights,
                                            tune_weights)
    return {
        "predictions": fetch_track_record(days=180),
        "by_strategy": strategy_performance(),
        "by_regime":   regime_performance(),
        "calibration": calibration_table(),
        "active_weights": load_active_weights(),
        "recommended":    tune_weights(min_observations=10, lookback_days=180),
    }


def main():
    col_t, col_r = st.columns([6, 1])
    with col_t:
        st.title("📈 Track Record & Model Evolution")
        st.caption("Honest backtest of every prediction · how the system is learning "
                   "from its own outcomes")
    with col_r:
        st.write("")
        if st.button("🔄 Refresh", use_container_width=True):
            fetch_all.clear()
            st.rerun()

    data = fetch_all()
    predictions = data["predictions"]

    if not predictions:
        _render_empty_state()
        return

    correlated = [p for p in predictions if p.get("return_1d") is not None]

    # KPI strip
    _render_kpi_strip(predictions, correlated)

    st.divider()

    tab_overall, tab_strategy, tab_regime, tab_evolution = st.tabs([
        "📊 Overall", "🎲 By Strategy", "🌐 By Regime", "🧠 Model Evolution"
    ])

    with tab_overall:
        _render_overall(predictions, correlated, data["calibration"])
    with tab_strategy:
        _render_by_strategy(data["by_strategy"])
    with tab_regime:
        _render_by_regime(data["by_regime"])
    with tab_evolution:
        _render_evolution(data["active_weights"], data["recommended"], correlated)


# ── Renderers ──────────────────────────────────────────────────────────────

def _render_empty_state():
    st.info(
        "📭 **No predictions logged yet.**\n\n"
        "The track record starts populating after you run **🎯 Opportunity Scanner** "
        "or **🎲 Strategies**. Predictions are logged with full signal breakdown. "
        "Outcomes (forward returns) auto-fill at 1d/3d/7d/30d after each prediction.\n\n"
        "Once you have ≥10 predictions with completed outcomes (typically 1-2 weeks "
        "of usage), this page shows:\n"
        "- Hit rate by direction × confidence band (calibration check)\n"
        "- Per-strategy and per-regime performance\n"
        "- Recommended new weights for the prediction engine\n"
        "- One-click activation of learned weights"
    )
    st.markdown("##### Make sure migrations 009 + 010 are applied:")
    st.link_button(
        "Open Supabase SQL editor",
        "https://supabase.com/dashboard/project/jptwbvigtgiffjqnctic/sql/new",
        use_container_width=True,
    )


def _render_kpi_strip(predictions, correlated):
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total predictions", len(predictions))
    c2.metric("Settled outcomes", len(correlated),
              delta=f"{len(correlated) / max(len(predictions), 1) * 100:.0f}%",
              delta_color="off",
              help="Predictions with ≥1d of forward return data")
    if correlated:
        avg_7d = sum(p.get("return_7d", 0) or 0 for p in correlated) / max(
            sum(1 for p in correlated if p.get("return_7d") is not None), 1)
        bull = [p for p in correlated if p["direction"] == "bullish" and p.get("return_7d") is not None]
        wins = sum(1 for p in bull if p["return_7d"] > 0)
        bull_hit = (wins / len(bull) * 100) if bull else 0
        bear = [p for p in correlated if p["direction"] == "bearish" and p.get("return_7d") is not None]
        bear_wins = sum(1 for p in bear if p["return_7d"] < 0)
        bear_hit = (bear_wins / len(bear) * 100) if bear else 0
        c3.metric("Avg 7d return", f"{avg_7d:+.2f}%",
                  delta_color="normal" if avg_7d >= 0 else "inverse",
                  help="Across all settled predictions")
        c4.metric("Bullish hit rate", f"{bull_hit:.0f}%",
                  delta=f"{wins}/{len(bull)}", delta_color="off",
                  help="% of bullish calls that gained at 7d")
        c5.metric("Bearish hit rate", f"{bear_hit:.0f}%",
                  delta=f"{bear_wins}/{len(bear)}", delta_color="off",
                  help="% of bearish calls that fell at 7d")
    else:
        c3.metric("Avg 7d return", "—")
        c4.metric("Bullish hit rate", "—")
        c5.metric("Bearish hit rate", "—")


def _render_overall(predictions, correlated, calibration):
    st.markdown("#### 🎯 Calibration: do high-confidence calls actually beat low ones?")
    st.caption("If the model is well-calibrated, hit rate grows monotonically with "
               "confidence band. Mis-calibration = the system is over/under-confident.")
    if calibration:
        import pandas as pd
        df = pd.DataFrame(calibration)
        st.dataframe(df, use_container_width=True,
                     column_config={
                         "n":            st.column_config.NumberColumn("Total"),
                         "n_settled":    st.column_config.NumberColumn("Settled"),
                         "avg_return_7d": st.column_config.NumberColumn("Avg 7d %",
                                                                         format="%+.2f"),
                         "hit_rate_7d":  st.column_config.ProgressColumn(
                             "Hit rate 7d", min_value=0, max_value=1, format="%.2f"),
                     })
    else:
        st.caption("Need ≥1 settled prediction for calibration data.")

    st.divider()

    # Recent predictions table
    st.markdown("#### 🕒 Recent predictions")
    import pandas as pd
    rows = []
    for p in predictions[:80]:
        ret_7d = p.get("return_7d")
        if ret_7d is not None:
            won = ((p["direction"] == "bullish" and ret_7d > 0) or
                   (p["direction"] == "bearish" and ret_7d < 0))
            outcome = "✓ Win" if won else "✗ Loss"
        else:
            outcome = "⏳ Pending"
        rows.append({
            "Ticker":      p["ticker"],
            "Strategy":    p.get("strategy_name") or "—",
            "Regime":      p.get("regime_at_pred") or "—",
            "Direction":   p["direction"].upper(),
            "Confidence":  p["confidence_pct"],
            "Price@Pred":  p.get("price_at_pred"),
            "1d %":        p.get("return_1d"),
            "7d %":        ret_7d,
            "Outcome":     outcome,
            "Made":        p["predicted_at"][:16].replace("T", " "),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True,
                 column_config={
                     "Confidence": st.column_config.ProgressColumn(format="%.0f%%",
                                                                     min_value=0, max_value=100),
                     "Price@Pred": st.column_config.NumberColumn(format="$%.2f"),
                     "1d %":       st.column_config.NumberColumn(format="%+.2f%%"),
                     "7d %":       st.column_config.NumberColumn(format="%+.2f%%"),
                 }, height=400)


def _render_by_strategy(by_strategy):
    if not by_strategy:
        st.info("No per-strategy data yet. Run more Opportunity / Strategies scans to "
                "tag predictions with strategy names.")
        return
    st.markdown("#### 🎲 Performance by strategy")
    st.caption("Compare which playbooks actually work. Hit rate ≥55% on ≥10 settled "
               "predictions = strategy has edge.")
    import pandas as pd
    df = pd.DataFrame(by_strategy)
    st.dataframe(df, use_container_width=True,
                 column_config={
                     "n_predictions":  st.column_config.NumberColumn("Total"),
                     "n_settled":      st.column_config.NumberColumn("Settled"),
                     "avg_return_7d":  st.column_config.NumberColumn("Avg 7d %",
                                                                     format="%+.2f"),
                     "avg_return_30d": st.column_config.NumberColumn("Avg 30d %",
                                                                     format="%+.2f"),
                     "avg_mfe":        st.column_config.NumberColumn("Avg MFE",
                                                                     format="%+.2f",
                                                                     help="Max Favorable Excursion — best move in your direction"),
                     "avg_mae":        st.column_config.NumberColumn("Avg MAE",
                                                                     format="%+.2f",
                                                                     help="Max Adverse Excursion — worst move against you"),
                     "hit_rate_7d":    st.column_config.ProgressColumn(
                         "Hit rate", min_value=0, max_value=1, format="%.2f"),
                     "avg_confidence": st.column_config.NumberColumn("Avg conf",
                                                                      format="%.0f%%"),
                 })


def _render_by_regime(by_regime):
    if not by_regime:
        st.info("No per-regime data yet. Need predictions tagged with regime_at_pred.")
        return
    st.markdown("#### 🌐 Performance by regime")
    st.caption("Different strategies work in different regimes. Use this to know when "
               "to trust which signal.")
    import pandas as pd
    df = pd.DataFrame(by_regime)
    st.dataframe(df, use_container_width=True,
                 column_config={
                     "n_predictions": st.column_config.NumberColumn("Total"),
                     "n_settled":     st.column_config.NumberColumn("Settled"),
                     "avg_return_7d": st.column_config.NumberColumn("Avg 7d %",
                                                                     format="%+.2f"),
                     "hit_rate_7d":   st.column_config.ProgressColumn(
                         "Hit rate", min_value=0, max_value=1, format="%.2f"),
                 })


def _render_evolution(active_weights, recommended, correlated):
    st.markdown("#### 🧠 How the system is learning")
    st.caption("As predictions settle, the system can recompute which signal "
               "components actually predict moves and rebalance weights accordingly.")

    # Active weights
    st.markdown("##### Currently active weights")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Technical", f"{(active_weights.get('technical_w') or 0) * 100:.0f}%",
              help="Weight on SMA/RSI/MACD/Bollinger/ADX vote")
    c2.metric("Sentiment", f"{(active_weights.get('sentiment_w') or 0) * 100:.0f}%",
              help="Weight on per-ticker sentiment from articles")
    c3.metric("Analyst", f"{(active_weights.get('analyst_w') or 0) * 100:.0f}%",
              help="Weight on Finnhub analyst recommendations")
    c4.metric("Vol regime", f"{(active_weights.get('vol_w') or 0) * 100:.0f}%",
              help="Vol regime context modifier (GARCH-based)")
    st.caption(f"**Active version:** `{active_weights.get('version', '—')}` · "
               f"`{active_weights.get('notes') or 'baseline'}`")

    st.divider()

    # Recommended weights
    st.markdown("##### 🔬 Recommended new weights (from outcome data)")

    trained_on = recommended.get("trained_on") or 0
    if trained_on < 20:
        st.info(f"Need at least 20 settled predictions to tune weights. "
                f"Currently: **{trained_on}** settled. Run more scans + wait "
                f"for outcomes to fill.")
        return

    rec_t = recommended.get("technical_w") or 0
    rec_s = recommended.get("sentiment_w") or 0
    rec_a = recommended.get("analyst_w") or 0
    rec_v = recommended.get("vol_w") or 0

    cur_t = active_weights.get("technical_w") or 0.35
    cur_s = active_weights.get("sentiment_w") or 0.25
    cur_a = active_weights.get("analyst_w") or 0.25
    cur_v = active_weights.get("vol_w") or 0.15

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Technical", f"{rec_t * 100:.0f}%",
              delta=f"{(rec_t - cur_t) * 100:+.1f}pp",
              delta_color="off")
    c2.metric("Sentiment", f"{rec_s * 100:.0f}%",
              delta=f"{(rec_s - cur_s) * 100:+.1f}pp",
              delta_color="off")
    c3.metric("Analyst", f"{rec_a * 100:.0f}%",
              delta=f"{(rec_a - cur_a) * 100:+.1f}pp",
              delta_color="off")
    c4.metric("Vol regime", f"{rec_v * 100:.0f}%",
              delta=f"{(rec_v - cur_v) * 100:+.1f}pp",
              delta_color="off")

    st.caption(f"**Trained on:** {trained_on} settled predictions · "
               f"Baseline hit rate: **{(recommended.get('hit_rate') or 0) * 100:.0f}%** · "
               f"_{recommended.get('notes', '')}_")

    st.divider()

    # Activation button (manual review required)
    st.markdown("##### Apply learned weights")
    st.caption("Activating sets these weights as the new active version. "
               "Old version is deactivated but kept in history.")
    if st.button("🚀 Activate recommended weights", use_container_width=True,
                  type="primary"):
        try:
            from datetime import datetime, timezone
            from shared.learning_loop import activate_weights
            ok = activate_weights(
                version=f"v1.1-learned-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}",
                tech_w=rec_t, sent_w=rec_s, analyst_w=rec_a, vol_w=rec_v,
                trained_on=trained_on,
                hit_rate=recommended.get("hit_rate"),
                notes=recommended.get("notes", "") + " · manually activated",
            )
            if ok:
                st.success("✓ New weights activated. Next predictions will use them.")
                fetch_all.clear()
                st.rerun()
            else:
                st.error("Activation failed. Check Supabase connection.")
        except Exception as e:
            st.error(f"Error: {e}")


main()
