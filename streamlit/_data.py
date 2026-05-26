"""INTL Data Layer — defensive data fetching with graceful fallbacks."""
from __future__ import annotations
import os
import streamlit as st


# ── Supabase client ──────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def supabase_client():
    """Cached Supabase client. Returns None if credentials missing."""
    url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None


def _is_missing_table(err: Exception, table: str) -> bool:
    """Check if exception is the 'table not in schema cache' error."""
    msg = str(err)
    return table in msg and "schema cache" in msg


# ── Sentiment aggregation (credibility-weighted) ─────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def load_weighted_sentiment(limit: int = 200, time_decay: bool = True) -> dict:
    """Aggregate sentiment across articles, weighted by source credibility + time decay."""
    articles, _ = load_articles(limit=limit)
    try:
        from shared.credibility import weighted_sentiment
        return weighted_sentiment(articles, time_decay=time_decay)
    except Exception:
        bull = sum(1 for a in articles if a.get("sentiment_label") == "bullish")
        bear = sum(1 for a in articles if a.get("sentiment_label") == "bearish")
        total = max(len(articles), 1)
        return {
            "bullish_pct":    round(bull / total * 100, 1),
            "bearish_pct":    round(bear / total * 100, 1),
            "neutral_pct":    round((1 - (bull + bear) / total) * 100, 1),
            "weighted_score": 0.0,
            "n_items":        len(articles),
            "total_weight":   0.0,
        }


@st.cache_data(ttl=300, show_spinner=False)
def load_per_ticker_sentiment(tickers: tuple, limit: int = 200) -> dict:
    """Per-ticker sentiment from recent articles. Cached per (tickers, limit)."""
    if not tickers:
        return {}
    articles, _ = load_articles(limit=limit)
    try:
        from shared.credibility import per_ticker_sentiment
        return per_ticker_sentiment(articles, list(tickers))
    except Exception:
        return {}


# ── Articles (news feed) ─────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def load_articles(limit: int = 200) -> tuple[list, str]:
    """Load articles. Returns (list, status) where status is: ok | empty | missing | error.

    Sort priority: hybrid recency × terminal_score. Try inserted_at column first
    (post-migration 008), fall back to briefing_date order.
    """
    client = supabase_client()
    if not client:
        return [], "missing"

    # Prefer inserted_at (intraday resolution) if migration 008 applied
    for order_col in ("inserted_at", "briefing_date"):
        try:
            rows = (client.table("articles")
                    .select("*")
                    .order(order_col, desc=True)
                    .order("terminal_score", desc=True)
                    .limit(limit)
                    .execute()).data or []
            rows = [r for r in rows if isinstance(r, dict)]
            return rows, "ok" if rows else "empty"
        except Exception as e:
            err = str(e)
            if "schema cache" in err and order_col in err:
                continue   # column doesn't exist yet, try fallback
            if _is_missing_table(e, "articles"):
                return [], "missing"
            return [], "error"
    return [], "error"


@st.cache_data(ttl=60, show_spinner=False)
def load_data_freshness() -> dict:
    """Returns last update timestamps per source + overall pipeline freshness.

    Used by the UI to show 'Data is X minutes old' indicators.
    """
    client = supabase_client()
    if not client:
        return {}
    try:
        rows = (client.table("v_data_freshness")
                .select("*")
                .execute()).data or []
        if not rows:
            return {}
        # Most recent insert across all sources
        latest = max((r.get("last_inserted") for r in rows if r.get("last_inserted")),
                     default=None)
        return {
            "per_source": rows,
            "latest_insert": latest,
            "minutes_since_latest":
                min((r.get("minutes_since_last") for r in rows
                     if r.get("minutes_since_last") is not None), default=None),
        }
    except Exception:
        # v_data_freshness view doesn't exist — fall back to articles direct query
        try:
            row = (client.table("articles")
                   .select("briefing_date,inserted_at")
                   .order("briefing_date", desc=True)
                   .limit(1)
                   .execute()).data or []
            if row:
                return {"latest_insert": row[0].get("inserted_at") or row[0].get("briefing_date")}
        except Exception:
            pass
        return {}


