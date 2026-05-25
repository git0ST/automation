"""
INTL — Intelligence Terminal (Streamlit Edition)
Deployable on Streamlit Community Cloud: share.streamlit.io

This dashboard reads from:
  - Supabase PostgreSQL (persistent storage)
  - INTL FastAPI backend (live data, optional)
  - Yahoo Finance via yfinance (free market data)

Host: https://share.streamlit.io → Connect GitHub repo → main file: streamlit/app.py
Required secrets (Streamlit Cloud → Settings → Secrets):
  SUPABASE_URL = "https://..."
  SUPABASE_ANON_KEY = "sb_publishable_..."
  GROQ_API_KEY = "gsk_..."   # optional but recommended
  INTL_API_URL = "http://..."  # optional: your deployed FastAPI URL
"""

import os
import sys
from pathlib import Path

# ── Path setup — make repo-root AND projects/daily_digest importable ────────
ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "projects" / "daily_digest"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import streamlit as st

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title    = "INTL — Intelligence Terminal",
    page_icon     = "📊",
    layout        = "wide",
    initial_sidebar_state = "expanded",
    menu_items    = {
        "Get Help":    "https://github.com/git0ST/automation",
        "Report a bug":"https://github.com/git0ST/automation/issues",
        "About":       "INTL v2.1 — Aladdin-inspired intelligence platform",
    },
)

