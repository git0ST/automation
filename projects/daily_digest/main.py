"""
Intelligence Terminal v2.1 — FastAPI web server.

17-source pipeline: HN · arXiv · Reddit · GitHub · RSS · StackOverflow ·
  FRED · Credit Spreads · Fear&Greed · Finance · EDGAR · GDELT · StockTwits ·
  Options · CoinGecko · Congress · FINRA

Endpoints:
  GET  /                    — Terminal UI (Bloomberg/Aladdin-style dark terminal)
  GET  /api/pipeline        — Full pipeline (cached 5 min, stale-while-revalidate)
  GET  /api/market          — Market data only (cached 2 min)
  GET  /api/market/history  — Price history for sparklines (Supabase)
  GET  /api/macro           — FRED + credit spread macro indicators
  GET  /api/fear_greed      — Fear & Greed indices
  GET  /api/signals         — Trade signals: insider (edgar), options flow, congress
  GET  /api/regime          — BlackRock Aladdin-style regime classification
  GET  /api/risk            — Systemic Risk Score (0-100 composite)
  GET  /api/alerts          — Recent alerts
  GET  /api/sentiment       — Current sentiment summary
  GET  /api/stream          — SSE stream: pushed when pipeline refreshes
  GET  /api/cache           — Cache status
  POST /api/summarize       — On-demand AI summary (Ollama)
"""

import os, sys, time, asyncio, json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn
from fastapi import FastAPI, Query, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from sources import ALL_SOURCES
from agents.pipeline import run_pipeline

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")
STATIC_DIR = Path(__file__).parent / "static"

# ── Cache ──────────────────────────────────────────────────────────────────────

_cache: dict[str, dict] = {
    "pipeline": {"data": None, "ts": 0.0, "refreshing": False},
    "market":   {"data": None, "ts": 0.0, "refreshing": False},
}
PIPELINE_TTL = 300   # 5 min
MARKET_TTL   = 120   # 2 min

# ── SSE broadcast registry ────────────────────────────────────────────────────

_sse_clients: list[asyncio.Queue] = []


async def _broadcast(event_type: str, data: dict) -> None:
    if not _sse_clients:
        return
    msg = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    dead = []
    for q in _sse_clients:
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        try: _sse_clients.remove(q)
        except ValueError: pass


# ── Background auto-pipeline loop ────────────────────────────────────────────

async def _auto_pipeline_loop() -> None:
    """Runs continuously inside the server: refreshes pipeline every PIPELINE_TTL seconds."""
    await asyncio.sleep(5)          # let server finish startup first
    while True:
        await _do_pipeline_refresh(run_ai=False)
        await asyncio.sleep(PIPELINE_TTL)


async def _auto_market_loop() -> None:
    """Refreshes market tickers every MARKET_TTL seconds."""
    await asyncio.sleep(10)
    while True:
        await _do_market_refresh()
        await asyncio.sleep(MARKET_TTL)


# ── Lifespan: start background tasks ─────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_auto_pipeline_loop())
    asyncio.create_task(_auto_market_loop())
    yield


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_fresh(key: str, ttl: int) -> bool:
    c = _cache[key]
    return c["data"] is not None and (time.time() - c["ts"]) < ttl


