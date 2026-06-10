"""
Intelligence Terminal — Multi-agent pipeline.

Stages:
  1. FETCH       — parallel async ingestion from all sources
  2. FILTER      — deduplicate, remove junk
  3. SCORE       — composite terminal_score
  4. SENTIMENT   — VADER for all items, entity extraction
  5. INTELLIGENCE— Regime detection + Systemic Risk Score (Aladdin-inspired)
  6. ANALYZE     — Ollama cross-source trend analysis  (run_ai=True)
  7. BRIEF       — Ollama editorial briefing           (run_ai=True)
  8. ALERTS      — detect significant market moves
  9. STORE       — persist to Supabase (async, non-blocking)
"""

import asyncio
import math
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

# ── Stage 1: Fetch ────────────────────────────────────────────────────────────

async def fetch_stage(sources: list[str], limits: dict[str, int]) -> tuple[list[dict], dict]:
    from sources import SOURCE_FETCHERS
    tasks = {}
    for src in sources:
        if src not in SOURCE_FETCHERS:
            continue
        tasks[src] = SOURCE_FETCHERS[src](limit=limits.get(src, limits.get("default", 15)))

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    items, stats = [], {}
    for src, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            stats[src] = f"ERROR: {result}"
        else:
            stats[src] = f"{len(result)} items"
            items.extend(result)
    return items, stats


# ── Stage 2: Filter ───────────────────────────────────────────────────────────

def filter_stage(items: list[dict]) -> list[dict]:
    seen_urls, seen_titles, clean = set(), set(), []
    for item in items:
        title = (item.get("title") or "").strip()
        url   = (item.get("url") or "").rstrip("/")
        if not title:
            continue
        if url and url in seen_urls:
            continue
        if not url and title in seen_titles:
            continue
        if url:
            seen_urls.add(url)
        seen_titles.add(title)
        clean.append(item)
    return clean


# ── Stage 3: Score ────────────────────────────────────────────────────────────

SOURCE_WEIGHTS = {
    "hackernews":    1.0,
    "arxiv":         0.9,
    "github":        0.8,
    "reddit":        0.7,
    "stackoverflow": 0.7,
    "rss":           0.6,
    "finance":       1.0,
    "fred":          0.5,
    "fear_greed":    0.5,
    # Premium signal sources
    "edgar":         1.2,
    "options":       1.1,
    "congress":      1.1,
    "finra":         1.0,
    "coingecko":     0.9,
    "gdelt":         0.7,
    "stocktwits":    0.6,
}


def score_stage(items: list[dict]) -> list[dict]:
    """Composite terminal score = source_weight × log(raw) × finance_score × adaptive.

    Layers:
      - source_weight  : credibility per source (SEC > Bloomberg > Reddit)
      - log(raw_score) : platform popularity, log-scaled
      - finance_score  : multi-signal relevance (0-1)
      - cross_source   : amplify if 3+ sources mention same entity
      - adaptive       : learned weight from past entity → market move correlation
    """
    # Cross-source amplification (mutates items in place)
    try:
        from shared.finance_filter import cross_source_amplify
        items = cross_source_amplify(items)
    except Exception:
        pass

    # Per-item scoring + optional adaptive layer
    try:
        from shared.adaptive_relevance import adaptive_score
        adaptive_enabled = True
    except Exception:
        adaptive_enabled = False

    for item in items:
        raw            = item.get("score") or 0
        weight         = SOURCE_WEIGHTS.get(item["source"], 0.5)
        finance_score  = float(item.get("finance_score") or 0.5)

        if adaptive_enabled and item.get("evidence"):
            try:
                finance_score, _ = adaptive_score(finance_score, item["evidence"])
            except Exception:
                pass

        base = weight * math.log(max(raw, 1) + 1) * 10
        item["terminal_score"] = round(base * finance_score, 1)

    return sorted(items, key=lambda x: x.get("terminal_score", 0), reverse=True)


# ── Stage 4: Sentiment + Entities ─────────────────────────────────────────────

def sentiment_stage(items: list[dict]) -> tuple[list[dict], dict]:
    try:
        from agents.sentiment import score_stage_sentiment, enrich_entities, compute_sentiment_summary
        items = score_stage_sentiment(items)
        items = enrich_entities(items)
        return items, compute_sentiment_summary(items)
    except Exception:
        return items, {}


