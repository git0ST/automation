"""Auto-mode paper trading + market-shift adaptation.

Every pipeline pass, run_paper_cycle():
  1. ADAPT  — detect regime flips (NIFTY trend) and VIX spikes → de-risk
              (half Kelly, temporarily raised entry bar); self-throttle the
              entry threshold from the rolling hit-rate of closed trades.
  2. MANAGE — mark open positions to market on daily bars: stop hit, target
              hit (stop checked first within a bar — conservative), or
              time-stop at horizon expiry → close + record realized P&L.
  3. ENTER  — open virtual positions from the system's OWN recent predictions
              (≥ adaptive threshold, deduped, ¼-Kelly sized, vol-scaled stops,
              2R targets, 60% gross-exposure cap, max 15 concurrent).

Persistence: Supabase `paper_trades` (migration 015) via the service key;
falls back to a local JSON book (~/.intl_snapshots/paper_trades.json) until
the migration is run — auto-mode works either way. Adaptation state lives in
~/.intl_snapshots/paper_state.json.

This book is position-level ground truth: predictions measure *direction*,
the paper book measures *the whole discipline* (sizing, stops, exits).
"""
from __future__ import annotations
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT, _ROOT / "streamlit"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_DIR = Path.home() / ".intl_snapshots"
_STATE = _DIR / "paper_state.json"
_LOCAL_BOOK = _DIR / "paper_trades.json"

CAPITAL = float(os.getenv("PAPER_CAPITAL", "1000000"))
GROSS_CAP, MAX_OPEN, POS_CAP = 0.60, 15, 0.15
TIME_STOP_DAYS = {"intraday": 2, "short": 14, "medium": 45, "long": 90}
BASE_THRESHOLD, MIN_TH, MAX_TH = 55.0, 50.0, 70.0


# ── Persistence (Supabase first, local JSON fallback) ─────────────────────────

def _client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not (url and key):
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None


def _sb_available(client) -> bool:
    try:
        client.table("paper_trades").select("id").limit(1).execute()
        return True
    except Exception:
        return False


def _local_load() -> list[dict]:
    try:
        return json.loads(_LOCAL_BOOK.read_text())
    except Exception:
        return []


def _local_save(trades: list[dict]) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    _LOCAL_BOOK.write_text(json.dumps(trades, default=str))


def load_open_trades() -> tuple[list[dict], str]:
    """→ (open trades, backend 'supabase'|'local')."""
    c = _client()
    if c and _sb_available(c):
        rows = (c.table("paper_trades").select("*").eq("status", "open")
                .execute()).data or []
        return rows, "supabase"
    return [t for t in _local_load() if t.get("status") == "open"], "local"


def _save_new(trade: dict, backend: str) -> None:
    if backend == "supabase":
        _client().table("paper_trades").insert(trade).execute()
    else:
        book = _local_load()
        trade["id"] = str(uuid.uuid4())[:8]
        book.append(trade)
        _local_save(book)


def _save_close(trade: dict, backend: str, exit_price: float,
                reason: str) -> dict:
    entry = float(trade["entry_price"])
    sign = 1 if trade["direction"] == "bullish" else -1
    pnl = (exit_price / entry - 1) * 100 * sign
    upd = {"status": "closed", "exit_price": round(exit_price, 2),
           "exit_at": datetime.now(timezone.utc).isoformat(),
           "exit_reason": reason, "pnl_pct": round(pnl, 3)}
    if backend == "supabase":
        _client().table("paper_trades").update(upd).eq("id", trade["id"]).execute()
    else:
        book = _local_load()
        for t in book:
            if t.get("id") == trade.get("id"):
                t.update(upd)
        _local_save(book)
    return {**trade, **upd}


# ── Adaptation state ──────────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        return json.loads(_STATE.read_text())
    except Exception:
        return {"regime": None, "conf_threshold": BASE_THRESHOLD,
                "derisk_until": None, "recent_closed": []}


def _save_state(s: dict) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    _STATE.write_text(json.dumps(s, default=str))


def _derisk_active(s: dict) -> bool:
    du = s.get("derisk_until")
    if not du:
        return False
    try:
        return datetime.now(timezone.utc) < datetime.fromisoformat(du)
    except Exception:
        return False


# ── The cycle ─────────────────────────────────────────────────────────────────