def _build_pipeline_payload(result: dict) -> dict:
    from sources import NON_FEED_SOURCES

    items_out = []
    for item in result["items"]:
        if item.get("source") in NON_FEED_SOURCES:
            continue
        items_out.append({
            "id":              item.get("id", ""),
            "source":          item.get("source", ""),
            "title":           item.get("title", ""),
            "url":             item.get("url", ""),
            "score":           item.get("score", 0),
            "terminal_score":  item.get("terminal_score", 0),
            "preview":         (item.get("preview") or "")[:320],
            "meta":            item.get("meta", ""),
            "tags":            item.get("tags", []),
            "sector":          item.get("sector", ""),
            "sentiment_score": item.get("sentiment_score", 0),
            "sentiment_label": item.get("sentiment_label", "neutral"),
            "entities":        item.get("entities", []),
        })

    # Equities + crypto market data
    market_out = []
    for item in result.get("market_data", []):
        md = item.get("market_data", {})
        if not md:
            continue
        market_out.append({
            "ticker":     md.get("ticker", ""),
            "name":       md.get("name", ""),
            "price":      md.get("price", 0),
            "change_pct": md.get("change_pct", 0),
            "arrow":      md.get("arrow", ""),
            "type":       md.get("type", "stock"),
            "volume_usd": md.get("volume_usd"),
            "market_cap": md.get("market_cap"),
            "change_7d":  md.get("change_7d"),
        })

    # Trade signals panel (insider trades, options flow, congress STOCK Act)
    signals_out = []
    for item in result.get("signal_data", []):
        sig = {
            "id":              item.get("id", ""),
            "source":          item.get("source", ""),
            "title":           item.get("title", ""),
            "url":             item.get("url", ""),
            "preview":         (item.get("preview") or "")[:300],
            "sentiment_label": item.get("sentiment_label", "neutral"),
            "sentiment_score": item.get("sentiment_score", 0),
            "entities":        item.get("entities", []),
            "tags":            item.get("tags", []),
        }
        if item.get("option_data"):
            sig["option_data"] = item["option_data"]
        signals_out.append(sig)

    macro_out = [i["macro_data"] for i in result.get("macro_data", []) if i.get("macro_data")]
    fg_out    = [i["fear_greed"] for i in result.get("fear_greed", [])  if i.get("fear_greed")]

    # Intelligence layer — regime + systemic risk
    intelligence = result.get("intelligence", {})
    regime_out = intelligence.get("regime") or {}
    risk_out   = intelligence.get("risk") or {}

    alerts_out = []
    for a in result.get("alerts", []):
        alerts_out.append({
            "type":     a.get("type", ""),
            "title":    a.get("title", ""),
            "body":     a.get("body", ""),
            "priority": a.get("priority", 0),
            "ticker":   a.get("ticker"),
        })

    return {
        "items":       items_out,
        "market":      market_out,
        "macro":       macro_out,
        "fear_greed":  fg_out,
        "signals":     signals_out,
        "alerts":      alerts_out,
        "sentiment":   result.get("sentiment", {}),
        "briefing":    result.get("briefing", ""),
        "trends":      result.get("trends", {}),
        "regime":      regime_out,
        "risk":        risk_out,
        "fetch_stats": result.get("fetch_stats", {}),
        "run_meta":    result.get("run_meta", {}),
        "server_ts":   int(time.time()),
    }


async def _do_pipeline_refresh(run_ai: bool = False) -> None:
    if _cache["pipeline"]["refreshing"]:
        return
    _cache["pipeline"]["refreshing"] = True
    try:
        src_list = list(ALL_SOURCES)
        limits = {
            # Core news sources
            "hackernews":    15,
            "arxiv":         12,
            "reddit":        15,
            "github":        12,
            "rss":           15,
            "stackoverflow": 10,
            # Market + macro
            "finance":       20,
            "fred":          12,
            "fear_greed":    5,
            # Premium signals
            "edgar":         20,
            "options":       15,
            "congress":      15,
            # Sentiment + world news
            "gdelt":         20,
            "stocktwits":    25,
            # Crypto
            "coingecko":     20,
            # Short interest
            "finra":         15,
            # Institutional credit spreads (ICE BofA via FRED)
            "credit":        10,
        }
        result  = await run_pipeline(sources=src_list, limits=limits, run_ai=run_ai)
        payload = _build_pipeline_payload(result)
        _cache["pipeline"]["data"] = payload
        _cache["pipeline"]["ts"]   = time.time()

        # Broadcast update to all SSE clients
        regime = payload.get("regime", {})
        risk   = payload.get("risk", {})
        await _broadcast("pipeline_updated", {
            "item_count":   len(payload["items"]),
            "signal_count": len(payload["signals"]),
            "alert_count":  len(payload["alerts"]),
            "alerts":       payload["alerts"][:5],
            "sentiment":    payload["sentiment"],
            "regime_label": regime.get("label"),
            "regime_color": regime.get("color"),
            "srs":          risk.get("srs"),
            "risk_level":   risk.get("level"),
            "server_ts":    payload["server_ts"],
        })
    except Exception as e:
        print(f"[pipeline] refresh error: {e}")
        await _broadcast("pipeline_error", {"error": str(e)})
    finally:
        _cache["pipeline"]["refreshing"] = False