# ── Stage 5: Trend Analysis ────────────────────────────────────────────────────

async def analyze_stage(items: list[dict]) -> dict:
    """Cross-source trend detection via Research Agent (Groq/Gemini/fallback)."""
    try:
        from agents.research_agent import detect_trends
        trend_text = await detect_trends(items)
        return {"cross_source": trend_text}
    except Exception:
        return {}


# ── Stage 6: Briefing ─────────────────────────────────────────────────────────

def _time_of_day() -> str:
    h = datetime.now().hour
    if h < 12: return "Morning"
    if h < 17: return "Afternoon"
    if h < 21: return "Evening"
    return "Night"


async def briefing_stage(items: list[dict], trends: dict, market_items: list[dict],
                         sentiment: dict, regime: dict = None, risk: dict = None) -> str:
    """Generate intelligence briefing via Research Agent (Groq/Gemini/fallback)."""
    try:
        from agents.research_agent import generate_briefing
        market_flat = [i["market_data"] for i in market_items if i.get("market_data")]
        return await generate_briefing(
            items       = items,
            market_data = market_flat,
            regime      = regime or {},
            risk        = risk or {},
            sentiment   = sentiment,
        )
    except Exception:
        return _fallback_briefing(items, market_items)


def _fallback_briefing(items: list[dict], market_items: list[dict]) -> str:
    tod    = _time_of_day()
    by_src = defaultdict(list)
    for item in items:
        by_src[item["source"]].append(item)
    parts = [f"{tod} Intelligence Briefing — {datetime.now().strftime('%B %d, %Y %H:%M')}"]
    for src in ["hackernews", "reddit", "rss", "arxiv"]:
        if by_src[src]:
            parts.append(f"Top {src}: \"{by_src[src][0]['title'][:65]}\"")
    if market_items:
        parts.append("Markets: " + "  ·  ".join(m["title"] for m in market_items[:4]))
    return "\n".join(parts)


# ── Stage 7: Alerts ───────────────────────────────────────────────────────────

def alerts_stage(market_flat: list[dict], sentiment: dict) -> list[dict]:
    try:
        from agents.sentiment import detect_market_alerts
        alerts = detect_market_alerts(market_flat, threshold_pct=2.5)
    except Exception:
        alerts = []

    br = sentiment.get("bearish_pct", 0)
    bl = sentiment.get("bullish_pct", 0)
    if br >= 60:
        alerts.append({"type":"sentiment","title":f"High Bearish Sentiment {br}%",
                        "body":f"{br}% of today's news is bearish — broad negative signal",
                        "priority":1,"ticker":None})
    elif bl >= 70:
        alerts.append({"type":"sentiment","title":f"High Bullish Sentiment {bl}%",
                        "body":f"{bl}% of today's news is bullish — broad positive signal",
                        "priority":0,"ticker":None})
    return alerts


# ── Stage 8: Supabase Store ───────────────────────────────────────────────────

def store_stage(items, market_flat, briefing, tod, alerts, macro_items, fg_items,
                signal_items=None, intelligence=None) -> dict:
    try:
        from db.supabase_sync import (
            is_available, upsert_articles, save_market_snapshot,
            save_briefing, create_alert, save_macro_indicators, save_fear_greed,
            save_signals, save_regime_snapshot, save_risk_score,
        )
    except ImportError:
        return {"supabase": False}

    if not is_available():
        return {"supabase": False}

    stats = upsert_articles(items)
    save_market_snapshot(market_flat)
    if briefing:
        save_briefing(briefing, len(items), tod)
    for a in alerts:
        create_alert(a["type"], a["title"], a["body"], a["priority"], a.get("ticker"))
    macro_rows = [it["macro_data"] for it in macro_items if it.get("macro_data")]
    if macro_rows:
        save_macro_indicators(macro_rows)
    for it in fg_items:
        fg = it.get("fear_greed", {})
        if fg:
            save_fear_greed(fg["value"], fg["label"], fg.get("source","crypto"))
    if signal_items:
        try:
            save_signals(signal_items)
        except Exception:
            pass
    # Persist intelligence layer snapshots for historical analytics
    if intelligence:
        try:
            if intelligence.get("regime"):
                save_regime_snapshot(intelligence["regime"])
            if intelligence.get("risk"):
                save_risk_score(intelligence["risk"])
        except Exception as e:
            print(f"  [store] intelligence persist error: {e}")
    return {"supabase": True, **stats}


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_market_data(items):
    # Include both equity (finance) and crypto (coingecko) market data
    return [i for i in items if i.get("source") in ("finance", "coingecko") and i.get("market_data")]