def run_paper_cycle() -> dict:
    import numpy as np
    import yfinance as yf

    state = _load_state()
    events: list[str] = []

    # 1 ── ADAPT: regime flip + VIX spike → de-risk window
    try:
        from shared.india_swing import india_regime
        reg = india_regime()
        cur = f"india_{reg['trend']}"
        if state.get("regime") and state["regime"] != cur:
            state["derisk_until"] = (datetime.now(timezone.utc)
                                     + timedelta(days=3)).isoformat()
            state["conf_threshold"] = min(MAX_TH, state["conf_threshold"] + 5)
            events.append(f"REGIME FLIP {state['regime']}→{cur}: de-risk 3d, "
                          f"bar→{state['conf_threshold']:.0f}%")
        state["regime"] = cur
        if reg.get("vix") and reg["vix"] > 25:
            state["derisk_until"] = (datetime.now(timezone.utc)
                                     + timedelta(days=2)).isoformat()
            events.append(f"VIX SPIKE {reg['vix']:.1f}: de-risk 2d")
    except Exception:
        reg = {"srs": 50, "trend": "?"}

    open_trades, backend = load_open_trades()

    # 2 ── MANAGE: mark to market on daily bars since entry
    closed = []
    if open_trades:
        tks = sorted({t["ticker"] for t in open_trades})
        bars = yf.download(tks, period="1mo", interval="1d", group_by="ticker",
                           threads=True, progress=False, auto_adjust=True)
        for t in open_trades:
            try:
                df = bars[t["ticker"]].dropna(subset=["Close"]) if len(tks) > 1 \
                     else bars.dropna(subset=["Close"])
                ent = datetime.fromisoformat(str(t["entry_at"]).replace("Z", "+00:00"))
                df = df[df.index.tz_localize(None) >= ent.replace(tzinfo=None)
                        - timedelta(days=1)]
                if df.empty:
                    continue
                stop, tgt = float(t["stop_price"]), float(t["target_price"])
                long = t["direction"] == "bullish"
                exit_px = reason = None
                for _, b in df.iterrows():
                    lo, hi = float(b["Low"]), float(b["High"])
                    if long and lo <= stop:
                        exit_px, reason = stop, "stop"; break
                    if long and hi >= tgt:
                        exit_px, reason = tgt, "target"; break
                    if not long and hi >= stop:
                        exit_px, reason = stop, "stop"; break
                    if not long and lo <= tgt:
                        exit_px, reason = tgt, "target"; break
                ts_at = t.get("time_stop_at")
                if not reason and ts_at and datetime.now(timezone.utc) >= \
                        datetime.fromisoformat(str(ts_at).replace("Z", "+00:00")):
                    exit_px, reason = float(df["Close"].iloc[-1]), "time"
                if reason:
                    closed.append(_save_close(t, backend, exit_px, reason))
            except Exception:
                continue
        open_trades = [t for t in open_trades
                       if t["ticker"] not in {c["ticker"] for c in closed}]

    # Self-throttle from rolling hit-rate of last 20 closed
    if closed:
        rc = (state.get("recent_closed") or [])
        rc.extend([1 if c["pnl_pct"] > 0 else 0 for c in closed])
        state["recent_closed"] = rc[-20:]
        if len(state["recent_closed"]) >= 10:
            hit = sum(state["recent_closed"]) / len(state["recent_closed"])
            if hit < 0.45:
                state["conf_threshold"] = min(MAX_TH, state["conf_threshold"] + 2)
                events.append(f"hit {hit:.0%}<45%: bar→{state['conf_threshold']:.0f}%")
            elif hit > 0.60:
                state["conf_threshold"] = max(MIN_TH, state["conf_threshold"] - 2)
                events.append(f"hit {hit:.0%}>60%: bar→{state['conf_threshold']:.0f}%")

    # 3 ── ENTER: new positions from the system's own recent predictions
    opened = []
    c = _client()
    threshold = state["conf_threshold"]
    kelly_frac = 0.125 if _derisk_active(state) else 0.25
    if c:
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat()
            preds = (c.table("predictions").select(
                        "ticker,direction,confidence_pct,price_at_pred,"
                        "horizon,source_page,regime_at_pred")
                     .gte("predicted_at", cutoff)
                     .gte("confidence_pct", threshold)
                     .neq("direction", "neutral")
                     .order("confidence_pct", desc=True).limit(40)
                     .execute()).data or []
        except Exception:
            preds = []
        held = {t["ticker"] for t in open_trades}
        gross = sum(float(t.get("notional") or 0) for t in open_trades)
        from _strategy_engine import kelly_position_sizing
        seen = set()
        for p in preds:
            tk = p["ticker"]
            if tk in held or tk in seen or len(open_trades) + len(opened) >= MAX_OPEN:
                continue
            seen.add(tk)
            try:
                h = yf.Ticker(tk).history(period="3mo", interval="1d",
                                          auto_adjust=True)
                arr = h["Close"].to_numpy(dtype=float)
                if len(arr) < 21:
                    continue
                price = float(arr[-1])
                dvol = float(np.std(np.diff(np.log(arr[-63:])), ddof=1)) \
                    if len(arr) >= 22 else 0.015
                stop_pct = min(0.12, max(0.025, 2.0 * dvol))
                k = kelly_position_sizing(
                    win_prob=float(p["confidence_pct"]) / 100, payoff_ratio=2.0,
                    portfolio_value=CAPITAL, stop_pct=stop_pct,
                    kelly_fraction=kelly_frac, max_position_pct=POS_CAP)
                if k["no_trade"] or k["position_value"] < CAPITAL * 0.005:
                    continue
                notional = min(k["position_value"], CAPITAL * GROSS_CAP - gross)
                if notional <= 0:
                    continue
                long = p["direction"] == "bullish"
                sp = price * (1 - stop_pct) if long else price * (1 + stop_pct)
                tp = price * (1 + 2 * stop_pct) if long else price * (1 - 2 * stop_pct)
                days = TIME_STOP_DAYS.get(p.get("horizon") or "", 30)
                trade = {
                    "ticker": tk, "direction": p["direction"],
                    "market": "india" if tk.endswith(".NS") else "us",
                    "source": p.get("source_page"), "horizon": p.get("horizon"),
                    "confidence": float(p["confidence_pct"]),
                    "entry_price": round(price, 2),
                    "entry_at": datetime.now(timezone.utc).isoformat(),
                    "qty": round(notional / price, 2),
                    "notional": round(notional, 2),
                    "stop_price": round(sp, 2), "target_price": round(tp, 2),
                    "time_stop_at": (datetime.now(timezone.utc)
                                     + timedelta(days=days)).isoformat(),
                    "status": "open",
                    "regime_at_entry": p.get("regime_at_pred") or state.get("regime"),
                }
                _save_new(trade, backend)
                gross += notional
                opened.append(trade)
            except Exception:
                continue

    _save_state(state)
    return {"backend": backend, "opened": len(opened), "closed": len(closed),
            "open_now": len(open_trades) + len(opened),
            "threshold": state["conf_threshold"],
            "derisk": _derisk_active(state),
            "events": events,
            "closed_pnl": [round(c["pnl_pct"], 2) for c in closed]}