async def _do_market_refresh() -> None:
    if _cache["market"]["refreshing"]:
        return
    _cache["market"]["refreshing"] = True
    try:
        from sources.finance import fetch_finance
        items = await fetch_finance(limit=20)
        market_out = []
        for item in items:
            md = item.get("market_data", {})
            if not md:
                continue
            market_out.append({
                "ticker":     md.get("ticker", ""),
                "name":       md.get("name", ""),
                "price":      md.get("price", 0),
                "change_pct": md.get("change_pct", 0),
                "arrow":      md.get("arrow", ""),
                "type":       md.get("type", "stock"),
            })
        payload = {"market": market_out, "server_ts": int(time.time())}
        _cache["market"]["data"] = payload
        _cache["market"]["ts"]   = time.time()

        # Push live market ticks to SSE clients
        await _broadcast("market_tick", {"market": market_out, "server_ts": payload["server_ts"]})
    except Exception as e:
        print(f"[market] refresh error: {e}")
    finally:
        _cache["market"]["refreshing"] = False


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Intelligence Terminal", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return TEMPLATES.TemplateResponse(request=request, name="index.html")


# ── SSE Stream ────────────────────────────────────────────────────────────────

@app.get("/api/stream")
async def api_stream() -> StreamingResponse:
    """Server-Sent Events: pushes pipeline_updated / market_tick / heartbeat."""
    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    _sse_clients.append(q)

    async def generator() -> AsyncGenerator[str, None]:
        try:
            # Immediately send current cache state so the client knows it's connected
            yield "event: connected\ndata: " + json.dumps({"clients": len(_sse_clients)}) + "\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=25)
                    yield msg
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            try: _sse_clients.remove(q)
            except ValueError: pass

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering":"no",
            "Connection":       "keep-alive",
        },
    )


# ── Pipeline ──────────────────────────────────────────────────────────────────

@app.get("/api/pipeline")
async def api_pipeline(
    background_tasks: BackgroundTasks,
    refresh: bool = Query(default=False),
    run_ai:  bool = Query(default=False),
):
    if _is_fresh("pipeline", PIPELINE_TTL) and not refresh:
        data = dict(_cache["pipeline"]["data"])
        data["cached"] = True; data["stale"] = False
        data["cache_age"] = int(time.time() - _cache["pipeline"]["ts"])
        return JSONResponse(data)

    if _cache["pipeline"]["data"] and not refresh:
        background_tasks.add_task(_do_pipeline_refresh, run_ai)
        data = dict(_cache["pipeline"]["data"])
        data["cached"] = True; data["stale"] = True
        data["cache_age"] = int(time.time() - _cache["pipeline"]["ts"])
        return JSONResponse(data)

    await _do_pipeline_refresh(run_ai)
    if not _cache["pipeline"]["data"]:
        return JSONResponse({"error": "pipeline failed"}, status_code=500)
    data = dict(_cache["pipeline"]["data"])
    data["cached"] = False; data["stale"] = False; data["cache_age"] = 0
    return JSONResponse(data)


@app.get("/api/market")
async def api_market(
    background_tasks: BackgroundTasks,
    refresh: bool = Query(default=False),
):
    if _is_fresh("market", MARKET_TTL) and not refresh:
        data = dict(_cache["market"]["data"])
        data["cached"] = True; data["cache_age"] = int(time.time() - _cache["market"]["ts"])
        return JSONResponse(data)

    if _cache["market"]["data"] and not refresh:
        background_tasks.add_task(_do_market_refresh)
        data = dict(_cache["market"]["data"])
        data["cached"] = True; data["stale"] = True
        data["cache_age"] = int(time.time() - _cache["market"]["ts"])
        return JSONResponse(data)

    await _do_market_refresh()
    data = dict(_cache["market"]["data"])
    data["cached"] = False; data["cache_age"] = 0
    return JSONResponse(data)


@app.get("/api/market/history")
async def api_market_history(ticker: str = Query(...), limit: int = Query(default=50)):
    try:
        from db.supabase_sync import get_market_history
        rows = get_market_history(ticker, limit=limit)
        return JSONResponse({"ticker": ticker, "history": rows})
    except Exception as e:
        return JSONResponse({"ticker": ticker, "history": [], "error": str(e)})


@app.get("/api/macro")
async def api_macro():
    try:
        from db.supabase_sync import get_latest_macro
        rows = get_latest_macro()
        if rows:
            return JSONResponse({"macro": rows, "source": "supabase"})
    except Exception:
        pass
    try:
        from sources.fred import fetch_fred
        items = await fetch_fred()
        return JSONResponse({"macro": [i["macro_data"] for i in items if i.get("macro_data")], "source": "live"})
    except Exception as e:
        return JSONResponse({"macro": [], "error": str(e)})


