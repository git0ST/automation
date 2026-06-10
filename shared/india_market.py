"""India market module — NSE universe + trading-session logic.

Single source of truth for the India intraday layer:
  * NIFTY50 — liquid large-cap universe (yfinance .NS symbols) with sectors.
  * INDIA_INDICES — NIFTY / BANKNIFTY / India VIX context symbols.
  * nse_session() — IST-aware session state machine (pre-open, opening range,
    regular, closing window, closed) used to gate entries the way intraday
    desks do: no fresh entries while the opening range is forming or in the
    square-off window.

Pure data + stdlib (zoneinfo); safe to import from the Streamlit app, the
pipeline, or headless scripts.

Known limitation: index composition drifts a few names per year and NSE
holidays are not encoded (weekday check only) — both are display-level
concerns, not correctness risks, since prices simply stop updating on holidays.
"""
from __future__ import annotations
from datetime import datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# ── NIFTY 50 universe (yfinance suffix .NS) ───────────────────────────────────
NIFTY50: dict[str, dict] = {
    "RELIANCE.NS":   {"name": "Reliance Industries", "sector": "Energy"},
    "HDFCBANK.NS":   {"name": "HDFC Bank",           "sector": "Bank"},
    "ICICIBANK.NS":  {"name": "ICICI Bank",          "sector": "Bank"},
    "SBIN.NS":       {"name": "State Bank of India", "sector": "Bank"},
    "KOTAKBANK.NS":  {"name": "Kotak Mahindra Bank", "sector": "Bank"},
    "AXISBANK.NS":   {"name": "Axis Bank",           "sector": "Bank"},
    "INDUSINDBK.NS": {"name": "IndusInd Bank",       "sector": "Bank"},
    "TCS.NS":        {"name": "TCS",                 "sector": "IT"},
    "INFY.NS":       {"name": "Infosys",             "sector": "IT"},
    "HCLTECH.NS":    {"name": "HCL Technologies",    "sector": "IT"},
    "WIPRO.NS":      {"name": "Wipro",               "sector": "IT"},
    "TECHM.NS":      {"name": "Tech Mahindra",       "sector": "IT"},
    "BHARTIARTL.NS": {"name": "Bharti Airtel",       "sector": "Telecom"},
    "BAJFINANCE.NS": {"name": "Bajaj Finance",       "sector": "NBFC"},
    "BAJAJFINSV.NS": {"name": "Bajaj Finserv",       "sector": "NBFC"},
    "SHRIRAMFIN.NS": {"name": "Shriram Finance",     "sector": "NBFC"},
    "HDFCLIFE.NS":   {"name": "HDFC Life",           "sector": "Insurance"},
    "SBILIFE.NS":    {"name": "SBI Life",            "sector": "Insurance"},
    "MARUTI.NS":     {"name": "Maruti Suzuki",       "sector": "Auto"},
    "M&M.NS":        {"name": "Mahindra & Mahindra", "sector": "Auto"},
    "JIOFIN.NS":     {"name": "Jio Financial",       "sector": "NBFC"},
    "BAJAJ-AUTO.NS": {"name": "Bajaj Auto",          "sector": "Auto"},
    "EICHERMOT.NS":  {"name": "Eicher Motors",       "sector": "Auto"},
    "HEROMOTOCO.NS": {"name": "Hero MotoCorp",       "sector": "Auto"},
    "SUNPHARMA.NS":  {"name": "Sun Pharma",          "sector": "Pharma"},
    "DRREDDY.NS":    {"name": "Dr. Reddy's",         "sector": "Pharma"},
    "CIPLA.NS":      {"name": "Cipla",               "sector": "Pharma"},
    "APOLLOHOSP.NS": {"name": "Apollo Hospitals",    "sector": "Healthcare"},
    "HINDUNILVR.NS": {"name": "Hindustan Unilever",  "sector": "FMCG"},
    "ITC.NS":        {"name": "ITC",                 "sector": "FMCG"},
    "NESTLEIND.NS":  {"name": "Nestlé India",        "sector": "FMCG"},
    "BRITANNIA.NS":  {"name": "Britannia",           "sector": "FMCG"},
    "TATACONSUM.NS": {"name": "Tata Consumer",       "sector": "FMCG"},
    "TITAN.NS":      {"name": "Titan",               "sector": "Consumer"},
    "TRENT.NS":      {"name": "Trent",               "sector": "Consumer"},
    "ASIANPAINT.NS": {"name": "Asian Paints",        "sector": "Consumer"},
    "LT.NS":         {"name": "Larsen & Toubro",     "sector": "Infra"},
    "ULTRACEMCO.NS": {"name": "UltraTech Cement",    "sector": "Cement"},
    "GRASIM.NS":     {"name": "Grasim",              "sector": "Cement"},
    "NTPC.NS":       {"name": "NTPC",                "sector": "Power"},
    "POWERGRID.NS":  {"name": "Power Grid",          "sector": "Power"},
    "COALINDIA.NS":  {"name": "Coal India",          "sector": "Energy"},
    "ONGC.NS":       {"name": "ONGC",                "sector": "Energy"},
    "BPCL.NS":       {"name": "BPCL",                "sector": "Energy"},
    "TATASTEEL.NS":  {"name": "Tata Steel",          "sector": "Metals"},
    "JSWSTEEL.NS":   {"name": "JSW Steel",           "sector": "Metals"},
    "HINDALCO.NS":   {"name": "Hindalco",            "sector": "Metals"},
    "ADANIENT.NS":   {"name": "Adani Enterprises",   "sector": "Conglomerate"},
    "ADANIPORTS.NS": {"name": "Adani Ports",         "sector": "Infra"},
    "BEL.NS":        {"name": "Bharat Electronics",  "sector": "Defence"},
}

