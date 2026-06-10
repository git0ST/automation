"""ICICI Direct Breeze client — execution-grade NSE data + gated order entry.

Why this exists: yfinance NSE bars lag ~1–2 min, which is fine for signal
generation but not for live intraday execution. Breeze provides real-time
quotes, 1/5/30-minute historical bars, and order placement against the user's
own ICICI Direct account.

Credentials (in .env, never committed):
    BREEZE_API_KEY        — from api.icicidirect.com app registration
    BREEZE_API_SECRET     — same page
    BREEZE_SESSION_TOKEN  — DAILY token: log in via login_url(), copy the
                            `apisession` value from the redirect URL bar.
    BREEZE_ALLOW_ORDERS   — must be the literal string "true" to enable
                            place_order(); anything else → orders hard-blocked.

Operational reality (SEBI static-IP rule, in force since 1 Apr 2026): API
calls must originate from the IP registered with the app. That means Breeze
works when the terminal runs LOCALLY (or on a VM whose static IP you
registered) — the Streamlit Cloud deployment keeps using yfinance.

Symbol mapping: Breeze uses ICICI's own stock codes (e.g. RELIANCE → RELIND).
nse_to_isec() resolves via the SDK's get_names() and caches per-process.
"""
from __future__ import annotations
import os
from datetime import datetime, timedelta
from typing import Optional

_client = None          # process-level singleton
_code_cache: dict = {}  # NSE symbol -> ISEC stock code


def is_configured() -> bool:
    return bool(os.getenv("BREEZE_API_KEY") and os.getenv("BREEZE_API_SECRET"))


def login_url() -> str:
    """Where the user fetches today's session token (valid ~24h)."""
    import urllib.parse
    key = urllib.parse.quote_plus(os.getenv("BREEZE_API_KEY", ""))
    return f"https://api.icicidirect.com/apiuser/login?api_key={key}"


def connect():
    """Singleton authenticated BreezeConnect, or None (missing creds / stale
    daily token / network). Callers must handle None → fall back to yfinance."""
    global _client
    if _client is not None:
        return _client
    if not is_configured() or not os.getenv("BREEZE_SESSION_TOKEN"):
        return None
    try:
        from breeze_connect import BreezeConnect
        b = BreezeConnect(api_key=os.getenv("BREEZE_API_KEY"))
        b.generate_session(api_secret=os.getenv("BREEZE_API_SECRET"),
                           session_token=os.getenv("BREEZE_SESSION_TOKEN"))
        _client = b
        return b
    except Exception:
        return None


def is_live() -> bool:
    return connect() is not None


def _unwrap(resp):
    """Breeze responses arrive as {'Success': [...], 'Status': 200, 'Error': x}."""
    if isinstance(resp, dict):
        ok = resp.get("Success")
        if ok:
            return ok[0] if isinstance(ok, list) and ok else ok
    return None


def nse_to_isec(nse_symbol: str) -> Optional[str]:
    """Map an NSE symbol (RELIANCE / RELIANCE.NS) to ICICI's stock code."""
    sym = nse_symbol.replace(".NS", "").upper()
    if sym in _code_cache:
        return _code_cache[sym]
    b = connect()
    if not b:
        return None
    try:
        r = b.get_names(exchange_code="NSE", stock_code=sym)
        code = (r.get("isec_stock_code") if isinstance(r, dict)
                else getattr(r, "isec_stock_code", None))
        if code:
            code = str(code).strip()
            _code_cache[sym] = code
            return code
    except Exception:
        pass
    return None


def get_quote(nse_symbol: str) -> Optional[dict]:
    """Real-time quote → {ltp, prev_close, change_pct, volume, ts} or None."""
    b = connect()
    code = nse_to_isec(nse_symbol)
    if not (b and code):
        return None
    try:
        q = _unwrap(b.get_quotes(stock_code=code, exchange_code="NSE",
                                 product_type="cash", expiry_date="",
                                 right="", strike_price=""))
        if not q:
            return None
        ltp = float(q.get("ltp") or 0)
        prev = float(q.get("previous_close") or q.get("prev_close") or 0)
        return {
            "ltp": ltp,
            "prev_close": prev,
            "change_pct": (ltp / prev - 1) * 100 if prev else 0.0,
            "volume": q.get("total_quantity_traded") or q.get("volume"),
            "ts": q.get("ltt") or datetime.now().isoformat(),
        }
    except Exception:
        return None


def get_intraday_bars(nse_symbol: str, interval: str = "5minute",
                      days: int = 1) -> list[dict]:
    """Intraday OHLCV bars (list of dicts, oldest→newest). Empty on failure.
    interval ∈ {1minute, 5minute, 30minute, 1day}."""
    b = connect()
    code = nse_to_isec(nse_symbol)
    if not (b and code):
        return []
    try:
        to_d = datetime.now()
        from_d = to_d - timedelta(days=days)
        r = b.get_historical_data_v2(
            interval=interval,
            from_date=from_d.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            to_date=to_d.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            stock_code=code, exchange_code="NSE", product_type="cash")
        rows = r.get("Success") if isinstance(r, dict) else None
        return rows or []
    except Exception:
        return []


# ── Order entry (hard-gated) ──────────────────────────────────────────────────

def orders_enabled() -> bool:
    return os.getenv("BREEZE_ALLOW_ORDERS", "").strip().lower() == "true"


def place_intraday_order(nse_symbol: str, action: str, quantity: int,
                         limit_price: float, confirm: bool = False) -> dict:
    """Place an intraday (margin/MIS) LIMIT order on NSE.

    DOUBLE-GATED: requires BREEZE_ALLOW_ORDERS=true in the environment AND an
    explicit confirm=True from a user interaction. Never call this from any
    automated path — entries are human decisions; this only routes them.
    Stop-loss/target management stays with the user (broker app), v1 places
    the entry leg only.
    """
    if not orders_enabled():
        return {"ok": False, "msg": "Orders disabled (set BREEZE_ALLOW_ORDERS=true to enable)."}
    if not confirm:
        return {"ok": False, "msg": "Order not confirmed by user."}
    if action not in ("buy", "sell") or quantity < 1 or limit_price <= 0:
        return {"ok": False, "msg": "Invalid order parameters."}
    b = connect()
    code = nse_to_isec(nse_symbol)
    if not (b and code):
        return {"ok": False, "msg": "Breeze session not live (refresh daily token)."}
    try:
        r = b.place_order(
            stock_code=code, exchange_code="NSE", product="margin",
            action=action, order_type="limit", quantity=str(int(quantity)),
            price=str(round(limit_price, 2)), validity="day",
            stoploss="", disclosed_quantity="0",
        )
        ok = isinstance(r, dict) and r.get("Status") == 200
        detail = (_unwrap(r) or {}) if ok else {}
        return {"ok": ok,
                "order_id": detail.get("order_id"),
                "msg": (r.get("Error") if isinstance(r, dict) else None) or
                       ("Order placed." if ok else "Order rejected.")}
    except Exception as e:
        return {"ok": False, "msg": f"Order failed: {e}"}
