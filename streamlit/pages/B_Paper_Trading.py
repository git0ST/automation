"""Paper Trading — the auto-mode virtual book.

The cron opens positions from the system's own predictions, manages stops /
targets / time-stops, de-risks on regime flips and VIX spikes, and adapts its
entry bar to the rolling hit-rate. This page is the read-only window onto
that book: equity, open risk, closed-trade ledger, and the adaptation state.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for p in (ROOT, ROOT / "projects" / "daily_digest"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import streamlit as st

st.set_page_config(page_title="Paper Trading · INTL", page_icon="🧪", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _theme import apply_theme, COLORS
from _data import supabase_client
apply_theme()
from _terminal_chrome import render_chrome
render_chrome("Paper Trading")


@st.cache_data(ttl=120, show_spinner=False)
def _load_trades() -> list[dict]:
    client = supabase_client()
    if client:
        try:
            return (client.table("paper_trades").select("*")
                    .order("entry_at", desc=True).limit(500).execute()).data or []
        except Exception:
            pass
    # Local fallback (when running on the cron machine pre-migration)
    try:
        import json
        return json.loads((Path.home() / ".intl_snapshots" /
                           "paper_trades.json").read_text())
    except Exception:
        return []


def main():
    col_t, col_r = st.columns([6, 1])
    with col_t:
        st.title("🧪 Paper Trading")
        st.caption("Auto-mode virtual book — entries from the system's own "
                   "calls · stops/targets managed by the cron · regime-adaptive")
    with col_r:
        st.write("")
        if st.button("🔄 Refresh", use_container_width=True):
            _load_trades.clear()
            st.rerun()

    trades = _load_trades()
    if not trades:
        st.info("No paper trades yet. The book opens positions on each pipeline "
                "run (cron 3×/day) from predictions clearing the adaptive bar. "
                "Run **migration 015** in Supabase so the cloud app can see the "
                "book the cron writes.")
        return

    open_t = [t for t in trades if t.get("status") == "open"]
    closed = sorted([t for t in trades if t.get("status") == "closed"],
                    key=lambda t: str(t.get("exit_at")))
    wins = [t for t in closed if (t.get("pnl_pct") or 0) > 0]
    realized = sum((t.get("pnl_pct") or 0) / 100 * (t.get("notional") or 0)
                   for t in closed)
    gross = sum(t.get("notional") or 0 for t in open_t)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Realized P&L", f"{realized:+,.0f}",
              delta=f"{len(closed)} closed")
    c2.metric("Win rate", f"{len(wins)/len(closed)*100:.0f}%" if closed else "—",
              delta=f"{len(wins)}W / {len(closed)-len(wins)}L" if closed else None,
              delta_color="off")
    c3.metric("Open positions", len(open_t))
    c4.metric("Open exposure", f"{gross:,.0f}")
    avg_r = (sum(t.get("pnl_pct") or 0 for t in closed) / len(closed)) if closed else 0
    c5.metric("Avg trade", f"{avg_r:+.2f}%")

    # Equity curve from closed trades
    if len(closed) >= 2:
        try:
            import plotly.graph_objects as go
            cum, eq = 0.0, []
            for t in closed:
                cum += (t.get("pnl_pct") or 0) / 100 * (t.get("notional") or 0)
                eq.append(cum)
            fig = go.Figure(go.Scatter(y=eq, mode="lines",
                                       line=dict(color="#00d68f", width=2)))
            fig.update_layout(height=220, margin=dict(l=8, r=12, t=10, b=8),
                              paper_bgcolor=COLORS["bg"], plot_bgcolor=COLORS["bg"],
                              font=dict(color=COLORS["text"]),
                              xaxis=dict(title="closed trade #", automargin=True,
                                         gridcolor=COLORS["border"]),
                              yaxis=dict(title="cum P&L", automargin=True,
                                         gridcolor=COLORS["border"]))
            st.plotly_chart(fig, use_container_width=True, theme=None)
        except Exception:
            pass

    tab_open, tab_closed = st.tabs([f"📂 Open ({len(open_t)})",
                                    f"✅ Closed ({len(closed)})"])
    import pandas as pd
    with tab_open:
        if open_t:
            df = pd.DataFrame([{
                "Ticker": t["ticker"].replace(".NS", ""),
                "Dir": t["direction"], "Mkt": t.get("market"),
                "Entry": t.get("entry_price"), "Stop": t.get("stop_price"),
                "Target": t.get("target_price"),
                "Notional": t.get("notional"), "Conf": t.get("confidence"),
                "Horizon": t.get("horizon"),
                "Since": str(t.get("entry_at"))[:10],
            } for t in open_t])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.caption("No open positions.")
    with tab_closed:
        if closed:
            df = pd.DataFrame([{
                "Ticker": t["ticker"].replace(".NS", ""),
                "Dir": t["direction"],
                "Entry": t.get("entry_price"), "Exit": t.get("exit_price"),
                "P&L %": t.get("pnl_pct"), "Reason": t.get("exit_reason"),
                "Closed": str(t.get("exit_at"))[:10],
                "Source": t.get("source"),
            } for t in reversed(closed)])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.caption("No closed trades yet — stops/targets need time to resolve.")

    # Adaptation state (only present on the cron machine)
    try:
        import json
        s = json.loads((Path.home() / ".intl_snapshots" /
                        "paper_state.json").read_text())
        st.caption(f"⚙ Adaptation: entry bar **{s.get('conf_threshold', 55):.0f}%** · "
                   f"regime **{s.get('regime', '—')}** · "
                   f"{'🔻 DE-RISK active' if s.get('derisk_until') else 'normal risk'} · "
                   f"rolling hits {sum(s.get('recent_closed', []))}/"
                   f"{len(s.get('recent_closed', []))}")
    except Exception:
        pass


main()
