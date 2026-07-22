"""Weekly error report — aggregate history and optionally narrate with Claude."""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timedelta

from rich.panel import Panel

from . import output, _constants
from ._paths import HISTORY_FILE


def _load_recent(days: int = 7) -> list[dict]:
    """Load history entries from the last N days."""
    if not HISTORY_FILE.exists():
        return []
    cutoff = datetime.now() - timedelta(days=days)
    entries = []
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    ts = datetime.fromisoformat(e.get("timestamp", "2000-01-01"))
                    if ts >= cutoff:
                        entries.append(e)
                except (json.JSONDecodeError, ValueError):
                    pass
    except OSError:
        pass
    return entries


def _top_error_types(entries: list[dict], n: int = 5) -> list[tuple[str, int]]:
    from .utils import extract_error_type
    types = [extract_error_type(e.get("error", "")) or "unknown" for e in entries]
    return Counter(types).most_common(n)


def _busiest_hour(entries: list[dict]) -> str | None:
    if not entries:
        return None
    hours = Counter()
    for e in entries:
        try:
            h = datetime.fromisoformat(e["timestamp"]).hour
            hours[h] += 1
        except (KeyError, ValueError):
            pass
    if not hours:
        return None
    peak_h = hours.most_common(1)[0][0]
    return f"{peak_h:02d}:00–{peak_h:02d}:59"


def weekly_report() -> None:
    """Aggregate the last 7 days of history and print a rich weekly report."""
    entries = _load_recent(days=7)

    output.console.rule("[bold cyan]errex — Weekly Report[/bold cyan]")
    output.console.print()

    if not entries:
        output.console.print(Panel(
            "No history in the last 7 days.",
            title="Weekly Summary",
            expand=False,
        ))
        output.console.rule(style="dim")
        return

    total = len(entries)
    top_types = _top_error_types(entries, n=5)
    models_used = list(dict.fromkeys(e.get("model", "?") for e in entries))
    busiest = _busiest_hour(entries)

    stats_lines = [
        f"[bold]Total errors explained:[/bold]  {total}",
        "",
        "[bold]Top 5 error types:[/bold]",
    ]
    for etype, cnt in top_types:
        stats_lines.append(f"  {cnt:>4}×  {etype}")
    stats_lines += [
        "",
        f"[bold]Models used:[/bold]  {', '.join(models_used) or 'n/a'}",
        f"[bold]Busiest hour:[/bold]  {busiest or 'n/a'}",
    ]
    stats_text = "\n".join(stats_lines)

    output.console.print(Panel(stats_text, title="Last 7 Days", expand=False))
    output.console.print()

    # Optional Claude narrative
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        output.console.print("[dim]Generating narrative report with Claude…[/dim]\n")

        top_str = ", ".join(f"{t} ({c}x)" for t, c in top_types)
        prompt = (
            f"You are a DevOps assistant. Write a 3-paragraph weekly report for a developer "
            f"based on the following errex error statistics from the past 7 days.\n\n"
            f"Total errors: {total}\n"
            f"Top error types: {top_str}\n"
            f"Models used: {', '.join(models_used)}\n"
            f"Busiest hour: {busiest or 'unknown'}\n\n"
            f"Paragraph 1: summarize the week's error activity.\n"
            f"Paragraph 2: highlight the most common problems and what they suggest.\n"
            f"Paragraph 3: concrete recommendations to reduce errors next week.\n\n"
            f"Keep it professional and concise. Use plain text, no markdown headers."
        )
        from .core import call_claude
        _model = os.environ.get("ERREX_MODEL") or _constants.CONFIG_DEFAULTS["model"]
        call_claude("weekly report", model=_model, messages=[{"role": "user", "content": prompt}])
        print()

    output.console.rule(style="dim")
    output.console.print()
