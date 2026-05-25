"""
FINRA Short Sale Volume — institutional short pressure intelligence.

FINRA publishes daily short-sale volume data for all exchange-listed stocks.
This is the same data sold by premium vendors for $200-500/mo.

Source: https://www.finra.org/investors/learn-to-invest/advanced-investing/short-selling/regsho/daily-short-sale-volume-files
Updates: Daily (T+1), free, no API key.

Signals:
  - Short volume > 45% of total volume → elevated short pressure
  - Short volume > 60% → aggressive institutional short
  - Spike vs 20-day average → directional institutional bet
"""

import httpx
import csv
import io
from datetime import datetime, date, timedelta

BASE = "https://cdn.finra.org/equity/regsho/daily"
WATCHLIST = [
    "NVDA", "AAPL", "MSFT", "TSLA", "META", "GOOGL", "AMZN",
    "AMD", "SPY", "QQQ", "NFLX", "CRM", "INTC", "PLTR",
]

HEADERS = {"User-Agent": "IntelligenceTerminal/2.0 contact@intl.local"}


def _get_filename(d: date) -> str:
    # FINRA file format: CNMSshvol{YYYYMMDD}.txt
    return f"CNMSshvol{d.strftime('%Y%m%d')}.txt"


async def fetch_finra_short(limit: int = 20) -> list[dict]:
    items = []
    # Try last 3 trading days (skip weekends)
    checked = 0
    d = date.today() - timedelta(days=1)
    while checked < 5:
        if d.weekday() < 5:  # Mon–Fri
            items = await _fetch_day(d, limit)
            if items:
                break
            checked += 1
        d -= timedelta(days=1)
    return items[:limit]


async def _fetch_day(target: date, limit: int) -> list[dict]:
    url = f"{BASE}/{_get_filename(target)}"
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return []
            return _parse_finra(r.text, target, limit)
    except Exception:
        return []


def _parse_finra(text: str, report_date: date, limit: int) -> list[dict]:
    items = []
    try:
        reader = csv.DictReader(io.StringIO(text), delimiter="|")
        rows = {row.get("Symbol", ""): row for row in reader}

        for ticker in WATCHLIST:
            if ticker not in rows:
                continue
            row = rows[ticker]
            try:
                short_vol = int(row.get("ShortVolume", 0) or 0)
                total_vol = int(row.get("TotalVolume", 0) or 0)
                if total_vol == 0:
                    continue
                short_pct = round(short_vol / total_vol * 100, 1)

                if short_pct < 40:
                    continue  # Not noteworthy

                label = "neutral"
                direction = "neutral"
                if short_pct >= 60:
                    label = "aggressive-short"
                    direction = "bearish"
                elif short_pct >= 50:
                    label = "elevated-short"
                    direction = "bearish"
                elif short_pct >= 45:
                    label = "moderate-short"
                    direction = "bearish"

                items.append({
                    "id":              f"finra-{ticker}-{report_date.isoformat()}",
                    "source":         "finra",
                    "title":          f"[SHORT FLOW] {ticker}: {short_pct}% short volume ({label.replace('-', ' ')})",
                    "url":            f"https://www.finra.org/investors/learn-to-invest/advanced-investing/short-selling",
                    "score":          int(short_pct),
                    "preview":        (
                        f"{ticker} short volume: {short_vol:,} / {total_vol:,} total "
                        f"({short_pct}%) on {report_date.isoformat()}. "
                        f"FINRA RegSHO daily filing."
                    ),
                    "meta":           f"FINRA RegSHO · {report_date.isoformat()}",
                    "tags":           ["short-interest", "finra", "institutional", ticker.lower()],
                    "sector":         "finance",
                    "sentiment_label": direction,
                    "sentiment_score": -round(short_pct / 100, 3),
                    "entities":       [ticker],
                    "short_data": {
                        "ticker":     ticker,
                        "short_vol":  short_vol,
                        "total_vol":  total_vol,
                        "short_pct":  short_pct,
                        "label":      label,
                        "date":       report_date.isoformat(),
                    },
                })
            except (ValueError, TypeError):
                continue
    except Exception:
        pass
    # Sort by short_pct descending
    items.sort(key=lambda x: x.get("short_data", {}).get("short_pct", 0), reverse=True)
    return items[:limit]
