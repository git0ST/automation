"""
Token-bucket rate limiter + Supabase-backed API response cache.

Prevents hitting free-tier API limits:
  - Yahoo Finance: ~2,000 req/hour (no official limit but rate-limited)
  - Alpha Vantage: 25 req/day (free), 75/min (premium)
  - Financial Modeling Prep: 250 req/day (free)
  - FRED: 120 req/min (no key), 1,000/min (with key)
  - Groq: 14,400 req/day, 6,000 TPM

Usage:
    from shared.rate_limiter import rate_limit, cached_fetch

    @rate_limit("alpha_vantage", max_per_day=25)
    async def fetch_av_data(...):
        ...

    data = await cached_fetch("av:AAPL:daily", ttl_hours=24, fetcher=fetch_av_data)
"""

import asyncio
import hashlib
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Optional

# ── In-memory token bucket ────────────────────────────────────────────────────

_buckets: dict[str, dict] = defaultdict(lambda: {"tokens": 0, "last": 0.0, "daily": 0, "day": ""})

FREE_TIER_LIMITS = {
    "yahoo_finance":   {"per_min": 100,  "per_day": 0},       # no official daily limit
    "alpha_vantage":   {"per_min": 5,    "per_day": 25},       # free tier
    "fmp":             {"per_min": 10,   "per_day": 250},      # free tier
    "fred":            {"per_min": 120,  "per_day": 0},        # free, generous
    "groq":            {"per_min": 30,   "per_day": 14400},    # free tier
    "gemini":          {"per_min": 15,   "per_day": 1500},     # free tier
    "coingecko":       {"per_min": 10,   "per_day": 0},        # free, 10-50/min
    "newsapi":         {"per_min": 100,  "per_day": 100},      # free tier
    "default":         {"per_min": 60,   "per_day": 0},
}


def check_rate_limit(source: str) -> tuple[bool, str]:
    """
    Check if a request is allowed.

    Returns:
        (allowed: bool, reason: str)
    """
    limits = FREE_TIER_LIMITS.get(source, FREE_TIER_LIMITS["default"])
    bucket = _buckets[source]
    now    = time.time()
    today  = datetime.now().strftime("%Y-%m-%d")

    # Reset daily count on new day
    if bucket["day"] != today:
        bucket["day"]  = today
        bucket["daily"] = 0

    # Check daily limit
    if limits["per_day"] > 0 and bucket["daily"] >= limits["per_day"]:
        return False, f"{source}: daily limit {limits['per_day']} reached"

    # Check per-minute limit (token bucket, refill rate = per_min/60 per second)
    elapsed = now - bucket["last"]
    refill  = elapsed * (limits["per_min"] / 60.0)
    bucket["tokens"] = min(limits["per_min"], bucket["tokens"] + refill)
    bucket["last"]   = now

    if bucket["tokens"] < 1:
        wait_ms = int((1 - bucket["tokens"]) * 60 / limits["per_min"] * 1000)
        return False, f"{source}: rate limited, retry in ~{wait_ms}ms"

    bucket["tokens"] -= 1
    bucket["daily"]  += 1
    return True, "ok"