@app.get("/api/fear_greed")
async def api_fear_greed():
    try:
        from db.supabase_sync import get_latest_fear_greed
        row = get_latest_fear_greed()
        if row:
            return JSONResponse({"fear_greed": [row], "source": "supabase"})
    except Exception:
        pass
    try:
        from sources.fear_greed import fetch_fear_greed
        items = await fetch_fear_greed()
        return JSONResponse({"fear_greed": [i["fear_greed"] for i in items if i.get("fear_greed")], "source": "live"})
    except Exception as e:
        return JSONResponse({"fear_greed": [], "error": str(e)})


@app.get("/api/alerts")
async def api_alerts(limit: int = Query(default=20)):
    try:
        from db.supabase_sync import get_recent_alerts
        rows = get_recent_alerts(limit=limit)
        if rows:
            return JSONResponse({"alerts": rows, "source": "supabase"})
    except Exception:
        pass
    cached = _cache["pipeline"].get("data") or {}
    return JSONResponse({"alerts": cached.get("alerts", []), "source": "cache"})


@app.get("/api/signals")
async def api_signals(
    source: str = Query(default=None, description="Filter by source: edgar|options|congress"),
    limit:  int = Query(default=30),
):
    """Return trade signals: insider (edgar), options flow, congress (STOCK Act)."""
    # Try Supabase first for persistence
    try:
        from db.supabase_sync import get_recent_signals
        rows = get_recent_signals(source=source, limit=limit)
        if rows:
            return JSONResponse({"signals": rows, "source": "supabase", "count": len(rows)})
    except Exception:
        pass
    # Fall back to in-memory pipeline cache
    cached = _cache["pipeline"].get("data") or {}
    sigs = cached.get("signals", [])
    if source:
        sigs = [s for s in sigs if s.get("source") == source]
    return JSONResponse({"signals": sigs[:limit], "source": "cache", "count": len(sigs)})


@app.get("/api/regime")
async def api_regime():
    """
    BlackRock Aladdin-style market regime classification.
    Returns: Goldilocks | Reflation | Stagflation | Deflation
    with confidence score, growth/inflation axes, and asset allocation implications.
    """
    cached = _cache["pipeline"].get("data") or {}
    regime = cached.get("regime")
    if regime:
        return JSONResponse({"regime": regime, "source": "cache",
                             "cache_age": int(time.time() - _cache["pipeline"]["ts"])})
    # Live fallback: fetch macro data and compute immediately
    try:
        from sources.fred import fetch_fred
        from intelligence.regime import detect_regime, regime_to_dict, macro_list_to_dict
        items = await fetch_fred()
        macro_dict = macro_list_to_dict([i["macro_data"] for i in items if i.get("macro_data")])
        r = detect_regime(macro_dict)
        return JSONResponse({"regime": regime_to_dict(r), "source": "live"})
    except Exception as e:
        return JSONResponse({"regime": {}, "error": str(e)}, status_code=500)


@app.get("/api/risk")
async def api_risk():
    """
    Systemic Risk Score (SRS) — 0–100 composite risk indicator.
    Inspired by BlackRock's multi-factor risk framework.
    Components: VIX (30%), Yield Curve (25%), Rate Stress (15%),
                Sentiment Extremes (15%), Labor Market (15%).
    """
    cached = _cache["pipeline"].get("data") or {}
    risk = cached.get("risk")
    if risk:
        return JSONResponse({"risk": risk, "source": "cache",
                             "cache_age": int(time.time() - _cache["pipeline"]["ts"])})
    try:
        from sources.fred import fetch_fred
        from intelligence.risk import compute_risk, risk_to_dict
        from intelligence.regime import macro_list_to_dict
        items = await fetch_fred()
        macro_dict = macro_list_to_dict([i["macro_data"] for i in items if i.get("macro_data")])
        r = compute_risk(macro_dict)
        return JSONResponse({"risk": risk_to_dict(r), "source": "live"})
    except Exception as e:
        return JSONResponse({"risk": {}, "error": str(e)}, status_code=500)


@app.get("/api/regime/history")
async def api_regime_history(limit: int = Query(default=30)):
    """Historical regime snapshots — enables regime transition analysis."""
    try:
        from db.supabase_sync import get_regime_history
        rows = get_regime_history(limit=limit)
        return JSONResponse({"history": rows, "count": len(rows)})
    except Exception as e:
        return JSONResponse({"history": [], "error": str(e)})