# ── Signals ──────────────────────────────────────────────────────────────────

@st.cache_data(ttl=180, show_spinner=False)
def load_signals(limit: int = 50) -> tuple[list, str]:
    """Load alpha signals (insider, options, congress, FINRA)."""
    client = supabase_client()
    if not client:
        return [], "missing"
    try:
        rows = (client.table("signals")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()).data or []
        rows = [r for r in rows if isinstance(r, dict)]
        return rows, "ok" if rows else "empty"
    except Exception as e:
        if _is_missing_table(e, "signals"):
            return [], "missing"
        return [], "error"


# ── Market snapshots ─────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def load_market_snapshots(limit: int = 60) -> tuple[list, str]:
    client = supabase_client()
    if not client:
        return [], "missing"
    try:
        rows = (client.table("market_snapshots")
                .select("*")
                .order("snapshot_at", desc=True)
                .limit(limit)
                .execute()).data or []
        return [r for r in rows if isinstance(r, dict)], "ok" if rows else "empty"
    except Exception as e:
        if _is_missing_table(e, "market_snapshots"):
            return [], "missing"
        return [], "error"


# ── Regime + Risk (with live FRED fallback) ──────────────────────────────────

# FRED series IDs — keyed by series_id with raw float values to match
# the format detect_regime() and compute_risk() expect.
FRED_SERIES = [
    "T10Y2Y", "T10Y3M",                  # yield curve
    "FEDFUNDS", "DFF", "DGS10", "DGS2",  # rates
    "CPIAUCSL", "PCEPI", "T10YIE",       # inflation
    "UNRATE", "PAYEMS", "ICSA",          # labor
    "VIXCLS", "DTWEXBGS",                # risk + FX
    "BAMLH0A0HYM2", "BAMLC0A0CM", "TEDRATE",  # credit
    "INDPRO", "GDPC1",                   # growth
]


@st.cache_data(ttl=900, show_spinner=False)  # 15 min — FRED updates daily
def fetch_fred_live() -> dict:
    """Fetch latest macro values from FRED public CSV.

    Returns dict keyed by FRED series_id (T10Y2Y, VIXCLS, ...) with raw float
    values — matches the shape detect_regime() and compute_risk() require.
    """
    import httpx
    macro: dict[str, float] = {}
    try:
        with httpx.Client(timeout=10) as client:
            for series_id in FRED_SERIES:
                try:
                    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
                    r = client.get(url)
                    if r.status_code != 200:
                        continue
                    lines = [ln.strip() for ln in r.text.splitlines() if ln.strip()]
                    for row in reversed(lines[1:]):
                        parts = row.split(",")
                        if len(parts) >= 2 and parts[1] not in (".", ""):
                            try:
                                macro[series_id] = float(parts[1])
                                break
                            except ValueError:
                                continue
                except Exception:
                    continue
    except Exception:
        pass
    return macro


@st.cache_data(ttl=600, show_spinner=False)
def compute_regime_risk_live():
    """Compute regime + risk from live FRED data. Heavy — cached aggressively."""
    macro = fetch_fred_live()
    if not macro:
        return {}, {}
    try:
        from intelligence.regime import detect_regime, regime_to_dict
        from intelligence.risk   import compute_risk, risk_to_dict
        regime_obj = detect_regime(macro, sentiment_score=0.0)
        risk_obj   = compute_risk(macro, fear_greed_value=50, sentiment_avg=0.0)
        return regime_to_dict(regime_obj), risk_to_dict(risk_obj)
    except Exception:
        return {}, {}


