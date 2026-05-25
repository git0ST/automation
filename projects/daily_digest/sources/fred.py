"""
FRED (Federal Reserve Economic Data) — macro indicators.
No API key required for CSV downloads.
https://fred.stlouisfed.org/
"""

import asyncio
import httpx
from datetime import datetime

SERIES = {
    "FEDFUNDS": ("Fed Funds Rate",    "%",     "monthly"),
    "CPIAUCSL": ("CPI (YoY proxy)",   "index", "monthly"),
    "UNRATE":   ("Unemployment Rate", "%",     "monthly"),
    "T10Y2Y":   ("10Y-2Y Spread",     "pct",   "daily"),
    "VIXCLS":   ("VIX",               "index", "daily"),
    "GDPC1":    ("Real GDP",          "bil$",  "quarterly"),
    "DGS10":    ("10Y Treasury",      "%",     "daily"),
}

BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"


async def _fetch_series(client: httpx.AsyncClient, sid: str) -> dict | None:
    try:
        r = await client.get(BASE, params={"id": sid}, timeout=10)
        if r.status_code != 200:
            return None
        lines = r.text.strip().split("\n")
        # last non-empty line with a numeric value
        for line in reversed(lines[1:]):
            parts = line.split(",")
            if len(parts) == 2 and parts[1].strip() not in ("", "."):
                return {
                    "series_id": sid,
                    "name":      SERIES[sid][0],
                    "value":     float(parts[1].strip()),
                    "unit":      SERIES[sid][1],
                    "period":    parts[0].strip(),
                }
    except Exception:
        return None


async def fetch_fred(limit: int = 20) -> list[dict]:
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[_fetch_series(client, sid) for sid in SERIES],
            return_exceptions=True,
        )

    items = []
    for r in results:
        if not isinstance(r, dict):
            continue
        items.append({
            "id":      f"macro-{r['series_id']}",
            "source":  "macro",
            "title":   f"{r['name']}: {r['value']:.2f}{r['unit']}  [{r['period']}]",
            "url":     f"https://fred.stlouisfed.org/series/{r['series_id']}",
            "score":   0,
            "preview": f"FRED series {r['series_id']} · latest value {r['value']:.4f} ({r['period']})",
            "meta":    "Macro · FRED",
            "tags":    ["macro", "economics"],
            "sector":  "macro",
            "macro_data": r,
        })
    return items
