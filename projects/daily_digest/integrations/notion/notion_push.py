"""
Intelligence Terminal — Notion push orchestrator.

Usage:
    bash run.sh notion                          # full run, all sources
    bash run.sh notion --summarize              # + Ollama AI analysis & briefing
    bash run.sh notion --sources hn,arxiv       # specific sources
    bash run.sh notion --limit 20               # items per source (default 15)
    bash run.sh notion --no-market              # skip finance/market fetch
    bash run.sh notion --no-header              # skip terminal header refresh
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

import argparse
import asyncio
import os
from datetime import datetime

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich import box

load_dotenv(ROOT / ".env")

from sources import ALL_SOURCES as _ALL_SOURCES
from agents.pipeline import run_pipeline
from notion_sync import (
    get_client,
    find_or_create_database,
    refresh_terminal_header,
    push_items_to_notion,
    update_daily_brief,
)

console = Console()

SOURCE_ALIASES = {
    "hn": "hackernews", "hacker": "hackernews", "hackernews": "hackernews",
    "arxiv": "arxiv",   "reddit": "reddit",
    "github": "github", "gh": "github",
    "rss": "rss",       "finance": "finance", "fin": "finance",
    "so": "stackoverflow", "stackoverflow": "stackoverflow",
}

ALL_SOURCES = _ALL_SOURCES  # from sources/__init__.py


def _print_banner(sources: list[str], run_ai: bool):
    tod = datetime.now().strftime("%H:%M")
    mode = "🤖 AI MODE" if run_ai else "⚡ FAST MODE"
    console.rule(f"[bold cyan]📡 INTELLIGENCE TERMINAL  ·  {tod}  ·  {mode}[/bold cyan]")
    console.print(f"[dim]Sources: {', '.join(sources)}[/dim]\n")


def _print_results(result: dict, push_stats: dict):
    meta  = result["run_meta"]
    table = Table(box=box.ROUNDED, title="Terminal Run Summary", show_header=True,
                  header_style="bold cyan")
    table.add_column("Source",  style="bold")
    table.add_column("Fetched", justify="right")
    table.add_column("Status",  justify="right")

    counts = {}
    for item in result["items"]:
        counts[item["source"]] = counts.get(item["source"], 0) + 1

    for src, n in sorted(counts.items()):
        status = result["fetch_stats"].get(src, "")
        table.add_row(src.capitalize(), str(n), status)

    console.print(table)
    console.print(
        f"\n[bold green]✓ Created:[/bold green] {push_stats['created']}  "
        f"[yellow]Skipped:[/yellow] {push_stats['skipped']}  "
        f"[red]Errors:[/red] {push_stats['errors']}  "
        f"[dim]({meta['total_clean']} items after dedup)[/dim]"
    )


def main():
    parser = argparse.ArgumentParser(description="Intelligence Terminal → Notion")
    parser.add_argument("--sources",    default="all",
                        help="Comma-separated: hn,arxiv,reddit,github,rss,finance,so  or 'all'")
    parser.add_argument("--limit",      type=int, default=15,  help="Items per source")
    parser.add_argument("--summarize",  action="store_true",   help="Run Ollama AI analysis + briefing")
    parser.add_argument("--no-market",  action="store_true",   help="Skip market/finance fetch")
    parser.add_argument("--no-header",  action="store_true",   help="Skip terminal header refresh")
    args = parser.parse_args()

    # ── Resolve sources ───────────────────────────────────────────────────────
    if args.sources == "all":
        sources = list(ALL_SOURCES)
    else:
        sources = [SOURCE_ALIASES.get(s.strip(), s.strip()) for s in args.sources.split(",")]

    if args.no_market and "finance" in sources:
        sources.remove("finance")

    # ── Env check ─────────────────────────────────────────────────────────────
    for var, hint in [
        ("NOTION_TOKEN",   "Get from notion.so/my-integrations"),
        ("NOTION_PAGE_ID", "32-char ID from your Notion dashboard URL"),
    ]:
        if not os.getenv(var):
            console.print(f"[red]✗ {var} not set in .env — {hint}[/red]")
            sys.exit(1)

    parent_page_id = (os.getenv("NOTION_PAGE_ID") or "").split("/")[-1].split("?")[0].replace("-", "")
    _print_banner(sources, args.summarize)

    client = get_client()

    # ── 1. Database ───────────────────────────────────────────────────────────
    with console.status("Connecting to Notion database…"):
        db_id = find_or_create_database(client, parent_page_id)
    console.print(f"[green]✓[/green] Database: {db_id[:8]}…\n")

    # ── 2. Multi-agent pipeline ───────────────────────────────────────────────
    console.print("[bold]Running intelligence pipeline…[/bold]")
    limits = {src: args.limit for src in sources}
    limits["finance"]       = 20   # always get full market snapshot
    limits["stackoverflow"] = 12   # SO hot questions

    result = asyncio.run(run_pipeline(
        sources=sources,
        limits=limits,
        run_ai=args.summarize,
    ))

    items       = result["items"]
    market_data = result["market_data"]
    briefing    = result["briefing"]
    trends      = result["trends"]
    meta        = result["run_meta"]

    console.print(f"\n[bold]{meta['total_clean']} items after pipeline filtering[/bold]")
    for src, status in result["fetch_stats"].items():
        icon = "✓" if "ERROR" not in status else "⚠"
        color = "green" if "ERROR" not in status else "yellow"
        console.print(f"  [{color}]{icon}[/{color}] {src}: {status}")

    if not items:
        console.print("[yellow]\nNo items fetched. Check your network.[/yellow]")
        return

    # ── 3. Push articles to database ─────────────────────────────────────────
    console.print(f"\n[bold]Pushing to Notion database…[/bold]")
    push_stats = push_items_to_notion(client, db_id, items)

    # ── 4. Refresh terminal header ────────────────────────────────────────────
    if not args.no_header:
        with console.status("Refreshing terminal header…"):
            try:
                refresh_terminal_header(
                    client=client,
                    parent_page_id=parent_page_id,
                    meta=meta,
                    market_data=market_data,
                    briefing=briefing,
                    trends=trends,
                    items=items,
                    total_db=push_stats["created"] + push_stats["skipped"],
                )
                console.print("[green]✓[/green] Terminal header refreshed")
            except Exception as e:
                console.print(f"[yellow]⚠ Header skipped: {e}[/yellow]")

    # ── 5. Update daily brief sub-page ────────────────────────────────────────
    if push_stats["created"] > 0:
        with console.status("Updating daily brief…"):
            try:
                update_daily_brief(client, parent_page_id, items, push_stats, briefing)
                console.print("[green]✓[/green] Daily brief updated")
            except Exception as e:
                console.print(f"[yellow]⚠ Brief skipped: {e}[/yellow]")

    # ── 6. Summary ────────────────────────────────────────────────────────────
    console.print()
    _print_results(result, push_stats)

    if briefing:
        console.print(f"\n[bold cyan]📰 BRIEFING:[/bold cyan]")
        console.print(f"[dim]{briefing[:300]}{'…' if len(briefing) > 300 else ''}[/dim]")

    console.print(f"\n[dim]Open terminal → https://notion.so/{parent_page_id}[/dim]")


if __name__ == "__main__":
    main()