@st.cache_data(ttl=60, show_spinner=False)
def load_regime_risk() -> tuple[dict, dict, list[str], str]:
    """Returns (regime, risk, missing_tables, source).
    source: supabase | live_fred | empty
    """
    client = supabase_client()
    missing = []
    regime, risk = {}, {}

    if client:
        try:
            rows = (client.table("regime_snapshots")
                    .select("*").order("captured_at", desc=True).limit(1)
                    .execute()).data
            regime = rows[0] if rows else {}
        except Exception as e:
            if _is_missing_table(e, "regime_snapshots"):
                missing.append("regime_snapshots")

        try:
            rows = (client.table("risk_scores")
                    .select("*").order("captured_at", desc=True).limit(1)
                    .execute()).data
            risk = rows[0] if rows else {}
        except Exception as e:
            if _is_missing_table(e, "risk_scores"):
                missing.append("risk_scores")

    if regime and risk:
        return regime, risk, missing, "supabase"

    # Fallback: live FRED
    live_regime, live_risk = compute_regime_risk_live()
    if not regime and live_regime:
        regime = live_regime
    if not risk and live_risk:
        risk = live_risk

    if regime or risk:
        return regime, risk, missing, "live_fred"
    return {}, {}, missing, "empty"


# ── Market prices (yfinance batched) ─────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def load_market_prices(tickers: tuple) -> dict:
    """Batched yfinance fetch — single API call for N tickers."""
    if not tickers:
        return {}
    try:
        import yfinance as yf
        prices = {}
        try:
            batch = yf.download(
                list(tickers), period="5d", interval="1d",
                auto_adjust=True, progress=False, group_by="ticker", threads=True,
            )
            for ticker in tickers:
                try:
                    if len(tickers) > 1 and ticker in batch.columns.get_level_values(0):
                        sub = batch[ticker].dropna()
                    else:
                        sub = batch.dropna()
                    if sub.empty:
                        continue
                    closes = sub["Close"]
                    prev = float(closes.iloc[-2]) if len(closes) >= 2 else float(closes.iloc[-1])
                    last = float(closes.iloc[-1])
                    prices[ticker] = {
                        "price":      round(last, 2),
                        "change_pct": round((last / prev - 1) * 100, 2) if prev else 0,
                        "history":    [round(float(x), 2) for x in closes.tolist()[-5:]],
                    }
                except Exception:
                    continue
        except Exception:
            for ticker in tickers:
                try:
                    h = yf.Ticker(ticker).history(period="5d", auto_adjust=True)
                    if not h.empty:
                        last = float(h["Close"].iloc[-1])
                        prev = float(h["Close"].iloc[-2]) if len(h) >= 2 else last
                        prices[ticker] = {
                            "price": round(last, 2),
                            "change_pct": round((last / prev - 1) * 100, 2) if prev else 0,
                            "history": h["Close"].tolist()[-5:],
                        }
                except Exception:
                    continue
        return prices
    except Exception:
        return {}


# ── Setup status check ───────────────────────────────────────────────────────

@st.cache_data(ttl=120)
def check_setup_status() -> dict:
    """Returns setup status for all required tables. Used by setup checker."""
    client = supabase_client()
    if not client:
        return {"supabase_connected": False}

    status = {"supabase_connected": True, "tables": {}}
    for table in ["articles", "signals", "market_snapshots",
                  "regime_snapshots", "risk_scores",
                  "portfolio_positions", "api_cache", "credit_spreads"]:
        try:
            r = client.table(table).select("id", count="exact", head=True).execute()
            status["tables"][table] = {"exists": True, "rows": r.count if hasattr(r, "count") else 0}
        except Exception as e:
            if _is_missing_table(e, table):
                status["tables"][table] = {"exists": False, "rows": 0}
            else:
                status["tables"][table] = {"exists": "unknown", "rows": 0}

    # Aggregate readiness
    intelligence_ready = all(status["tables"].get(t, {}).get("exists") is True
                             for t in ["regime_snapshots", "risk_scores"])
    portfolio_ready    = status["tables"].get("portfolio_positions", {}).get("exists") is True
    has_pipeline_data  = status["tables"].get("articles", {}).get("rows", 0) > 0

    status["intelligence_ready"] = intelligence_ready
    status["portfolio_ready"]    = portfolio_ready
    status["has_pipeline_data"]  = has_pipeline_data
    return status