INDIA_INDICES = {
    "^NSEI":     "NIFTY 50",
    "^NSEBANK":  "NIFTY Bank",
    "^INDIAVIX": "India VIX",
}

# Session boundaries (IST)
_OPEN          = time(9, 15)
_OR_END        = time(9, 45)    # opening-range window: first 30 minutes
_SQUARE_OFF    = time(15, 10)   # brokers force-close MIS positions ~15:20
_CLOSE         = time(15, 30)


def nse_session(now: datetime | None = None) -> dict:
    """NSE session state in IST.

    Returns {phase, is_open, ist_now, minutes_to_close, can_enter, note}.
    Phases: closed · pre_open · opening_range · regular · closing_window.
    `can_enter` encodes intraday desk discipline: no fresh entries while the
    opening range is still forming or inside the MIS square-off window.
    """
    now = (now or datetime.now(IST)).astimezone(IST)
    t = now.time()
    weekday = now.weekday() < 5

    if not weekday or t < time(9, 0) or t >= _CLOSE:
        return {"phase": "closed", "is_open": False, "ist_now": now,
                "minutes_to_close": 0, "can_enter": False,
                "note": "Market closed — showing last session."}
    if t < _OPEN:
        return {"phase": "pre_open", "is_open": False, "ist_now": now,
                "minutes_to_close": 0, "can_enter": False,
                "note": "Pre-open auction — no entries until 09:15."}

    mins_to_close = (_CLOSE.hour * 60 + _CLOSE.minute) - (t.hour * 60 + t.minute)
    if t < _OR_END:
        return {"phase": "opening_range", "is_open": True, "ist_now": now,
                "minutes_to_close": mins_to_close, "can_enter": False,
                "note": "Opening range forming (09:15–09:45) — wait for the break."}
    if t >= _SQUARE_OFF:
        return {"phase": "closing_window", "is_open": True, "ist_now": now,
                "minutes_to_close": mins_to_close, "can_enter": False,
                "note": "Square-off window — manage exits, no fresh entries."}
    return {"phase": "regular", "is_open": True, "ist_now": now,
            "minutes_to_close": mins_to_close, "can_enter": True,
            "note": f"Session live · {mins_to_close} min to close."}