def extract_macro_data(items):
    return [i for i in items if i.get("source") in ("fred", "macro", "credit")]

def extract_fear_greed(items):
    return [i for i in items if i.get("source") == "fear_greed"]

def extract_signals(items):
    """Extract high-value trade signals: insider trades, options flow, congress."""
    from sources import SIGNAL_SOURCES
    return [i for i in items if i.get("source") in SIGNAL_SOURCES]


# ── Stage 5: Intelligence (Regime + Risk) ─────────────────────────────────────

def intelligence_stage(macro_items: list[dict], fg_items: list[dict], sentiment: dict) -> dict:
    """
    Run BlackRock Aladdin-inspired regime detection and systemic risk scoring.

    Returns:
        {
          "regime": RegimeReading serialized dict,
          "risk":   RiskSnapshot serialized dict,
        }
    """
    result = {"regime": None, "risk": None}
    try:
        from intelligence.regime import detect_regime, regime_to_dict, macro_list_to_dict
        from intelligence.risk import compute_risk, risk_to_dict

        # Build {series_id: value} dict from FRED + credit spread items
        macro_dict = macro_list_to_dict([
            it["macro_data"] for it in macro_items if it.get("macro_data")
        ])

        # Fear/Greed value (use equity F&G if available, else crypto)
        fg_value = None
        for item in fg_items:
            fg = item.get("fear_greed", {})
            if fg and fg.get("source") == "stocks":
                fg_value = fg.get("value")
                break
        if fg_value is None:
            for item in fg_items:
                fg = item.get("fear_greed", {})
                if fg:
                    fg_value = fg.get("value")
                    break

        sentiment_avg = sentiment.get("avg") if sentiment else None

        regime  = detect_regime(macro_dict, sentiment_score=sentiment_avg)
        risk    = compute_risk(macro_dict, fear_greed_value=fg_value, sentiment_avg=sentiment_avg)

        result["regime"] = regime_to_dict(regime)
        result["risk"]   = risk_to_dict(risk)

    except Exception as e:
        print(f"  [intelligence] error: {e}")

    return result


# ── Main Entrypoint ───────────────────────────────────────────────────────────