# ── Theme CSS — Bloomberg dark theme + generous section spacing ──────────────
st.markdown("""
<style>
/* Base */
.main { background: #080810; }
.block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 100% !important; }

/* Metrics: bigger gaps + breathing room */
.stMetric {
  background: #0c0c18; border-radius: 8px; padding: 14px 16px;
  border: 1px solid #1a1b2e; margin-bottom: 0.8rem;
}
.stMetric label { color: #5a5e7a !important; font-size: 10px !important;
                  letter-spacing: .14em; text-transform: uppercase; }
.stMetric div[data-testid="metric-container"] > div:nth-child(2) {
  font-size: 24px !important; font-weight: 700 !important;
}

/* Section dividers */
hr { margin: 1.8rem 0 !important; border-color: #1a1b2e !important; }
section.main h2, section.main h3 { margin-top: 2rem !important; margin-bottom: 1rem !important; }
section.main h1 { margin-bottom: 0.4rem !important; }

/* Expandable cards — used for charts/news/regime details */
.stExpander {
  background: #0c0c18 !important; border: 1px solid #1a1b2e !important;
  border-radius: 8px !important; margin-bottom: 1rem !important;
}
.stExpander > details > summary {
  font-weight: 600; padding: 0.7rem 1rem !important; color: #c8cce0 !important;
}
.stExpander > details[open] > summary { border-bottom: 1px solid #1a1b2e; }

/* Dataframes / tables */
.stDataFrame { margin: 1rem 0 !important; border-radius: 6px; overflow: hidden; }

/* Sidebar */
[data-testid="stSidebarNav"] { background: #0c0c18; }
.sidebar-card { background: #0f0f1c; border: 1px solid #1a1b2e;
                border-radius: 8px; padding: 14px; margin-bottom: 14px; }
.regime-badge { display: inline-block; padding: 4px 10px; border-radius: 4px;
                font-weight: 700; font-size: 14px; letter-spacing: .08em; }
.srs-bar-container { background: #1a1b2e; border-radius: 4px; height: 8px; overflow: hidden; }
.srs-bar { height: 100%; border-radius: 4px; transition: width .5s ease; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] { gap: 8px; margin-bottom: 1rem; }
.stTabs [data-baseweb="tab"] { padding: 0.5rem 1rem; border-radius: 6px 6px 0 0; }

/* Containers — add bottom spacing for visual breathing */
div[data-testid="stVerticalBlock"] > div[data-testid="stHorizontalBlock"] {
  margin-bottom: 0.6rem;
}

/* Buttons */
.stButton button { border-radius: 6px; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def get_supabase():
    """Cached Supabase client (persists across reruns)."""
    url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None


@st.cache_data(ttl=180, show_spinner=False)  # cache 3 min — keep feed fresh
def load_pipeline_data():
    """Fetch latest pipeline data from FastAPI or Supabase."""
    api_url = st.secrets.get("INTL_API_URL") or os.getenv("INTL_API_URL")
    if api_url:
        try:
            import httpx
            r = httpx.get(f"{api_url}/api/pipeline", timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass

    # Fallback: direct Supabase query
    client = get_supabase()
    if not client:
        return {}
    try:
        # Pull max-coverage: 200 articles, 60 market snapshots, 50 signals
        articles = (client.table("articles")
                    .select("*")
                    .order("terminal_score", desc=True)
                    .limit(200)
                    .execute()).data or []
        market   = (client.table("market_snapshots")
                    .select("*")
                    .order("snapshot_at", desc=True)
                    .limit(60)
                    .execute()).data or []
        signals  = []
        try:
            signals = (client.table("signals")
                       .select("*")
                       .order("created_at", desc=True)
                       .limit(50)
                       .execute()).data or []
        except Exception:
            pass

        # Sentiment aggregate from articles for KPI tiles
        bull = sum(1 for a in articles if a.get("sentiment_label") == "bullish")
        bear = sum(1 for a in articles if a.get("sentiment_label") == "bearish")
        total = max(len(articles), 1)
        sentiment = {
            "bullish_pct": round(bull / total * 100),
            "bearish_pct": round(bear / total * 100),
        }
        return {"items": articles, "market": market, "signals": signals,
                "sentiment": sentiment, "source": "supabase"}
    except Exception:
        return {}


@st.cache_data(ttl=600, show_spinner=False)  # 10 min — live FRED fallback is heavy
def _compute_regime_risk_live():
    """Compute regime + risk inline from live FRED data when Supabase is empty.
    Heavy operation — cached aggressively. Falls back gracefully if any source fails."""
    try:
        from intelligence.regime import detect_regime, regime_to_dict
        from intelligence.risk   import compute_risk, risk_to_dict
        import httpx

        # FRED series we need for both regime + risk
        # Free FRED API: https://fred.stlouisfed.org/docs/api/fred/ (no key needed for public data)
        # We use the lightweight CSV endpoint
        FRED_SERIES = {
            "T10Y2Y":       "yield_curve_10y_2y",       # 10y - 2y spread
            "DFF":          "fed_funds",                # fed funds rate
            "CPIAUCSL":     "cpi",                      # consumer price index
            "UNRATE":       "unemployment",             # unemployment rate
            "VIXCLS":       "vix",                      # VIX
            "DGS10":        "treasury_10y",             # 10y treasury
            "T10YIE":       "breakeven_inflation_10y",  # 10y breakeven inflation
            "BAMLH0A0HYM2": "hy_oas",                   # ICE BofA HY OAS
        }
        macro = {}
        with httpx.Client(timeout=8) as client:
            for series_id, key in FRED_SERIES.items():
                try:
                    # Public CSV endpoint — no API key needed
                    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
                    r = client.get(url)
                    if r.status_code == 200:
                        lines = [ln.strip() for ln in r.text.splitlines() if ln.strip()]
                        # Last row with a value (skip header + missing)
                        for row in reversed(lines[1:]):
                            parts = row.split(",")
                            if len(parts) >= 2 and parts[1] not in (".", ""):
                                try:
                                    macro[key] = {
                                        "value": float(parts[1]),
                                        "period": parts[0],
                                        "series_id": series_id,
                                    }
                                    break
                                except ValueError:
                                    continue
                except Exception:
                    continue

        # Compute regime + risk
        regime_obj = detect_regime(macro, sentiment_score=0.0)
        risk_obj   = compute_risk(macro, fear_greed_value=50, sentiment_avg=0.0)
        return regime_to_dict(regime_obj), risk_to_dict(risk_obj)
    except Exception:
        return {}, {}


@st.cache_data(ttl=60, show_spinner=False)  # cache 1 min
def load_regime_risk():
    """Load latest regime + risk. Tries Supabase first, falls back to live FRED.
    Returns (regime, risk, missing_tables)."""
    client = get_supabase()
    missing = []
    regime, risk = {}, {}

    if client:
        try:
            rows = (client.table("regime_snapshots")
                    .select("*").order("captured_at", desc=True).limit(1)
                    .execute()).data
            regime = rows[0] if rows else {}
        except Exception as e:
            if "regime_snapshots" in str(e) and "schema cache" in str(e):
                missing.append("regime_snapshots")

        try:
            rows = (client.table("risk_scores")
                    .select("*").order("captured_at", desc=True).limit(1)
                    .execute()).data
            risk = rows[0] if rows else {}
        except Exception as e:
            if "risk_scores" in str(e) and "schema cache" in str(e):
                missing.append("risk_scores")

    # ── Fallback: compute live from FRED if Supabase has no data ────────────
    if not regime or not risk:
        live_regime, live_risk = _compute_regime_risk_live()
        if not regime and live_regime:
            regime = live_regime
            regime["_source"] = "live_fred"
        if not risk and live_risk:
            risk = live_risk
            risk["_source"] = "live_fred"

    return regime, risk, missing


@st.cache_data(ttl=600, show_spinner=False)  # 10-min cache (Yahoo = 15-min delay)
def load_market_prices(tickers: tuple):
    """Load recent prices via yfinance — batched for max API throughput."""
    try:
        import yfinance as yf
        data = {}
        # Use yf.download in batch — single API call for all tickers, much faster
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
                    data[ticker] = {
                        "price":      round(float(closes.iloc[-1]), 2),
                        "change_pct": round((float(closes.iloc[-1]) / float(closes.iloc[-2]) - 1) * 100, 2)
                                      if len(closes) >= 2 else 0,
                        "history":    [round(float(x), 2) for x in closes.tolist()[-5:]],
                    }
                except Exception:
                    continue
        except Exception:
            # Fallback to per-ticker fetch
            for ticker in tickers:
                try:
                    hist = yf.Ticker(ticker).history(period="5d", interval="1d", auto_adjust=True)
                    if not hist.empty:
                        data[ticker] = {
                            "price":      round(hist["Close"].iloc[-1], 2),
                            "change_pct": round((hist["Close"].iloc[-1] / hist["Close"].iloc[-2] - 1) * 100, 2)
                                          if len(hist) >= 2 else 0,
                            "history":    hist["Close"].tolist()[-5:],
                        }
                except Exception:
                    continue
        return data
    except Exception:
        return {}


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar(regime, risk):
    with st.sidebar:
        st.markdown("### 📊 INTL · Intelligence Terminal")
        st.caption("v2.1 · Aladdin-inspired platform")
        st.divider()

        # Regime card
        if regime:
            color_map = {
                "goldilocks": "#22d472", "reflation": "#e8a435",
                "stagflation": "#f75050", "deflation": "#4da6ff",
            }
            r_label = regime.get("label", "—")
            r_color = color_map.get(regime.get("regime", ""), "#888")
            r_conf  = regime.get("confidence_pct", 0)
            st.markdown(f"""
            <div class="sidebar-card">
              <div style="font-size:9px;color:#5a5e7a;letter-spacing:.14em;text-transform:uppercase;margin-bottom:6px">Market Regime · Aladdin</div>
              <div class="regime-badge" style="color:{r_color};background:{r_color}22;border:1px solid {r_color}44">{r_label}</div>
              <div style="margin-top:6px;font-size:11px;color:#5a5e7a">Confidence: <span style="color:#c8cce0">{r_conf:.0f}%</span></div>
              <div style="font-size:10px;color:#5a5e7a;margin-top:4px">Transition: {regime.get("transition_risk", "—")}</div>
            </div>""", unsafe_allow_html=True)
        else:
            st.caption("⏳ Regime data not yet available — trigger the pipeline cron to populate, or wait ~10 sec for live FRED fetch.")

        # Risk gauge
        if risk:
            srs   = risk.get("srs", 0)
            level = risk.get("level", "—")
            c = "#22d472" if srs < 26 else "#e3b341" if srs < 51 else "#f07030" if srs < 76 else "#f75050"
            st.markdown(f"""
            <div class="sidebar-card">
              <div style="font-size:9px;color:#5a5e7a;letter-spacing:.14em;text-transform:uppercase;margin-bottom:6px">Systemic Risk Score</div>
              <div style="display:flex;align-items:baseline;gap:8px">
                <span style="font-size:28px;font-weight:700;color:{c}">{srs}</span>
                <span style="font-size:11px;color:#5a5e7a">/ 100 · {level}</span>
              </div>
              <div class="srs-bar-container" style="margin-top:6px">
                <div class="srs-bar" style="width:{srs}%;background:{c}"></div>
              </div>
            </div>""", unsafe_allow_html=True)
        else:
            st.caption("⏳ Risk score not yet available — see banner above for next steps.")

        st.divider()
        st.markdown("**Navigation**")
        st.page_link("app.py",             label="🏠 Overview")
        st.page_link("pages/1_Markets.py",  label="📈 Markets")
        st.page_link("pages/2_Risk.py",     label="🎯 Risk & VaR")
        st.page_link("pages/3_Research.py", label="🔬 AI Research")
        st.page_link("pages/4_Portfolio.py",label="💼 Portfolio")
        st.divider()
        st.caption(f"Data: Yahoo Finance (15min delay) · FRED · ICE BofA")


# ── Main overview page ────────────────────────────────────────────────────────

def main():
    regime, risk, missing_tables = load_regime_risk()
    render_sidebar(regime, risk)

    # Header with refresh button
    col_title, col_refresh = st.columns([6, 1])
    with col_title:
        st.title("📊 Intelligence Terminal")
        st.caption("Bloomberg/Aladdin-inspired — free-tier market intelligence platform")
    with col_refresh:
        st.write("")
        if st.button("🔄 Refresh", use_container_width=True, help="Force re-fetch all data"):
            load_pipeline_data.clear()
            load_regime_risk.clear()
            load_market_prices.clear()
            _compute_regime_risk_live.clear()
            st.rerun()

    # Source banner — make data freshness explicit
    if regime.get("_source") == "live_fred" or risk.get("_source") == "live_fred":
        st.info(
            "📡 **Regime + Risk computed live from FRED** (pipeline cron hasn't populated Supabase yet). "
            "Trigger the pipeline at https://github.com/git0ST/automation/actions/workflows/digest.yml "
            "to enable full historical tracking + news/signals.",
            icon="📡",
        )

    # ── Setup warning if Supabase migrations not run ────────────────────────
    if missing_tables:
        st.warning(
            f"⚠ **Supabase tables missing:** `{', '.join(missing_tables)}` — "
            "run **`supabase/migrations/003_intelligence_tables.sql`** in the "
            "[Supabase SQL editor](https://supabase.com/dashboard/project/jptwbvigtgiffjqnctic/sql/new) "
            "to enable regime + risk tracking.",
            icon="⚠️",
        )

    st.divider()

    # ── Top KPIs ──────────────────────────────────────────────────────────────
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        r_label = regime.get("label", "—") if regime else "—"
        r_color_map = {"Goldilocks":"🟢","Reflation":"🟡","Stagflation":"🔴","Deflation/Recession":"🔵"}
        icon = r_color_map.get(r_label, "⚪")
        st.metric("Market Regime", f"{icon} {r_label}")

    with col2:
        srs = risk.get("srs", 0) if risk else 0
        level = risk.get("level", "—") if risk else "—"
        st.metric("Systemic Risk", f"{srs}/100", delta=f"{level}")

    with col3:
        data = load_pipeline_data()
        items = data.get("items", [])
        sent = data.get("sentiment", {})
        bull = sent.get("bullish_pct", 0)
        bear = sent.get("bearish_pct", 0)
        st.metric("Sentiment", f"↑{bull}% Bull", delta=f"↓{bear}% Bear")

    with col4:
        signals = data.get("signals", [])
        st.metric("Active Signals", len(signals), delta="insider + options + congress")

    with col5:
        st.metric("News Items", len(items), delta=f"{len(data.get('market',[]))} market tickers")

    st.divider()

    # ── Live market prices — expanded 16-ticker watchlist in batch call ──────
    st.subheader("📈 Live Markets")
    WATCHLIST = (
        # Indices
        "^GSPC", "^IXIC", "^DJI", "^VIX",
        # Mega cap
        "NVDA", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "TSLA", "AVGO",
        # Crypto
        "BTC-USD", "ETH-USD",
        # ETF benchmarks
        "SPY", "QQQ",
    )
    with st.spinner(f"Loading {len(WATCHLIST)} tickers (batched call)…"):
        mkt = load_market_prices(WATCHLIST)

    if mkt:
        # 4 cards per row — each tile wide enough for full prices ($72,345.67)
        mkt_items = list(mkt.items())
        COLS_PER_ROW = 4
        for row_start in range(0, len(mkt_items), COLS_PER_ROW):
            row_items = mkt_items[row_start:row_start + COLS_PER_ROW]
            cols = st.columns(COLS_PER_ROW)
            for col, (ticker, d) in zip(cols, row_items):
                with col:
                    delta_color = "normal" if d["change_pct"] >= 0 else "inverse"
                    st.metric(
                        label       = ticker,
                        value       = f"${d['price']:,.2f}",
                        delta       = f"{d['change_pct']:+.2f}%",
                        delta_color = delta_color,
                    )
    else:
        st.warning("Market data unavailable. Check yfinance installation.")

    st.divider()

    # ── Regime details (expandable) ───────────────────────────────────────────
    if regime:
      with st.expander("🌐 Market Regime Analysis", expanded=True):
        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown(f"**{regime.get('label', '—')}**")
            st.write(regime.get("description", "—"))
            st.metric("Confidence", f"{regime.get('confidence_pct', 0):.0f}%")
            st.metric("Transition Risk", regime.get("transition_risk", "—").upper())
        with c2:
            if regime.get("favors"):
                st.markdown("**↑ Favors:**  " + " · ".join(regime["favors"]))
            if regime.get("avoids"):
                st.markdown("**↓ Avoids:**  " + " · ".join(regime["avoids"]))
            g = regime.get("growth_score", 0)
            i = regime.get("inflation_score", 0)
            st.progress(min(max((g + 1) / 2, 0), 1), text=f"Growth axis: {g:+.3f}")
            st.progress(min(max((i + 1) / 2, 0), 1), text=f"Inflation axis: {i:+.3f}")

    st.divider()

    # ── Top news (expandable — defensive against non-dict items) ─────────────
    # Filter to only dict entries — Supabase/FastAPI may return mixed types
    dict_items = [it for it in items if isinstance(it, dict)]

    if dict_items:
        col_news, col_side = st.columns([3, 2])

        with col_news:
            with st.expander(f"📰 Top Intelligence Feed ({len(dict_items)} items)", expanded=True):
                for it in dict_items[:25]:
                    sent = it.get("sentiment_label") or "neutral"
                    sentiment_icon = "▲" if sent == "bullish" else \
                                     "▼" if sent == "bearish" else "·"
                    sent_color = "#22d472" if sent == "bullish" else \
                                 "#f75050" if sent == "bearish" else "#888"
                    src = (it.get("source") or "?").upper()[:4]
                    title = it.get("title", "—") or "—"
                    url   = it.get("url", "#") or "#"
                    score = it.get("terminal_score") or 0
                    st.markdown(
                        f"<span style='color:{sent_color};font-weight:700'>{sentiment_icon}</span> "
                        f"`{src}` [{title[:90]}]({url}) "
                        f"<span style='color:#5a5e7a;font-size:11px'>{score:.0f}pts</span>",
                        unsafe_allow_html=True,
                    )
                    if it.get("preview"):
                        st.caption(it["preview"][:180])
                    st.markdown("")  # spacing between items

        with col_side:
            # Signals panel
            sig_data = [s for s in data.get("signals", []) if isinstance(s, dict)]
            if sig_data:
                with st.expander(f"⚡ Active Signals ({len(sig_data)})", expanded=True):
                    src_label_map = {
                        "edgar": "SEC Insider", "options": "Options Flow",
                        "congress": "Congress", "finra": "FINRA Short",
                    }
                    for sig in sig_data[:15]:
                        s_label = src_label_map.get(sig.get("source"), (sig.get("source") or "?").upper())
                        s_sent = sig.get("sentiment_label") or "neutral"
                        s_icon = "▲" if s_sent == "bullish" else "▼" if s_sent == "bearish" else "—"
                        s_color = "#22d472" if s_sent == "bullish" else "#f75050" if s_sent == "bearish" else "#888"
                        st.markdown(
                            f"<span style='color:{s_color}'>{s_icon}</span> "
                            f"`{s_label}` {(sig.get('title') or '—')[:55]}",
                            unsafe_allow_html=True,
                        )

            # Briefing
            briefing = data.get("briefing", "")
            if briefing and isinstance(briefing, str):
                with st.expander("📋 Intelligence Briefing", expanded=True):
                    st.info(briefing)
    else:
        st.info("No news items yet. Run the pipeline (`gh workflow run digest.yml`) to populate the feed.")


if __name__ == "__main__":
    main()
else:
    main()
