"""My Plan — the beginner's portfolio cockpit (core-satellite with evidence gates).

Professional wealth management for a first portfolio is boring on purpose:
  1. Emergency buffer before anything else.
  2. CORE (most of the money): index SIP — owns the market's long-term drift,
     immune to signal quality, thrives on bear-market rupees.
  3. SATELLITE (small, capped): system-managed direct equity — UNLOCKED ONLY
     when the paper book proves the full discipline works (win rate, sample
     size, uptime). Until then satellite money parks in a liquid fund and the
     system trades it on paper.

This page turns that into numbers and enforces the gates with live data.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for p in (ROOT, ROOT / "projects" / "daily_digest"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import streamlit as st

st.set_page_config(page_title="My Plan · INTL", page_icon="🌱", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _theme import apply_theme
apply_theme()
from _terminal_chrome import render_chrome
render_chrome("My Plan")


@st.cache_data(ttl=300, show_spinner=False)
def _health():
    from shared.system_health import health_snapshot
    return health_snapshot()


@st.cache_data(ttl=1800, show_spinner=False)
def _india_trend():
    try:
        from shared.india_swing import india_regime
        return india_regime()
    except Exception:
        return {"trend": "?", "label": "—"}


def main():
    st.title("🌱 My Plan")
    st.caption("Core-satellite portfolio plan with live evidence gates — "
               "the system earns real money only after it proves itself on paper.")

    # ── System health strip ───────────────────────────────────────────────────
    h = _health()
    g_color = {"GREEN": "#00d68f", "AMBER": "#ffaa00", "RED": "#ff5773"}[h["grade"]]
    st.markdown(
        f"<div style='background:#131825;border-left:3px solid {g_color};"
        f"border-radius:6px;padding:10px 14px;margin-bottom:14px'>"
        f"<b style='color:{g_color}'>SYSTEM {h['grade']}</b> "
        f"<span style='color:#8b93a7;font-size:12px'>· runs 7d: "
        f"{h['runs_7d'] or 0}/{h['expected_7d']} · last run "
        f"{h['hours_since_run'] if h['hours_since_run'] is not None else '—'}h ago · "
        f"settled outcomes: {h['settled_total'] or 0} · paper: "
        f"{h['paper_open']} open / {h['paper_closed']} closed"
        f"{' · win ' + format(h['paper_win_rate']*100, '.0f') + '%' if h['paper_win_rate'] is not None else ''}"
        f"</span>"
        + "".join(f"<div style='color:#ff8800;font-size:12px;margin-top:4px'>⚠ {i}</div>"
                  for i in h["issues"])
        + "</div>", unsafe_allow_html=True)

    # ── Inputs ────────────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        monthly = st.number_input("Monthly investable (₹)", 1000, 10_000_000,
                                  int(st.session_state.get("plan_monthly", 25_000)),
                                  step=5_000, key="plan_monthly")
    with c2:
        lumpsum = st.number_input("Lump sum available (₹)", 0, 1_000_000_000,
                                  int(st.session_state.get("plan_lump", 0)),
                                  step=25_000, key="plan_lump")
    with c3:
        em_months = st.selectbox("Emergency fund covers",
                                 ["< 3 months", "3–6 months", "6+ months"],
                                 index=1, key="plan_em")
    with c4:
        core_pct = st.slider("Core allocation %", 60, 90, 75, step=5,
                             key="plan_core",
                             help="Index funds. The rest is the satellite the "
                                  "system manages — capped at 40% by design.")

    sat_pct = 100 - core_pct

    # ── Evidence gates (live) ────────────────────────────────────────────────
    gates = [
        ("Uptime ≥ 70% of runs (7d)", (h["runs_7d"] or 0) >= 15,
         f"{h['runs_7d'] or 0}/21 runs"),
        ("≥ 300 settled outcomes", (h["settled_total"] or 0) >= 300,
         f"{h['settled_total'] or 0} settled"),
        ("Paper book ≥ 30 closed trades", h["paper_closed"] >= 30,
         f"{h['paper_closed']} closed"),
        ("Paper win rate ≥ 50%", (h["paper_win_rate"] or 0) >= 0.50,
         f"{(h['paper_win_rate'] or 0)*100:.0f}%" if h["paper_closed"] else "no data"),
        ("Paper avg trade > 0", (h["paper_avg_pnl"] or 0) > 0,
         f"{(h['paper_avg_pnl'] or 0):+.2f}%" if h["paper_closed"] else "no data"),
        ("India calibration ≥ 100 calls", (h["india_predictions"] or 0) >= 100,
         f"{h['india_predictions'] or 0} India calls (7d)"),
    ]
    unlocked = all(ok for _, ok, _ in gates)

    # ── The plan ─────────────────────────────────────────────────────────────
    st.divider()
    colA, colB = st.columns([3, 2])

    with colA:
        st.markdown("#### 📋 Your allocation, this month")
        rows = []
        if em_months == "< 3 months":
            rows.append(("1. Emergency buffer FIRST", monthly,
                         "Liquid fund / sweep FD until 6 months of expenses — "
                         "skip investing this month"))
            core_amt = sat_amt = 0
        else:
            core_amt = int(monthly * core_pct / 100)
            sat_amt = monthly - core_amt
            rows.append((f"2. CORE · {core_pct}% — NIFTY 50 index fund SIP",
                         core_amt,
                         "Direct-growth index fund, auto-debit SIP. Bear/chop "
                         "months buy MORE units — never pause it."))
            if unlocked:
                rows.append((f"3. SATELLITE · {sat_pct}% — system-managed equity",
                             sat_amt,
                             "Deploy via India Invest page sizes (¼-Kelly, "
                             "stops honored). UNLOCKED — gates passed."))
            else:
                rows.append((f"3. SATELLITE · {sat_pct}% — 🔒 parked in liquid fund",
                             sat_amt,
                             "Locked until the paper book proves the discipline "
                             "(gates →). The system trades this on paper meanwhile; "
                             "the cash accumulates and earns ~6-7%."))
        for label, amt, note in rows:
            st.markdown(
                f"<div style='background:#131825;border:1px solid #1f2937;"
                f"border-radius:6px;padding:10px 14px;margin-bottom:6px'>"
                f"<div style='display:flex;justify-content:space-between'>"
                f"<b style='color:#e6e9f0'>{label}</b>"
                f"<b style='color:#00d68f;font-family:IBM Plex Mono,monospace'>"
                f"₹{amt:,.0f}/mo</b></div>"
                f"<div style='color:#8b93a7;font-size:12px;margin-top:3px'>{note}</div>"
                f"</div>", unsafe_allow_html=True)

        if lumpsum > 0:
            reg = _india_trend()
            stage = 6 if reg.get("trend") in ("bear", "chop") else 3
            st.markdown(
                f"<div style='background:#0f1422;border:1px solid #1f2937;"
                f"border-radius:6px;padding:10px 14px;margin-top:4px'>"
                f"<b style='color:#e6e9f0'>Lump sum ₹{lumpsum:,.0f}</b> "
                f"<span style='color:#8b93a7;font-size:12px'>— stage into the "
                f"core over <b>{stage} months</b> (₹{lumpsum/stage:,.0f}/mo STP). "
                f"Regime: {reg.get('label', '—')} — staging beats lump-sum entry "
                f"in {'bear/chop' if stage == 6 else 'trending'} tape.</span></div>",
                unsafe_allow_html=True)

    with colB:
        st.markdown("#### 🔓 Satellite unlock gates (live)")
        for label, ok, val in gates:
            icon, color = ("✅", "#00d68f") if ok else ("⬜", "#8b93a7")
            st.markdown(
                f"<div style='display:flex;gap:8px;padding:5px 0;"
                f"border-bottom:1px solid #1a2034'>"
                f"<span>{icon}</span><span style='color:#c8cce0;font-size:13px;"
                f"flex:1'>{label}</span>"
                f"<span style='color:{color};font-size:12px;font-family:"
                f"IBM Plex Mono,monospace'>{val}</span></div>",
                unsafe_allow_html=True)
        st.markdown(
            f"<div style='margin-top:10px;padding:10px;border-radius:6px;"
            f"background:{'#00d68f18' if unlocked else '#1a2034'};text-align:center'>"
            f"<b style='color:{'#00d68f' if unlocked else '#8b93a7'}'>"
            f"{'🔓 SATELLITE UNLOCKED — real money may follow the system' if unlocked else '🔒 SATELLITE LOCKED — paper-trading until proven'}"
            f"</b></div>", unsafe_allow_html=True)

        st.markdown("#### ☑ This week")
        st.markdown(
            "- Keep the Mac **awake** 06:00–18:00 IST (cron windows)\n"
            "- Glance at **🧪 Paper Trading** — is the book behaving?\n"
            "- **Core SIP on auto-debit** — never time it, never pause it\n"
            "- When static IP arrives → Breeze keys → holdings review\n"
            "- Do **not** add new strategies while the measurement runs")


main()