@app.get("/api/risk/history")
async def api_risk_history(limit: int = Query(default=30)):
    """Historical SRS snapshots — enables risk trend analysis."""
    try:
        from db.supabase_sync import get_risk_history
        rows = get_risk_history(limit=limit)
        return JSONResponse({"history": rows, "count": len(rows)})
    except Exception as e:
        return JSONResponse({"history": [], "error": str(e)})


@app.get("/api/sentiment")
async def api_sentiment():
    cached = _cache["pipeline"].get("data") or {}
    return JSONResponse({
        "sentiment": cached.get("sentiment", {}),
        "cache_age": int(time.time() - _cache["pipeline"]["ts"]) if _cache["pipeline"]["ts"] else None,
    })


@app.get("/api/cache")
async def api_cache_status():
    now = time.time()
    return JSONResponse({
        "pipeline": {
            "has_data":   _cache["pipeline"]["data"] is not None,
            "age_sec":    int(now - _cache["pipeline"]["ts"]) if _cache["pipeline"]["ts"] else None,
            "ttl_sec":    PIPELINE_TTL,
            "refreshing": _cache["pipeline"]["refreshing"],
        },
        "market": {
            "has_data":   _cache["market"]["data"] is not None,
            "age_sec":    int(now - _cache["market"]["ts"]) if _cache["market"]["ts"] else None,
            "ttl_sec":    MARKET_TTL,
            "refreshing": _cache["market"]["refreshing"],
        },
        "sse_clients": len(_sse_clients),
    })


@app.post("/api/query")
async def api_query(payload: dict):
    """
    Manager Agent endpoint — natural language query routing.
    Handles VaR, portfolio risk, technical analysis, regime, briefing, signals, news.

    Body: {"query": "What is the VaR of NVDA?"}
    """
    query = (payload.get("query") or "").strip()
    if not query:
        return JSONResponse({"error": "query field required"}, status_code=400)
    try:
        from agents.manager_agent import handle_query
        pipeline_cache = _cache["pipeline"].get("data") or {}
        result = await handle_query(query, pipeline_cache=pipeline_cache)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e), "intent": "error"}, status_code=500)


@app.post("/api/summarize")
async def api_summarize(payload: dict):
    """Summarise a single news item. Body: {"title": "...", "preview": "..."}"""
    title   = payload.get("title", "")
    preview = payload.get("preview", "")
    try:
        from agents.research_agent import summarise_item
        summary = await summarise_item({"title": title, "preview": preview})
        return {"summary": summary}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/math/var/{ticker}")
async def api_var(ticker: str, period: str = Query(default="1y")):
    """
    Value at Risk for a single ticker.
    Returns VaR 95/99, CVaR, Sharpe, Sortino, Max Drawdown, Beta.
    Data: Yahoo Finance (free, 15-min delayed).
    """
    try:
        from agents.math_agent import compute_var
        result = await compute_var(ticker.upper(), period=period)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e), "ticker": ticker}, status_code=500)


@app.post("/api/math/portfolio")
async def api_portfolio_risk(payload: dict):
    """
    Portfolio risk for a list of tickers.
    Body: {"tickers": ["NVDA","AAPL","MSFT"], "weights": [0.4,0.3,0.3], "period": "1y"}
    Returns portfolio VaR, individual metrics, correlation matrix.
    """
    tickers = payload.get("tickers", [])
    weights = payload.get("weights")
    period  = payload.get("period", "1y")
    if not tickers:
        return JSONResponse({"error": "tickers required"}, status_code=400)
    try:
        from agents.math_agent import compute_portfolio_risk
        result = await compute_portfolio_risk(tickers[:20], weights=weights, period=period)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/math/technical/{ticker}")
async def api_technical(ticker: str, period: str = Query(default="6mo")):
    """
    Technical indicators: SMA20/50/200, RSI14, trend signal.
    Data: Yahoo Finance.
    """
    try:
        from agents.math_agent import compute_technical
        result = await compute_technical(ticker.upper(), period=period)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e), "ticker": ticker}, status_code=500)


@app.get("/api/rate-limits")
async def api_rate_limits():
    """Debug: current API rate limit usage across all sources."""
    try:
        from shared.rate_limiter import rate_limit_status
        return JSONResponse(rate_limit_status())
    except Exception as e:
        return JSONResponse({"error": str(e)})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"\n  Intelligence Terminal  →  http://localhost:{port}\n")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