async def wait_for_rate_limit(source: str, max_wait: float = 5.0) -> bool:
    """Wait until rate limit allows a request, or timeout."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        allowed, _ = check_rate_limit(source)
        if allowed:
            return True
        await asyncio.sleep(0.1)
    return False


# ── In-memory response cache ──────────────────────────────────────────────────
# For expensive API calls (AV, FMP), cache in Supabase to survive restarts.
# For cheap calls (Yahoo), use in-memory with short TTL.

_mem_cache: dict[str, dict] = {}


def _cache_key(source: str, params: Any) -> str:
    raw = json.dumps({"s": source, "p": params}, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


def cache_get(key: str, ttl_sec: int = 3600) -> Optional[Any]:
    """Get from in-memory cache."""
    entry = _mem_cache.get(key)
    if not entry:
        return None
    if time.time() - entry["ts"] > ttl_sec:
        del _mem_cache[key]
        return None
    return entry["data"]


def cache_set(key: str, data: Any) -> None:
    """Set in-memory cache entry."""
    _mem_cache[key] = {"data": data, "ts": time.time()}


def cache_clear(pattern: str = "") -> int:
    """Clear cache entries matching pattern. Returns count cleared."""
    if not pattern:
        n = len(_mem_cache)
        _mem_cache.clear()
        return n
    keys = [k for k in _mem_cache if pattern in k]
    for k in keys:
        del _mem_cache[k]
    return len(keys)


# ── Supabase-backed persistent cache ─────────────────────────────────────────

def supabase_cache_get(cache_key: str) -> Optional[Any]:
    """Get from Supabase api_cache table (survives server restarts)."""
    try:
        from db.supabase_sync import get_client
        client = get_client()
        if not client:
            return None
        row = (client.table("api_cache")
               .select("data,expires_at")
               .eq("cache_key", cache_key)
               .maybe_single()
               .execute())
        if not row.data:
            return None
        expires = row.data.get("expires_at")
        if expires:
            exp_ts = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > exp_ts:
                return None  # expired
        return json.loads(row.data["data"])
    except Exception:
        return None


def supabase_cache_set(cache_key: str, data: Any, ttl_hours: int = 24) -> None:
    """Persist to Supabase api_cache table."""
    try:
        from db.supabase_sync import get_client
        client = get_client()
        if not client:
            return
        expires_at = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        # expires at midnight UTC + ttl_hours
        from datetime import timedelta
        expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
        client.table("api_cache").upsert({
            "cache_key":  cache_key,
            "data":       json.dumps(data, default=str),
            "expires_at": expires_at.isoformat(),
        }, on_conflict="cache_key").execute()
    except Exception:
        pass


async def cached_fetch(
    cache_key:   str,
    fetcher:     Callable,
    ttl_sec:     int = 3600,
    ttl_hours:   int = 0,         # if set, also persist to Supabase
    source_name: str = "default",
) -> Optional[Any]:
    """
    Cache-first async data fetch.

    1. Check in-memory cache
    2. Check Supabase (if ttl_hours > 0)
    3. Fetch live (respecting rate limits)
    4. Cache result in both layers
    """
    # L1: memory cache
    result = cache_get(cache_key, ttl_sec)
    if result is not None:
        return result

    # L2: Supabase persistent cache
    if ttl_hours > 0:
        result = supabase_cache_get(cache_key)
        if result is not None:
            cache_set(cache_key, result)
            return result

    # L3: Live fetch with rate limiting
    allowed = await wait_for_rate_limit(source_name, max_wait=10.0)
    if not allowed:
        return None

    try:
        result = await fetcher()
    except Exception as e:
        print(f"[cache] fetch error for {cache_key}: {e}")
        return None

    if result is not None:
        cache_set(cache_key, result)
        if ttl_hours > 0:
            supabase_cache_set(cache_key, result, ttl_hours)

    return result


# ── Batch processor ───────────────────────────────────────────────────────────

async def batch_process(
    items:      list,
    processor:  Callable,
    batch_size: int = 10,
    delay_sec:  float = 0.5,
) -> list:
    """
    Process a list in small batches to stay within memory and rate limits.

    Args:
        items:      List to process.
        processor:  Async function that takes a list and returns a list.
        batch_size: Items per batch (default 10).
        delay_sec:  Sleep between batches (default 0.5s).

    Returns:
        Flattened results list.
    """
    results = []
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        try:
            batch_result = await processor(batch)
            if isinstance(batch_result, list):
                results.extend(batch_result)
            elif batch_result is not None:
                results.append(batch_result)
        except Exception as e:
            print(f"[batch] error processing batch {i//batch_size}: {e}")
        if i + batch_size < len(items):
            await asyncio.sleep(delay_sec)
    return results


# ── Status reporting ──────────────────────────────────────────────────────────

def rate_limit_status() -> dict:
    """Return current usage stats for all tracked sources."""
    today = datetime.now().strftime("%Y-%m-%d")
    status = {}
    for source, bucket in _buckets.items():
        limits = FREE_TIER_LIMITS.get(source, FREE_TIER_LIMITS["default"])
        daily_used = bucket["daily"] if bucket["day"] == today else 0
        status[source] = {
            "daily_used":  daily_used,
            "daily_limit": limits["per_day"] or "∞",
            "tokens":      round(bucket["tokens"], 2),
        }
    return status
