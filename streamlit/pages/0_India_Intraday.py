"""India Intraday — live NSE setups from professional intraday signals.

Signal stack (what intraday desks actually trade):
  * VWAP position         — institutional intraday anchor
  * Opening-Range Breakout — first-30-min high/low break with volume
  * Relative Volume (RVOL) — participation confirms the move
  * Intraday RSI(14)       — 15-minute momentum
  * Gap behavior           — gap-and-go vs gap-fade
  * Higher-TF alignment    — trade with the daily trend (SMA20 / prev close)

Risk discipline mirrors the rest of the terminal: ATR-scaled stops (R/R 2:1),
quarter-Kelly sizing on conviction, India-VIX conviction haircut, and an
explicit AVOID screen. Calls are logged with horizon='intraday' so the
learning loop scores them like every other prediction.

Data: yfinance NSE 15-minute bars (near-real-time, can lag ~1-2 min). Good for
signal generation and paper trading; broker-API data (Kite/SmartAPI) is the
execution-grade upgrade path.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for p in (ROOT, ROOT / "projects" / "daily_digest"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import streamlit as st

st.set_page_config(page_title="India Intraday · INTL", page_icon="🇮🇳", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _theme import apply_theme
from _strategy_engine import kelly_position_sizing
from shared.india_market import NIFTY50, INDIA_INDICES, nse_session
from shared import breeze_client as bz
apply_theme()
from _terminal_chrome import render_chrome
render_chrome("India Intraday")


# ── Data ──────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=120, show_spinner=False)
def fetch_intraday(tickers: tuple) -> dict:
    """Batched 15m bars (last ~3 sessions) per ticker → dict of DataFrames."""
    import yfinance as yf
    out = {}
    data = yf.download(list(tickers), period="5d", interval="15m",
                       group_by="ticker", threads=True, progress=False,
                       auto_adjust=True)
    for tk in tickers:
        try:
            df = data[tk].dropna(subset=["Close"])
            if len(df) >= 10:
                out[tk] = df
        except Exception:
            continue
    return out


@st.cache_data(ttl=600, show_spinner=False)
def fetch_daily_context(tickers: tuple) -> dict:
    """Daily bars for higher-TF trend + ATR + previous close."""
    import yfinance as yf
    import numpy as np
    out = {}
    data = yf.download(list(tickers), period="3mo", interval="1d",
                       group_by="ticker", threads=True, progress=False,
                       auto_adjust=True)
    for tk in tickers:
        try:
            df = data[tk].dropna(subset=["Close"])
            if len(df) < 15:
                continue
            c, h, l = df["Close"].values, df["High"].values, df["Low"].values
            tr = np.maximum(h[1:] - l[1:],
                            np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
            atr_pct = float(tr[-14:].mean() / c[-1] * 100)
            out[tk] = {
                "prev_close": float(c[-2]) if len(c) >= 2 else float(c[-1]),
                "sma20":      float(c[-20:].mean()) if len(c) >= 20 else None,
                "atr_pct":    atr_pct,
                "avg_vol":    float(df["Volume"].values[-10:].mean()),
            }
        except Exception:
            continue
    return out


@st.cache_data(ttl=120, show_spinner=False)
def fetch_indices() -> dict:
    import yfinance as yf
    out = {}
    for sym, label in INDIA_INDICES.items():
        try:
            h = yf.Ticker(sym).history(period="5d", interval="15m")
            if h.empty:
                continue
            last = float(h["Close"].iloc[-1])
            # previous session close = last bar of the prior date in the index
            dates = h.index.normalize().unique()
            prev = (float(h[h.index.normalize() == dates[-2]]["Close"].iloc[-1])
                    if len(dates) >= 2 else last)
            out[sym] = {"label": label, "last": last,
                        "chg": (last / prev - 1) * 100 if prev else 0.0}
        except Exception:
            continue
    return out


# ── Per-ticker intraday analysis ─────────────────────────────────────────────

def analyze(tk: str, bars, daily: dict, session: dict, vix_chg: float) -> dict | None:
    """Compute the intraday signal stack for one name → setup dict."""
    import numpy as np

    last_day = bars.index[-1].date()
    day = bars[bars.index.date == last_day]
    if len(day) < 2:
        return None

    price   = float(day["Close"].iloc[-1])
    d_open  = float(day["Open"].iloc[0])
    prev_c  = daily.get("prev_close") or d_open
    sma20   = daily.get("sma20")
    atr_pct = daily.get("atr_pct") or 1.5

    # VWAP (today)
    typ = (day["High"] + day["Low"] + day["Close"]) / 3
    vol = day["Volume"].replace(0, np.nan).ffill().fillna(1)
    vwap = float((typ * vol).cumsum().iloc[-1] / vol.cumsum().iloc[-1])
    vwap_dev = (price / vwap - 1) * 100

    # Opening range = first two 15m bars (09:15–09:45)
    orb = day.iloc[:2]
    or_hi, or_lo = float(orb["High"].max()), float(orb["Low"].min())

    # Relative volume: today's cum vol vs prior sessions' same-bar-count average
    n = len(day)
    prior = bars[bars.index.date != last_day]
    prior_days = [g["Volume"].iloc[:n].sum()
                  for _, g in prior.groupby(prior.index.date)]
    rvol = (float(day["Volume"].sum()) / (np.mean(prior_days) + 1e-9)
            if prior_days else 1.0)

    # Intraday RSI(14) on 15m closes across sessions
    closes = bars["Close"].values
    deltas = np.diff(closes[-15:])
    ups = deltas[deltas > 0].sum() if (deltas > 0).any() else 0.0
    downs = -deltas[deltas < 0].sum() if (deltas < 0).any() else 1e-9
    rsi = 100 - 100 / (1 + ups / downs)

    gap = (d_open / prev_c - 1) * 100 if prev_c else 0.0

    # ── Votes (each ±1) — the desk checklist ────────────────────────────────
    votes, why = [], []
    if abs(vwap_dev) > 0.05:
        votes.append(1 if vwap_dev > 0 else -1)
        why.append(f"{'above' if vwap_dev > 0 else 'below'} VWAP {vwap_dev:+.2f}%")
    if price > or_hi and rvol > 1.1:
        votes.append(1);  why.append(f"ORB ↑ (>{or_hi:,.1f}, RVOL {rvol:.1f}×)")
    elif price < or_lo and rvol > 1.1:
        votes.append(-1); why.append(f"ORB ↓ (<{or_lo:,.1f}, RVOL {rvol:.1f}×)")
    if rsi > 60:
        votes.append(1);  why.append(f"RSI {rsi:.0f}")
    elif rsi < 40:
        votes.append(-1); why.append(f"RSI {rsi:.0f}")
    if abs(gap) > 0.3:
        held = price > d_open if gap > 0 else price < d_open
        v = (1 if gap > 0 else -1) * (1 if held else -1)
        votes.append(v)
        why.append(f"gap {gap:+.1f}% {'holding' if held else 'fading'}")
    if sma20:
        votes.append(1 if price > sma20 else -1)
        why.append(f"{'above' if price > sma20 else 'below'} daily SMA20")
    if prev_c:
        votes.append(1 if price > prev_c else -1)

    if not votes:
        return None
    avg = sum(votes) / len(votes)
    direction = "long" if avg > 0.25 else "short" if avg < -0.25 else "neutral"
    strength = abs(avg)

    # Conviction: transparent, capped at 85 until intraday calibration data
    # accumulates (per-horizon calibration is the planned upgrade).
    confidence = 50 + strength * 35
    if vix_chg > 5:                      # vol spiking — trim conviction
        confidence *= 0.88
        why.append(f"⚠ India VIX +{vix_chg:.0f}%")
    confidence = min(85.0, confidence)

    # ── AVOID screen (intraday discipline) ──────────────────────────────────
    avoid = []
    if rvol < 0.5:
        avoid.append(f"dead volume (RVOL {rvol:.1f}×)")
    if abs(gap) > 4:
        avoid.append(f"event-risk gap {gap:+.1f}%")
    if not session["can_enter"] and session["is_open"]:
        avoid.append(session["note"])

    # ── Risk: ATR-scaled intraday stop, R/R 2:1, quarter-Kelly ──────────────
    stop_pct = min(0.02, max(0.004, 0.35 * atr_pct / 100))
    if direction == "long":
        stop, target = price * (1 - stop_pct), price * (1 + 2 * stop_pct)
    else:
        stop, target = price * (1 + stop_pct), price * (1 - 2 * stop_pct)
    kelly = kelly_position_sizing(win_prob=confidence / 100, payoff_ratio=2.0,
                                  stop_pct=stop_pct, kelly_fraction=0.25)

    return {
        "ticker": tk, "name": NIFTY50.get(tk, {}).get("name", tk),
        "sector": NIFTY50.get(tk, {}).get("sector", "—"),
        "price": price, "direction": direction, "confidence": confidence,
        "vwap_dev": vwap_dev, "rvol": rvol, "rsi": rsi, "gap": gap,
        "or_hi": or_hi, "or_lo": or_lo, "stop": stop, "target": target,
        "stop_pct": stop_pct, "kelly_pct": kelly["position_pct"],
        "no_trade": kelly["no_trade"], "why": why, "avoid": avoid,
        "chg_day": (price / prev_c - 1) * 100 if prev_c else 0.0,
    }


# ── UI ────────────────────────────────────────────────────────────────────────

def main():
    session = nse_session()

    col_t, col_s, col_r = st.columns([4, 3, 1])
    with col_t:
        st.title("🇮🇳 India Intraday")
        st.caption("NIFTY 50 live setups · VWAP · opening-range breakout · RVOL · "
                   "ATR stops · ¼-Kelly sizing")
    breeze_live = bz.is_live()
    with col_s:
        phase_color = {"regular": "#00d68f", "opening_range": "#ffaa00",
                       "closing_window": "#ff8800", "pre_open": "#4da6ff",
                       "closed": "#8b93a7"}[session["phase"]]
        src_html = ("<span style='color:#00d68f;font-weight:700'>● LIVE · Breeze</span>"
                    if breeze_live else
                    "<span style='color:#ffaa00'>● DELAYED · Yahoo (~1–2 min)</span>")
        st.markdown(
            f"<div style='margin-top:18px;text-align:right'>"
            f"<span style='color:{phase_color};font-weight:700;font-size:13px'>"
            f"● NSE {session['phase'].replace('_', ' ').upper()}</span> "
            f"<span style='font-size:11px'>{src_html}</span><br>"
            f"<span style='color:#8b93a7;font-size:11px'>"
            f"{session['ist_now'].strftime('%H:%M IST')} · {session['note']}</span></div>",
            unsafe_allow_html=True,
        )
        if bz.is_configured() and not breeze_live:
            st.markdown(
                f"<div style='text-align:right;font-size:10px'>"
                f"<a href='{bz.login_url()}' target='_blank' style='color:#4c8bf5'>"
                f"Get today's Breeze session token ↗</a> → set BREEZE_SESSION_TOKEN, restart</div>",
                unsafe_allow_html=True,
            )
    with col_r:
        st.write("")
        if st.button("🔄", use_container_width=True, help="Refresh (data caches 2 min)"):
            fetch_intraday.clear(); fetch_indices.clear()
            st.rerun()

    # Index strip
    idx = fetch_indices()
    cols = st.columns(max(len(idx), 1))
    vix_chg = 0.0
    for col, (sym, d) in zip(cols, idx.items()):
        col.metric(d["label"], f"{d['last']:,.1f}", delta=f"{d['chg']:+.2f}%")
        if sym == "^INDIAVIX":
            vix_chg = d["chg"]

    st.divider()

    tickers = tuple(NIFTY50.keys())
    with st.spinner(f"Scanning {len(tickers)} NIFTY 50 names (15-min bars)…"):
        bars_map = fetch_intraday(tickers)
        daily_map = fetch_daily_context(tickers)

    setups = []
    for tk, bars in bars_map.items():
        try:
            s = analyze(tk, bars, daily_map.get(tk, {}), session, vix_chg)
            if s:
                setups.append(s)
        except Exception:
            continue

    if not setups:
        st.error("No NSE data returned — Yahoo may be rate-limited. Retry shortly.")
        return

    longs  = sorted([s for s in setups if s["direction"] == "long"  and not s["avoid"]],
                    key=lambda s: -s["confidence"])
    shorts = sorted([s for s in setups if s["direction"] == "short" and not s["avoid"]],
                    key=lambda s: -s["confidence"])
    avoids = [s for s in setups if s["avoid"]]

    # Breeze live-LTP overlay: refresh displayed setups with real-time prices
    # (yfinance bars lag ~1-2 min) and re-derive stop/target from the live LTP.
    if breeze_live:
        for s in (longs + shorts)[:20]:
            q = bz.get_quote(s["ticker"])
            if q and q.get("ltp"):
                s["price"] = q["ltp"]
                sp = s["stop_pct"]
                if s["direction"] == "long":
                    s["stop"], s["target"] = s["price"] * (1 - sp), s["price"] * (1 + 2 * sp)
                else:
                    s["stop"], s["target"] = s["price"] * (1 + sp), s["price"] * (1 - 2 * sp)

    c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 2])
    c1.metric("Scanned", len(setups))
    c2.metric("Long setups", len(longs))
    c3.metric("Short setups", len(shorts))
    c4.metric("Avoid-flagged", len(avoids))
    with c5:
        capital = st.number_input(
            "Intraday capital (₹)", min_value=10_000, max_value=100_000_000,
            value=int(st.session_state.get("india_capital", 200_000)),
            step=25_000, key="india_capital",
            help="Used to size trade tickets (qty = capital × ¼-Kelly ÷ price).",
        )

    # Log directional calls so the learning loop scores them (horizon=intraday)
    logged = 0
    try:
        from shared.prediction_tracker import log_prediction
        for s in (longs + shorts):
            if s["confidence"] >= 60 and not s["no_trade"]:
                if log_prediction(
                    ticker=s["ticker"],
                    direction="bullish" if s["direction"] == "long" else "bearish",
                    confidence_pct=s["confidence"], price=s["price"],
                    source_page="india_intraday", sector=s["sector"],
                    horizon="intraday",
                ):
                    logged += 1
    except Exception:
        pass
    if logged:
        st.caption(f"📝 {logged} intraday calls logged for outcome scoring.")

    tab_long, tab_short, tab_avoid = st.tabs([
        f"🚀 Long ({len(longs)})", f"📉 Short ({len(shorts)})",
        f"🚫 Avoid ({len(avoids)})",
    ])
    with tab_long:
        _render_setups(longs, session, capital, breeze_live)
    with tab_short:
        _render_setups(shorts, session, capital, breeze_live)
    with tab_avoid:
        for s in avoids:
            st.markdown(
                f"<div style='padding:8px 12px;background:#131825;"
                f"border-left:3px solid #ff8800;border-radius:6px;margin-bottom:5px'>"
                f"<b style='color:#e6e9f0'>{s['ticker'].replace('.NS','')}</b> "
                f"<span style='color:#8b93a7;font-size:12px'>{s['name']} — "
                f"{' · '.join(s['avoid'])}</span></div>",
                unsafe_allow_html=True,
            )

    st.divider()
    st.caption(
        "⚠ Data: Yahoo NSE 15-min bars (can lag ~1–2 min) — signal/paper-trade "
        "grade. Execution-grade live data + order routing needs a broker API "
        "(Zerodha Kite Connect / Angel One SmartAPI). Intraday (MIS) trading "
        "carries leverage risk — size with the Kelly column, honor the stops."
    )


def _render_setups(items: list[dict], session: dict, capital: float,
                   breeze_live: bool):
    if not items:
        st.info("No setups in this direction right now.")
        return
    for s in items:
        dir_color = "#00d68f" if s["direction"] == "long" else "#ff5773"
        sym = s["ticker"].replace(".NS", "")
        with st.expander(
            f"**{sym}** · {s['name']} · {s['direction'].upper()} · "
            f"{s['confidence']:.0f}% · ₹{s['price']:,.1f} ({s['chg_day']:+.2f}%)",
            expanded=False,
        ):
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Entry", f"₹{s['price']:,.1f}")
            c2.metric("Stop", f"₹{s['stop']:,.1f}",
                      delta=f"{s['stop_pct']*100:.2f}%", delta_color="off")
            c3.metric("Target (2R)", f"₹{s['target']:,.1f}")
            c4.metric("Size (¼-Kelly)",
                      "SKIP" if s["no_trade"] else f"{s['kelly_pct']:.1f}% cap")
            c5.metric("RVOL", f"{s['rvol']:.1f}×",
                      delta=f"RSI {s['rsi']:.0f}", delta_color="off")
            st.markdown(
                f"<span style='color:{dir_color};font-weight:600'>Why:</span> "
                f"<span style='color:#c8cce0'>{' · '.join(s['why'])}</span> "
                f"<span style='color:#5a6378'>· OR {s['or_lo']:,.1f}–{s['or_hi']:,.1f} "
                f"· VWAP dev {s['vwap_dev']:+.2f}%</span>",
                unsafe_allow_html=True,
            )

            # ── Trade ticket (MIS) — sized from capital × ¼-Kelly ────────────
            qty = 0 if s["no_trade"] else int(capital * s["kelly_pct"] / 100 / s["price"])
            if qty >= 1:
                action = "buy" if s["direction"] == "long" else "sell"
                st.markdown(
                    f"<div style='background:#0f1422;border:1px solid #1f2937;"
                    f"border-radius:6px;padding:8px 12px;font-family:IBM Plex Mono,"
                    f"monospace;font-size:12px;color:#c8cce0'>"
                    f"🎫 MIS {action.upper()} <b>{qty}</b> × {sym} @ "
                    f"₹{s['price']:,.1f} · SL ₹{s['stop']:,.1f} · "
                    f"TGT ₹{s['target']:,.1f} · risk ≈ "
                    f"₹{qty * abs(s['price'] - s['stop']):,.0f}</div>",
                    unsafe_allow_html=True,
                )
                if breeze_live and bz.orders_enabled() and session["can_enter"]:
                    ok = st.checkbox(f"I confirm this {action.upper()} order",
                                     key=f"cnf_{sym}")
                    if st.button(f"Place MIS {action.upper()} · {qty} {sym}",
                                 key=f"ord_{sym}", disabled=not ok):
                        r = bz.place_intraday_order(s["ticker"], action, qty,
                                                    s["price"], confirm=ok)
                        (st.success if r["ok"] else st.error)(
                            f"{r['msg']}" + (f" · ID {r.get('order_id')}" if r.get("order_id") else ""))
                        if r["ok"]:
                            st.caption("⚠ Entry leg only — set the SL/target in "
                                       "your broker app immediately.")
                elif breeze_live and not bz.orders_enabled():
                    st.caption("🔒 Order routing disabled (set BREEZE_ALLOW_ORDERS=true "
                               "in .env to enable the button — entries always need "
                               "a manual confirm).")
            if not session["can_enter"]:
                st.caption(f"⏳ {session['note']}")


main()