async def run_pipeline(
    sources: list[str],
    limits: Optional[dict] = None,
    run_ai: bool = False,
    store: bool = True,
) -> dict:
    if limits is None:
        limits = {"default": 15}

    print(f"\n  [1/8] Fetching from {len(sources)} sources…")
    raw_items, fetch_stats = await fetch_stage(sources, limits)

    print(f"  [2/8] Filtering {len(raw_items)} raw items…")
    filtered = filter_stage(raw_items)

    print(f"  [3/8] Scoring {len(filtered)} items…")
    scored = score_stage(filtered)

    print(f"  [4/9] Sentiment + entity analysis…")
    scored, sentiment = sentiment_stage(scored)

    market_data  = extract_market_data(scored)
    macro_data   = extract_macro_data(scored)
    fg_data      = extract_fear_greed(scored)
    signal_data  = extract_signals(scored)
    market_flat  = [i["market_data"] for i in market_data if i.get("market_data")]

    print(f"  [5/9] Intelligence layer (regime + risk)…")
    intelligence = intelligence_stage(macro_data, fg_data, sentiment)

    trends = {}
    briefing = ""
    if run_ai:
        print(f"  [6/9] Trend analysis (Groq/Gemini/fallback)…")
        trends = await analyze_stage(scored)
        print(f"  [7/9] Briefing generation (Groq/Gemini/fallback)…")
        briefing = await briefing_stage(
            scored, trends, market_data, sentiment,
            regime=intelligence.get("regime"),
            risk=intelligence.get("risk"),
        )
    else:
        briefing = _fallback_briefing(scored, market_data)

    print(f"  [8/9] Alert detection…")
    alerts = alerts_stage(market_flat, sentiment)

    store_stats = {}
    if store:
        print(f"  [9/9] Persisting to Supabase…")
        store_stats = store_stage(
            scored, market_flat, briefing, _time_of_day(),
            alerts, macro_data, fg_data, signal_data,
            intelligence=intelligence,
        )

        # [10] Run opportunity scanner — populate snapshots for Streamlit pages
        try:
            from agents.opportunity_runner import run_scan
            current_regime = (intelligence or {}).get("regime", {}).get("regime")
            current_srs    = (intelligence or {}).get("risk", {}).get("srs")
            print(f"  [10] Running opportunity scanner (full universe)…")
            scan_result = run_scan(current_regime=current_regime, current_srs=current_srs)
            print(f"    Scan: {scan_result.get('n_scanned')} scanned, "
                  f"{scan_result.get('n_written')} written, "
                  f"{scan_result.get('n_predicted', 0)} predictions logged, "
                  f"{scan_result.get('n_features', 0)} feature rows captured "
                  f"(finnhub={scan_result.get('finnhub')})")
            store_stats["opportunity_scan"] = scan_result
        except Exception as e:
            print(f"  [10] Opportunity scan skipped: {e}")

        # [10b] India swing scan — the India-first portfolio layer. Logs NSE
        # predictions + feature rows daily so India-specific calibration builds.
        try:
            from agents.india_runner import run_india_scan
            print(f"  [10b] Running India swing scan (NIFTY 50)…")
            india_result = run_india_scan()
            print(f"    India: {india_result.get('n_scanned', 0)} scanned, "
                  f"{india_result.get('n_predicted', 0)} predictions, "
                  f"{india_result.get('n_features', 0)} feature rows "
                  f"({india_result.get('regime', india_result.get('error', '?'))})")
            store_stats["india_scan"] = india_result
        except Exception as e:
            print(f"  [10b] India scan skipped: {e}")

        # [11] Intraday bars — sub-daily resolution (market hours only)
        intraday_items = []
        try:
            from sources.intraday import fetch_intraday
            print(f"  [11] Fetching intraday bars (market hours only)…")
            intraday_items = await fetch_intraday()
            if intraday_items:
                from db.supabase_sync import save_intraday_bars
                bars_to_save = []
                for it in intraday_items:
                    id_data = it.get("intraday_data", {})
                    bars_to_save.extend([
                        {k: v for k, v in b.items() if k != "ticker" or True}
                        for b in id_data.get("all_bars", [])
                    ])
                n_written = save_intraday_bars(bars_to_save)
                print(f"    Intraday: {len(intraday_items)} tickers, {n_written} bars saved")
            else:
                print(f"    Intraday: outside market hours — skipped")
        except Exception as e:
            print(f"  [11] Intraday fetch skipped: {e}")

        # [12] Earnings calendar — event risk awareness
        try:
            from sources.earnings_calendar import fetch_earnings_calendar
            print(f"  [12] Refreshing earnings calendar…")
            await fetch_earnings_calendar()
        except Exception as e:
            print(f"  [12] Earnings calendar skipped: {e}")

        # [13] Signal engine — execution-grade trade signals
        try:
            from agents.signal_engine import generate_trade_signals
            current_regime = (intelligence or {}).get("regime", {}).get("regime")
            print(f"  [13] Generating trade signals…")
            pipeline_payload = {
                "items":   scored,
                "signals": [{"source": s.get("source"), "title": s.get("title"),
                             "sentiment_label": s.get("sentiment_label"),
                             "sentiment_score": s.get("sentiment_score"),
                             "entities": s.get("entities", []),
                             "option_data": s.get("option_data"),
                             "payload": s.get("payload")}
                            for s in signal_data],
                "market":  market_flat,
                "macro":   [it["macro_data"] for it in macro_data if it.get("macro_data")],
            }
            trade_signals = await generate_trade_signals(
                pipeline_payload,
                intraday_items=intraday_items,
                regime=current_regime,
                max_signals=10,
            )
            store_stats["trade_signals"] = len(trade_signals)
            print(f"    Signals: {len(trade_signals)} fired")
        except Exception as e:
            print(f"  [13] Signal engine skipped: {e}")
            trade_signals = []

        # [14] Data lake — compressed snapshot for ML / backtesting
        try:
            from shared.data_lake import write_snapshot
            print(f"  [14] Writing data lake snapshot…")
            snap_payload = {
                "items":      scored[:100],
                "market":     market_flat,
                "macro":      [it["macro_data"] for it in macro_data if it.get("macro_data")],
                "fear_greed": [it["fear_greed"] for it in fg_data if it.get("fear_greed")],
                "signals":    [{"source": s.get("source"), "title": s.get("title"),
                                "sentiment_label": s.get("sentiment_label"),
                                "sentiment_score": s.get("sentiment_score"),
                                "entities": s.get("entities", [])}
                               for s in signal_data],
                "sentiment":  sentiment,
                "regime":     intelligence.get("regime") if intelligence else {},
                "risk":       intelligence.get("risk") if intelligence else {},
                "alerts":     alerts,
                "run_meta":   {"timestamp": datetime.now(timezone.utc).isoformat(),
                               "sources": sources, "total_items": len(scored)},
            }
            snap_result = write_snapshot(snap_payload, intraday_items=intraday_items)
            store_stats["data_lake"] = snap_result
        except Exception as e:
            print(f"  [14] Data lake snapshot skipped: {e}")

        # [15] Self-improvement loop — score past predictions against realized
        # outcomes, then re-tune model weights. THIS closes the learning loop:
        # without it, predictions are logged but never measured, so calibration,
        # hit-rate tracking and adaptive weighting all have zero data to learn
        # from. Runs every pipeline pass; outcomes fill in as time elapses
        # (return_1d next day, return_7d after a week, …). Weights auto-activate
        # only once ≥50 settled predictions exist (guarded in run_learning_cycle).
        try:
            from shared.learning_loop import run_learning_cycle
            print(f"  [15] Self-improvement: correlating outcomes + tuning weights…")
            learn = run_learning_cycle(auto_activate=True)
            corr = learn.get("correlation") or {}
            tuned = learn.get("tuning") or {}
            print(f"    Learning: {corr.get('updated', 0)} outcomes correlated "
                  f"({corr.get('processed', 0)} processed) · "
                  f"trained_on={tuned.get('trained_on', 0)} · "
                  f"weights {'ACTIVATED' if learn.get('activated') else 'unchanged'}")
            store_stats["learning"] = learn
        except Exception as e:
            print(f"  [15] Self-improvement cycle skipped: {e}")

        # [16] Auto-mode paper trading — act on our own predictions virtually:
        # manage stops/targets/time-stops, open new entries, adapt to regime
        # shifts (de-risk on flips / VIX spikes, hit-rate-driven entry bar).
        try:
            from shared.paper_trader import run_paper_cycle
            print(f"  [16] Paper trading cycle…")
            paper = run_paper_cycle()
            print(f"    Paper: +{paper['opened']} opened, {paper['closed']} closed "
                  f"{paper['closed_pnl'] or ''} · {paper['open_now']} open · "
                  f"bar {paper['threshold']:.0f}%"
                  f"{' · DE-RISK' if paper['derisk'] else ''} "
                  f"[{paper['backend']}]")
            for ev in paper.get("events", []):
                print(f"    ⚡ {ev}")
            store_stats["paper"] = paper
        except Exception as e:
            print(f"  [16] Paper trading skipped: {e}")

    return {
        "items":        scored,
        "market_data":  market_data,
        "macro_data":   macro_data,
        "fear_greed":   fg_data,
        "signal_data":  signal_data,
        "alerts":       alerts,
        "briefing":     briefing,
        "trends":       trends,
        "sentiment":    sentiment,
        "intelligence": intelligence,
        "fetch_stats":  fetch_stats,
        "store_stats":  store_stats,
        "run_meta": {
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "time_of_day": _time_of_day(),
            "total_raw":   len(raw_items),
            "total_clean": len(filtered),
            "sources":     sources,
        },
    }
