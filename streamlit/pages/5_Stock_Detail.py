"""Stock Detail page — single-ticker deep analysis.

Sections:
  1. Company overview + plain-English summary
  2. Live price card with 1D/1W/1M/1Y change
  3. Interactive price chart (candlestick + volume)
  4. Key fundamentals (P/E, EPS, market cap...)
  5. Technical indicators (RSI, SMA, MACD) — explained
  6. Risk metrics (VaR, Sharpe, MaxDD) — explained
  7. AI Prediction with confidence + rationale
  8. Recent news + analyst consensus
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for p in (ROOT, ROOT / "projects" / "daily_digest"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import streamlit as st

st.set_page_config(page_title="Stock Detail · INTL", page_icon="🔍", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _theme         import apply_theme, COLORS, status_pill
from _stock_analysis import (technical_signal, sentiment_signal,
                              analyst_signal, vol_signal, composite_prediction)
from _components    import TICKER_META
apply_theme()
from _terminal_chrome import render_chrome
render_chrome("Stock_Detail")


# Plain-English explanations for each metric — shown via st.metric(help=...)
EXPLAIN = {
    "price":      "Last traded price. Updated real-time when Finnhub is configured, else 15-min delayed.",
    "change_1d":  "Today's price change vs yesterday's close. Positive = up.",
    "change_1w":  "Price change over the past 5 trading days.",
    "change_1m":  "Price change over the past ~21 trading days (1 month).",
    "change_1y":  "Price change over the past year. Compare to S&P 500 for outperformance.",
    "market_cap": "Total company value = price × shares outstanding. >$200B = mega cap, $10-200B = large cap.",
    "pe_ratio":   "Price-to-Earnings. Lower = cheaper relative to profits. Tech ~25-40, value stocks ~10-15.",
    "eps":        "Earnings per share (annual). The profit each share earned last year.",
    "div_yield":  "Annual dividend ÷ price. 0% = no dividend (growth stock). >4% = income stock.",
    "beta":       "Sensitivity to market. β=1 moves with S&P 500. β>1 amplifies; β<0 inverse.",
    "rsi":        "0-100 momentum oscillator. >70 = overbought (pullback risk). <30 = oversold (bounce possible).",
    "sma_50":     "50-day moving average. Price above = uptrend, below = downtrend.",
    "sma_200":    "200-day average. Long-term trend. Golden Cross (50>200) is strongly bullish.",
    "vol_ann":    "Annualized volatility. Higher = wider price swings. Tech ~25-50%, utilities ~10-20%.",
    "var_95":     "Value at Risk. 95% of days the 1-day loss won't exceed this. 2% means 'worst case typical day -2%'.",
    "sharpe":     "Return per unit of risk. >1 = good, >2 = excellent. Negative = losing money.",
    "max_dd":     "Largest peak-to-trough drop over lookback. -30% means stock once fell 30% from a high.",
    "prediction": "AI composite call: combines technicals + sentiment + analysts + vol regime. Confidence drops when signals disagree.",
}


@st.cache_data(ttl=600, show_spinner=False)
def fetch_ohlc(ticker: str, period: str = "1y") -> dict | None:
    """Historical OHLCV from yfinance for chart + technicals."""
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=True)
        if hist.empty:
            return None
        return {
            "dates":  [d.strftime("%Y-%m-%d") for d in hist.index],
            "open":   hist["Open"].tolist(),
            "high":   hist["High"].tolist(),
            "low":    hist["Low"].tolist(),
            "close":  hist["Close"].tolist(),
            "volume": hist["Volume"].tolist(),
        }
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def fetch_finnhub_bundle(ticker: str) -> dict:
    """One call → profile + financials + recommendations + earnings + news."""
    try:
        from shared.finnhub_client import (is_available, company_profile_sync,
                                            basic_financials_sync, recommendations_sync,
                                            earnings_sync, company_news_sync, quote_sync,
                                            normalize_quote)
    except ImportError:
        return {}
    if not is_available():
        return {}
    quote = quote_sync(ticker)
    return {
        "profile":         company_profile_sync(ticker),
        "financials":      basic_financials_sync(ticker) or {},
        "recommendations": recommendations_sync(ticker),
        "earnings":        earnings_sync(ticker),
        "news":            company_news_sync(ticker, lookback_days=7, limit=10),
        "quote":           normalize_quote(ticker, quote) if quote else None,
    }


def main():
    col_t, col_r = st.columns([6, 1])
    with col_t:
        st.title("🔍 Stock Detail")
        st.caption("Real-time price · technicals · risk · AI prediction with confidence")
    with col_r:
        st.write("")
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # Ticker search — by symbol OR company name, with live preview (same engine
    # as the global command bar). Selecting a result loads it in place.
    col_input, col_period = st.columns([3, 1])
    with col_input:
        sd_query = st.text_input(
            "Find a ticker",
            placeholder="Search by symbol or name — NVDA · Apple · Bitcoin…",
            key="sd_search_q",
        )
    with col_period:
        period = st.selectbox("History", ["3mo", "6mo", "1y", "2y", "5y"], index=2)

    # Live preview rows (rendered full-width below to avoid nested columns).
    from _terminal_chrome import render_search_results
    shown = render_search_results(sd_query, key_prefix="sd_search",
                                  session_key="detail_ticker", navigate_to=None)

    # Raw fallback — ONLY when nothing matched the search (a genuinely unknown
    # symbol like ROKU). If previews exist the user should click one; a
    # company-name query like "apple" must not be analyzed as the literal
    # symbol "APPLE".
    raw = (sd_query or "").strip().upper()
    if not shown and raw and 1 <= len(raw) <= 6 \
            and raw.replace("-", "").replace(".", "").isalnum() \
            and raw != st.session_state.get("detail_ticker"):
        if st.button(f"↗ Analyze {raw} directly", key="sd_raw_go"):
            st.session_state["detail_ticker"] = raw
            st.rerun()

    ticker = st.session_state.get("detail_ticker", "NVDA")

    if not ticker:
        st.info("Search for a ticker or company above to analyse.")
        return

    # Show which ticker is currently loaded (search box is for switching)
    st.caption(f"Showing **{ticker}** · search above to switch.")

    # Load data in parallel-ish (caches help here)
    with st.spinner(f"Loading {ticker} data…"):
        ohlc = fetch_ohlc(ticker, period=period)
        bundle = fetch_finnhub_bundle(ticker)

    if not ohlc:
        st.error(f"Could not fetch price data for `{ticker}`. Check the symbol.")
        return

    # ── 1. Header + live price card ─────────────────────────────────────────
    _render_header(ticker, ohlc, bundle)

    st.divider()

    # ── 2. Plain-English company summary ────────────────────────────────────
    _render_summary(ticker, bundle)

    st.divider()

    # ── 3. Price chart ──────────────────────────────────────────────────────
    _render_price_chart(ticker, ohlc, period)

    st.divider()

    # ── 4. Key fundamentals ─────────────────────────────────────────────────
    _render_fundamentals(bundle)

    st.divider()

    # ── 5. Technical indicators ─────────────────────────────────────────────
    tech = _render_technicals(ticker, ohlc)

    st.divider()

    # ── 6. Risk metrics ─────────────────────────────────────────────────────
    risk = _render_risk_metrics(ticker, ohlc, period)

    st.divider()

    # ── 7. AI Prediction ────────────────────────────────────────────────────
    _render_prediction(ticker, ohlc, tech, risk, bundle)

    st.divider()

    # ── 8. Recent news + analyst consensus ──────────────────────────────────
    _render_news_and_analysts(ticker, bundle)


# ── Section renderers ──────────────────────────────────────────────────────

def _render_header(ticker, ohlc, bundle):
    closes = ohlc["close"]
    last  = closes[-1]
    prev  = closes[-2] if len(closes) >= 2 else last
    chg_1d  = (last / prev - 1) * 100 if prev else 0
    chg_1w  = (last / closes[-5] - 1) * 100 if len(closes) >= 5 else 0
    chg_1m  = (last / closes[-21] - 1) * 100 if len(closes) >= 21 else 0
    chg_1y  = (last / closes[0] - 1) * 100 if len(closes) >= 200 else 0

    profile = bundle.get("profile") or {}
    name    = profile.get("name") or TICKER_META.get(ticker, {}).get("name", ticker)
    industry = profile.get("finnhubIndustry") or TICKER_META.get(ticker, {}).get("sector", "—")
    mcap    = profile.get("marketCapitalization", 0)
    mcap_str = f"${mcap/1000:.1f}B" if mcap > 1000 else f"${mcap:.0f}M" if mcap else "—"

    rt_source = "● REAL-TIME" if bundle.get("quote") else "○ 15-MIN DELAYED"
    rt_kind = "live" if bundle.get("quote") else "stale"

    st.markdown(f"### {name} ({ticker})")
    st.caption(f"{industry} · Market cap {mcap_str} · "
               f"{status_pill(rt_source, rt_kind)}", unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Price",  f"${last:,.2f}", delta=f"{chg_1d:+.2f}% today", help=EXPLAIN["price"])
    c2.metric("1 Week", f"{chg_1w:+.2f}%", delta_color="off",
              help=EXPLAIN["change_1w"])
    c3.metric("1 Month", f"{chg_1m:+.2f}%", delta_color="off", help=EXPLAIN["change_1m"])
    c4.metric("1 Year", f"{chg_1y:+.2f}%", delta_color="off", help=EXPLAIN["change_1y"])
    c5.metric("Market Cap", mcap_str, delta_color="off", help=EXPLAIN["market_cap"])


def _render_summary(ticker, bundle):
    """AI-generated plain-English summary of current state."""
    st.markdown("#### 📝 What's happening now")
    profile = bundle.get("profile") or {}
    if profile.get("description"):
        st.markdown(f"**About:** {profile['description'][:400]}…")
    elif profile.get("name"):
        st.markdown(f"**{profile['name']}** — {profile.get('finnhubIndustry', 'company')}.")

    # AI summary from Groq if available + we have news
    news = bundle.get("news", []) or []
    if not news:
        st.caption("No recent company-specific news to summarize.")
        return

    if st.button(f"🤖 Generate AI summary of recent {ticker} news",
                 use_container_width=True):
        try:
            from shared.groq_client import chat, is_ai_available
            if not is_ai_available():
                st.warning("Add GROQ_API_KEY to Streamlit secrets for AI summaries.")
                return
            headlines = "\n".join(f"- {n.get('headline', '')[:120]}"
                                  for n in news[:6])
            with st.spinner("Generating summary via Groq…"):
                summary = chat(
                    f"Recent {ticker} headlines:\n{headlines}",
                    system=(
                        "You are a Bloomberg market analyst. In 3 short sentences "
                        "for a retail trader who isn't a finance expert: what's happening, "
                        "why it matters for the stock, and what to watch next. Be direct, "
                        "no jargon."
                    ),
                    model="smart", max_tokens=280,
                )
            st.info(summary)
        except Exception as e:
            st.error(f"AI summary failed: {e}")


def _render_price_chart(ticker, ohlc, period):
    st.markdown("#### 📊 Price History")
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        import pandas as pd

        df = pd.DataFrame({
            "Date":  pd.to_datetime(ohlc["dates"]),
            "Open":  ohlc["open"],
            "High":  ohlc["high"],
            "Low":   ohlc["low"],
            "Close": ohlc["close"],
            "Volume": ohlc["volume"],
        }).set_index("Date")

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                            vertical_spacing=0.03,
                            row_heights=[0.75, 0.25])

        fig.add_trace(go.Candlestick(
            x=df.index, open=df["Open"], high=df["High"],
            low=df["Low"], close=df["Close"], name=ticker,
            increasing_line_color="#00d68f", decreasing_line_color="#ff5773",
        ), row=1, col=1)

        # SMA overlays
        if len(df) >= 50:
            df["SMA50"] = df["Close"].rolling(50).mean()
            fig.add_trace(go.Scatter(x=df.index, y=df["SMA50"], name="SMA 50",
                                     line=dict(color="#ffaa00", width=1.5)),
                          row=1, col=1)
        if len(df) >= 200:
            df["SMA200"] = df["Close"].rolling(200).mean()
            fig.add_trace(go.Scatter(x=df.index, y=df["SMA200"], name="SMA 200",
                                     line=dict(color="#4c8bf5", width=1.5)),
                          row=1, col=1)

        # Volume bar
        colors = ["#00d68f" if c >= o else "#ff5773"
                  for c, o in zip(df["Close"], df["Open"])]
        fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="Volume",
                             marker_color=colors, opacity=0.6),
                      row=2, col=1)

        fig.update_layout(
            height=520,
            margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor=COLORS["bg"], plot_bgcolor=COLORS["bg"],
            font=dict(color=COLORS["text"], family="Inter"),
            xaxis_rangeslider_visible=False,
            xaxis=dict(gridcolor=COLORS["border"]),
            xaxis2=dict(gridcolor=COLORS["border"]),
            yaxis=dict(gridcolor=COLORS["border"], title="Price ($)"),
            yaxis2=dict(gridcolor=COLORS["border"], title="Volume"),
            legend=dict(bgcolor=COLORS["surface"], bordercolor=COLORS["border"]),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True, theme=None)
        st.caption("Green candles = up day, red = down. Yellow line = 50-day average (medium-term trend). "
                   "Blue line = 200-day average (long-term trend).")
    except Exception as e:
        st.error(f"Chart failed: {e}")


def _render_fundamentals(bundle):
    fin = bundle.get("financials") or {}
    if not fin:
        return
    st.markdown("#### 💰 Key Fundamentals")
    c1, c2, c3, c4, c5 = st.columns(5)

    pe   = fin.get("peNormalizedAnnual") or fin.get("peExclExtraAnnual")
    eps  = fin.get("epsBasicExclExtraItemsAnnual") or fin.get("epsAnnual")
    yld  = fin.get("dividendYieldIndicatedAnnual")
    beta = fin.get("beta")
    pb   = fin.get("pbAnnual")

    c1.metric("P/E Ratio", f"{pe:.1f}" if pe else "—", help=EXPLAIN["pe_ratio"])
    c2.metric("EPS (Annual)", f"${eps:.2f}" if eps else "—", help=EXPLAIN["eps"])
    c3.metric("Div Yield",  f"{yld:.2f}%" if yld else "0.00%",
              help=EXPLAIN["div_yield"])
    c4.metric("Beta",       f"{beta:.2f}" if beta else "—", help=EXPLAIN["beta"])
    c5.metric("P/B Ratio",  f"{pb:.1f}" if pb else "—",
              help="Price-to-Book. <1 may indicate undervaluation. >5 often growth stock.")


def _render_technicals(ticker, ohlc):
    st.markdown("#### 📈 Technical Indicators")
    closes = ohlc["close"]
    if len(closes) < 30:
        st.caption("Insufficient history for technicals (need ≥30 days).")
        return None

    import numpy as np
    arr = np.array(closes)
    price = float(arr[-1])

    sma_20  = float(arr[-20:].mean())  if len(arr) >= 20  else None
    sma_50  = float(arr[-50:].mean())  if len(arr) >= 50  else None
    sma_200 = float(arr[-200:].mean()) if len(arr) >= 200 else None

    # RSI 14
    deltas = np.diff(arr[-15:])
    ups = deltas[deltas > 0].sum() if len(deltas[deltas > 0]) > 0 else 0
    downs = -deltas[deltas < 0].sum() if len(deltas[deltas < 0]) > 0 else 1e-9
    rs = ups / downs if downs else 0
    rsi_14 = 100 - 100 / (1 + rs) if rs else 50

    c1, c2, c3, c4 = st.columns(4)
    rsi_signal_text = ("Overbought (pullback risk)" if rsi_14 > 70 else
                       "Oversold (bounce possible)" if rsi_14 < 30 else
                       "Neutral momentum")
    c1.metric("RSI 14", f"{rsi_14:.1f}", delta=rsi_signal_text, delta_color="off",
              help=EXPLAIN["rsi"])
    if sma_50:
        diff = (price / sma_50 - 1) * 100
        c2.metric("vs SMA 50", f"{diff:+.2f}%",
                  delta="Above (bullish)" if diff > 0 else "Below (bearish)",
                  delta_color="off", help=EXPLAIN["sma_50"])
    if sma_200:
        diff = (price / sma_200 - 1) * 100
        c3.metric("vs SMA 200", f"{diff:+.2f}%",
                  delta="Above (bullish)" if diff > 0 else "Below (bearish)",
                  delta_color="off", help=EXPLAIN["sma_200"])
    if sma_50 and sma_200:
        golden = sma_50 > sma_200
        c4.metric("Trend Signal", "Golden Cross 📈" if golden else "Death Cross 📉",
                  delta_color="off",
                  help="Golden Cross = SMA50 above SMA200 (long-term uptrend). Death Cross = opposite.")

    return {"price": price, "sma_20": sma_20, "sma_50": sma_50,
            "sma_200": sma_200, "rsi_14": rsi_14}


def _render_risk_metrics(ticker, ohlc, period):
    st.markdown("#### 🎯 Risk Metrics")
    try:
        import asyncio
        from agents.math_agent      import compute_var
        from agents.math_advanced   import garch_11_forecast, cornish_fisher_var
        loop = asyncio.new_event_loop()
        try:
            var = loop.run_until_complete(compute_var(ticker, period=period))
        finally:
            loop.close()
    except Exception as e:
        st.caption(f"Risk computation unavailable: {e}")
        return None

    if "error" in var:
        st.warning(f"Could not compute risk: {var['error']}")
        return None

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("VaR 95%",  f"{var.get('var_95', 0):.2f}%",
              delta="1-day historical", delta_color="off", help=EXPLAIN["var_95"])
    c2.metric("Sharpe",   f"{var.get('sharpe', 0):.2f}",
              delta="Higher = better risk/return", delta_color="off",
              help=EXPLAIN["sharpe"])
    c3.metric("Annual Vol", f"{var.get('annualised_vol', 0):.1f}%",
              delta="σ × √252", delta_color="off", help=EXPLAIN["vol_ann"])
    c4.metric("Max Drawdown", f"{var.get('max_drawdown', 0):.2f}%",
              delta="Worst peak-to-trough", delta_color="off", help=EXPLAIN["max_dd"])

    # GARCH forecast (advanced)
    import numpy as np
    closes = ohlc["close"]
    returns = np.diff(np.log(np.array(closes)))
    garch = garch_11_forecast(returns.tolist(), horizon=5) if len(returns) >= 60 else {}

    if garch and "error" not in garch:
        with st.expander("📊 Advanced: GARCH(1,1) volatility forecast"):
            cc1, cc2, cc3 = st.columns(3)
            cc1.metric("5-day forecast vol", f"{garch.get('forecast_vol', 0) * 100:.3f}%",
                       help="GARCH(1,1) forecast of next-5-day daily volatility")
            cc2.metric("Long-run vol", f"{garch.get('long_run_vol', 0) * 100:.3f}%",
                       help="Mean-reversion target — average vol the model expects long-term")
            cc3.metric("Persistence", f"{garch.get('persistence', 0):.3f}",
                       help="α+β. Near 1 = vol shocks persist. <0.95 = vol mean-reverts quickly")

    return {**var, "garch": garch if garch and "error" not in garch else None}


def _render_prediction(ticker, ohlc, tech, risk, bundle):
    st.markdown("#### 🤖 AI Prediction")

    if not tech:
        st.caption("Not enough data to generate prediction.")
        return

    # Build component signals
    tech_sig = technical_signal(tech["price"], tech.get("sma_20"),
                                tech.get("sma_50"), tech.get("sma_200"),
                                tech.get("rsi_14"))

    # Per-ticker sentiment from articles
    sent_data = {}
    try:
        from _data import load_per_ticker_sentiment
        sent_data = load_per_ticker_sentiment((ticker,)).get(ticker, {})
    except Exception:
        pass
    sent_sig = sentiment_signal(sent_data)

    analyst_sig = analyst_signal(bundle.get("recommendations") or [])
    vol_sig_data = vol_signal((risk or {}).get("garch") or {})

    # Live market environment → regime-conditional weights + systemic-risk haircut
    current_regime = current_srs = None
    try:
        from _data import load_regime_risk
        regime_dict, risk_dict, _, _ = load_regime_risk()
        current_regime = regime_dict.get("regime") if regime_dict else None
        current_srs    = risk_dict.get("srs") if risk_dict else None
    except Exception:
        pass

    # Realized annualized vol from the price series for volatility targeting
    realized_vol_annual = None
    try:
        import numpy as np
        _arr = np.array(ohlc["close"], dtype=float)
        if _arr.size >= 21:
            _lr = np.diff(np.log(_arr[-63:])) if _arr.size >= 63 else np.diff(np.log(_arr))
            if _lr.size > 1:
                realized_vol_annual = float(np.std(_lr, ddof=1) * np.sqrt(252) * 100)
    except Exception:
        pass

    pred = composite_prediction(
        tech_sig, sent_sig, analyst_sig, vol_sig_data,
        regime=current_regime,
        srs=current_srs,
        realized_vol_annual=realized_vol_annual,
    )

    # Big visual card
    dir_label = pred["direction"].upper()
    dir_color = ("#00d68f" if pred["direction"] == "bullish"
                 else "#ff5773" if pred["direction"] == "bearish"
                 else "#ffaa00")
    confidence = pred["confidence"]

    st.markdown(f"""
    <div style="background:#131825;border:1px solid #1f2937;border-radius:8px;padding:24px;margin:8px 0">
      <div style="display:flex;align-items:baseline;gap:16px;flex-wrap:wrap">
        <div style="font-size:36px;font-weight:700;color:{dir_color};font-family:'IBM Plex Mono',monospace">
          {dir_label}
        </div>
        <div style="font-size:24px;color:#e6e9f0;font-family:'IBM Plex Mono',monospace">
          {confidence}% confidence
        </div>
        <div style="font-size:13px;color:#8b93a7">
          Vol regime: <b style="color:#e6e9f0">{pred.get('vol_regime', '—').upper()}</b>
        </div>
      </div>
      <div style="background:#0f1422;border-radius:4px;height:8px;overflow:hidden;margin-top:14px">
        <div style="height:100%;width:{confidence}%;background:{dir_color}"></div>
      </div>
      <div style="color:#c8cce0;margin-top:14px;line-height:1.6">{pred['rationale']}</div>
    </div>
    """, unsafe_allow_html=True)

    # Component breakdown
    with st.expander("🔍 Signal breakdown — which components contributed?"):
        import pandas as pd
        rows = []
        for c in pred["components"]:
            rows.append({
                "Signal":    c["name"].title(),
                "Direction": c["direction"].title(),
                "Strength":  f"{c['strength']:.2f}",
                "Weight":    f"{c['weight']*100:.0f}%",
            })
        if rows:
            st.dataframe(pd.DataFrame(rows).set_index("Signal"),
                         use_container_width=True)
        st.caption(
            "**How this works**: Technical, quant (fundamental factors), analyst, "
            "sentiment and sector each vote bullish/bearish/neutral with a "
            "regime-tuned weight. Base conviction = agreement × strength × breadth, "
            "then scaled by realized volatility (vol targeting), haircut by the "
            "systemic-risk score, and finally pulled toward the historically "
            "observed hit-rate for its confidence band (empirical calibration)."
        )


def _render_news_and_analysts(ticker, bundle):
    col_news, col_consensus = st.columns([3, 2])
    with col_news:
        st.markdown(f"#### 📰 Recent {ticker} news")
        news = bundle.get("news") or []
        if not news:
            st.caption("No Finnhub news (configure FINNHUB_API_KEY for real-time news).")
        for n in news[:6]:
            src = n.get("source", "")
            hl  = n.get("headline", "")[:100]
            url = n.get("url", "#")
            sm  = n.get("summary", "")[:200]
            st.markdown(
                f'<div style="background:#131825;border:1px solid #1f2937;border-radius:6px;'
                f'padding:10px 14px;margin-bottom:8px">'
                f'<div style="display:flex;gap:8px;align-items:center;margin-bottom:4px">'
                f'<span style="color:#4c8bf5;font-size:11px;font-weight:600">{src}</span>'
                f'</div>'
                f'<a href="{url}" target="_blank" style="text-decoration:none;color:#e6e9f0;font-weight:500">{hl}</a>'
                f'<div style="color:#8b93a7;font-size:12px;margin-top:4px">{sm}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    with col_consensus:
        st.markdown("#### 👥 Analyst Consensus")
        recs = bundle.get("recommendations") or []
        if not recs:
            st.caption("No analyst data (Finnhub free tier).")
            return
        latest = recs[0]
        buy   = latest.get("strongBuy", 0) + latest.get("buy", 0)
        hold  = latest.get("hold", 0)
        sell  = latest.get("sell", 0) + latest.get("strongSell", 0)
        total = buy + hold + sell
        try:
            import plotly.graph_objects as go
            fig = go.Figure(data=[go.Pie(
                labels=["Buy", "Hold", "Sell"],
                values=[buy, hold, sell],
                hole=0.55,
                marker_colors=["#00d68f", "#8b93a7", "#ff5773"],
                textinfo="label+percent",
            )])
            fig.update_layout(
                height=300, margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor=COLORS["bg"],
                font=dict(color=COLORS["text"], family="Inter"),
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True, theme=None)
            st.caption(f"**{total}** analysts · {buy} Buy · {hold} Hold · {sell} Sell · "
                       f"Latest period: {latest.get('period', '—')}")
        except Exception:
            st.write(f"Buy: {buy} · Hold: {hold} · Sell: {sell}")


main()
