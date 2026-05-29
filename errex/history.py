from __future__ import annotations

import json
import sys
from datetime import datetime
from collections import Counter

from ._paths import HISTORY_FILE
from . import output, _constants
from .utils import extract_error_type, _parse_since, _error_fingerprint


def save_history(error_text: str, explanation: str, model: str, brief: bool, name: str | None = None) -> None:
    entry = {
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "brief": brief,
        "error": error_text[:200],
        "explanation": explanation,
    }
    if name:
        entry["name"] = name
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def show_history(search: str | None, since: str | None = None, filter_type: str | None = None) -> None:
    """Print past explanations from the history file."""
    from rich.markdown import Markdown
    if not HISTORY_FILE.exists():
        output.console.print("[yellow]No history yet.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if since:
        cutoff = _parse_since(since)
        entries = [
            e for e in entries
            if datetime.fromisoformat(e["timestamp"]) >= cutoff
        ]

    if filter_type:
        ft = filter_type.lower()
        entries = [
            e for e in entries
            if ft in extract_error_type(e.get("error", "")).lower()
            or ft in e.get("error", "").lower()
        ]

    if search:
        entries = [
            e for e in entries
            if search.lower() in e.get("error", "").lower()
            or search.lower() in e.get("explanation", "").lower()
        ]

    if not entries:
        output.console.print("[yellow]No matching history entries.[/yellow]")
        sys.exit(0)

    for entry in entries:
        label = f"  {entry['timestamp'][:19]}  |  {entry['model']}{'  |  brief' if entry.get('brief') else ''}"
        output.console.rule(label, style="dim")
        output.console.print(f"[bold red]Error:[/bold red] {entry['error'][:80]}{'...' if len(entry['error']) > 80 else ''}\n")
        output.console.print(Markdown(entry["explanation"]))
        output.console.print()


def show_recent(n: int, since: str | None = None, filter_type: str | None = None) -> None:
    """Show the N most recent history entries."""
    from rich.markdown import Markdown
    if not HISTORY_FILE.exists():
        output.console.print("[yellow]No history yet.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        output.console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    if since:
        cutoff = _parse_since(since)
        entries = [e for e in entries if datetime.fromisoformat(e["timestamp"]) >= cutoff]

    if filter_type:
        ft = filter_type.lower()
        entries = [
            e for e in entries
            if ft in extract_error_type(e.get("error", "")).lower()
            or ft in e.get("error", "").lower()
        ]

    recent = entries[-n:]
    label = f"Last {len(recent)} explanation{'s' if len(recent) != 1 else ''}"
    output.console.rule(f"[bold cyan]errex — {label}[/bold cyan]")
    output.console.print()

    for entry in recent:
        meta = f"  {entry['timestamp'][:19]}  ·  {entry['model']}{'  ·  brief' if entry.get('brief') else ''}"
        output.console.rule(meta, style="dim")
        output.console.print(f"[bold red]Error:[/bold red] {entry['error'][:80]}{'...' if len(entry['error']) > 80 else ''}\n")
        output.console.print(Markdown(entry["explanation"]))
        output.console.print()


def find_similar(error_text: str, top_n: int = 5) -> None:
    """Search history for past errors similar to the current one."""
    from rich.markdown import Markdown
    if not HISTORY_FILE.exists():
        output.console.print("[yellow]No history yet.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        output.console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    current_fp = _error_fingerprint(error_text)
    current_words = set(current_fp.lower().split())

    def jaccard(entry: dict) -> float:
        fp = _error_fingerprint(entry.get("error", ""))
        words = set(fp.lower().split())
        if not current_words or not words:
            return 0.0
        return len(current_words & words) / len(current_words | words)

    scored = sorted(((jaccard(e), e) for e in entries), reverse=True, key=lambda x: x[0])
    top = [(s, e) for s, e in scored if s > 0.0][:top_n]

    if not top:
        output.console.print("[yellow]No similar errors found in history.[/yellow]")
        return

    output.console.rule("[bold cyan]errex — Similar Past Errors[/bold cyan]")
    output.console.print(f"[dim]Matched {len(top)} result(s) from history[/dim]\n")
    for score, entry in top:
        label = f"  {entry['timestamp'][:19]}  ·  {entry['model']}  ·  {score:.0%} match"
        output.console.rule(label, style="dim")
        output.console.print(f"[bold red]Error:[/bold red] {entry['error'][:80]}{'...' if len(entry['error']) > 80 else ''}\n")
        output.console.print(Markdown(entry["explanation"]))
        output.console.print()


def clear_history(before_days: int | None) -> None:
    """Delete all or old history entries with a confirmation prompt."""
    if not HISTORY_FILE.exists():
        output.console.print("[yellow]No history to clear.[/yellow]")
        return

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        output.console.print("[yellow]History is already empty.[/yellow]")
        return

    pinned = [e for e in entries if e.get("pinned")]

    if before_days is not None:
        cutoff = datetime.now().timestamp() - before_days * 86400
        to_keep, to_delete = [], []
        for e in entries:
            if e.get("pinned"):
                to_keep.append(e)
                continue
            try:
                ts = datetime.fromisoformat(e["timestamp"]).timestamp()
                (to_delete if ts < cutoff else to_keep).append(e)
            except (KeyError, ValueError):
                to_keep.append(e)

        if not to_delete:
            output.console.print(f"[yellow]No entries older than {before_days} days.[/yellow]")
            return

        s = "y" if len(to_delete) == 1 else "ies"
        pin_note = f"  [dim]({len(pinned)} pinned entr{'y' if len(pinned) == 1 else 'ies'} kept)[/dim]" if pinned else ""
        output.console.print(f"This will delete [bold]{len(to_delete)}[/bold] entr{s} older than {before_days} days. [dim]({len(to_keep)} will remain)[/dim]{pin_note}")
        try:
            ans = input("Proceed? [y/N]: ").strip().lower()
        except KeyboardInterrupt:
            output.console.print("\n[dim]Cancelled.[/dim]")
            return
        if ans != "y":
            output.console.print("[dim]Cancelled.[/dim]")
            return
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            for e in to_keep:
                f.write(json.dumps(e) + "\n")
        output.console.print(f"[green]Deleted {len(to_delete)} old entr{s}.[/green]")
    else:
        deletable = [e for e in entries if not e.get("pinned")]
        s = "y" if len(deletable) == 1 else "ies"
        pin_note = f"  [dim]({len(pinned)} pinned entr{'y' if len(pinned) == 1 else 'ies'} will be kept)[/dim]" if pinned else ""
        output.console.print(f"This will permanently delete [bold]{len(deletable)}[/bold] history entr{s}.{pin_note}")
        try:
            ans = input("Proceed? [y/N]: ").strip().lower()
        except KeyboardInterrupt:
            output.console.print("\n[dim]Cancelled.[/dim]")
            return
        if ans != "y":
            output.console.print("[dim]Cancelled.[/dim]")
            return
        if pinned:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                for e in pinned:
                    f.write(json.dumps(e) + "\n")
        else:
            HISTORY_FILE.unlink()
        output.console.print(f"[green]Cleared {len(deletable)} history entr{s}.[/green]")


def export_history(output_path: str, fmt: str) -> None:
    """Export history to an HTML or Markdown file."""
    from pathlib import Path
    if not HISTORY_FILE.exists():
        output.console.print("[yellow]No history to export.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        output.console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    if fmt == "html":
        lines = ["""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>errex history</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
  body { font-family: -apple-system, sans-serif; max-width: 860px; margin: 2rem auto; padding: 0 1rem; background: #0f1117; color: #e2e8f0; }
  h1 { color: #7dd3fc; } .entry { border: 1px solid #2d3748; border-radius: 8px; padding: 1.25rem; margin: 1.5rem 0; }
  .meta { color: #64748b; font-size: 0.85rem; margin-bottom: 0.75rem; }
  .error-block { background: #1e2130; border-radius: 6px; padding: 0.75rem; font-family: monospace; font-size: 0.85rem; color: #f87171; white-space: pre-wrap; margin-bottom: 1rem; }
  .explanation { line-height: 1.7; } h2,h3 { color: #7dd3fc; } code { background: #1e2130; padding: 0.1em 0.4em; border-radius: 4px; color: #86efac; }
  pre { background: #1e2130; padding: 1rem; border-radius: 6px; overflow-x: auto; }
</style>
</head><body>
<h1>errex — Export</h1>"""]
        for e in entries:
            ts = e.get("timestamp", "")[:19]
            model = e.get("model", "")
            brief = " · brief" if e.get("brief") else ""
            error = e.get("error", "")
            explanation = e.get("explanation", "")
            lines.append(f"""<div class="entry">
  <div class="meta">{ts} · {model}{brief}</div>
  <div class="error-block">{error}</div>
  <div class="explanation" data-md="{explanation.replace('"', '&quot;')}"></div>
</div>""")
        lines.append("""<script>
  document.querySelectorAll('[data-md]').forEach(el => {
    el.innerHTML = marked.parse(el.dataset.md);
  });
</script></body></html>""")
        content = "\n".join(lines)

    else:  # markdown
        md_parts = ["# errex History\n"]
        for e in entries:
            ts = e.get("timestamp", "")[:19]
            model = e.get("model", "")
            brief = " · brief" if e.get("brief") else ""
            error = e.get("error", "")
            explanation = e.get("explanation", "")
            md_parts.append(f"---\n\n**{ts}** · {model}{brief}\n\n**Error:**\n```\n{error}\n```\n\n{explanation}\n")
        content = "\n".join(md_parts)

    out = Path(output_path)
    out.write_text(content, encoding="utf-8")
    output.console.print(f"[green]Exported {len(entries)} entries to[/green] [cyan]{out.resolve()}[/cyan]")


def show_stats() -> None:
    """Print usage statistics from ~/.errex_history."""
    from rich.table import Table
    from rich.panel import Panel
    from rich.columns import Columns
    from rich.markdown import Markdown
    if not HISTORY_FILE.exists():
        output.console.print("[yellow]No history yet — run errex on some errors first.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        output.console.print("[yellow]History file is empty.[/yellow]")
        sys.exit(0)

    total = len(entries)
    brief_count = sum(1 for e in entries if e.get("brief"))
    models = Counter(e.get("model", "unknown") for e in entries)
    error_types = Counter(extract_error_type(e.get("error", "")) for e in entries)
    days = Counter(e["timestamp"][:10] for e in entries if "timestamp" in e)
    hours = Counter(int(e["timestamp"][11:13]) for e in entries if "timestamp" in e)
    ratings = [e["rating"] for e in entries if "rating" in e]

    busiest_day = max(days, key=days.get) if days else "—"
    busiest_hour = max(hours, key=hours.get) if hours else 0
    first_used = min(e["timestamp"][:10] for e in entries if "timestamp" in e)
    avg_rating = f"{sum(ratings)/len(ratings):.1f}/5 ({len(ratings)} rated)" if ratings else "none yet"

    output.console.rule("[bold cyan]errex — Usage Stats[/bold cyan]")
    output.console.print()

    # Summary panel
    summary = (
        f"[bold]{total}[/bold] total explanations\n"
        f"[bold]{brief_count}[/bold] brief  /  [bold]{total - brief_count}[/bold] full\n"
        f"Avg rating: [dim]{avg_rating}[/dim]\n"
        f"First used: [dim]{first_used}[/dim]\n"
        f"Busiest day: [dim]{busiest_day} ({days.get(busiest_day, 0)} runs)[/dim]\n"
        f"Busiest hour: [dim]{busiest_hour:02d}:00–{busiest_hour:02d}:59[/dim]"
    )
    output.console.print(Panel(summary, title="Overview", border_style="cyan"))
    output.console.print()

    # Models table
    model_table = Table(title="Models used", show_header=True, header_style="bold magenta")
    model_table.add_column("Model", style="cyan")
    model_table.add_column("Count", justify="right")
    model_table.add_column("Share", justify="right")
    for model, count in models.most_common():
        model_table.add_row(model, str(count), f"{count/total*100:.0f}%")

    # Error types table
    type_table = Table(title="Top error types", show_header=True, header_style="bold magenta")
    type_table.add_column("Error type", style="red")
    type_table.add_column("Count", justify="right")
    for etype, count in error_types.most_common(8):
        type_table.add_row(etype, str(count))

    output.console.print(Columns([model_table, type_table], equal=False, expand=False))
    output.console.print()


def interactive_history(n: int = 15) -> None:
    """Show a numbered list of recent history entries; pick one to view."""
    from rich.table import Table
    from rich.markdown import Markdown
    if not HISTORY_FILE.exists():
        output.console.print("[yellow]No history yet.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        output.console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    recent = entries[-n:]

    output.console.rule("[bold cyan]errex — Interactive History[/bold cyan]")
    output.console.print()

    table = Table(show_header=True, header_style="bold magenta", box=None, show_edge=False)
    table.add_column("#", style="dim", width=3)
    table.add_column("Date", style="dim", width=17)
    table.add_column("Model", style="dim", width=22)
    table.add_column("Error", style="red")

    for i, entry in enumerate(recent, 1):
        ts = entry.get("timestamp", "")[:16]
        model = entry.get("model", "")
        error = entry.get("error", "")[:65]
        name_tag = f"[{entry['name']}] " if entry.get("name") else ""
        table.add_row(str(i), ts, model, f"{name_tag}{error}")

    output.console.print(table)
    output.console.print()

    try:
        choice = input(f"Pick an entry (1–{len(recent)}, or q to quit): ").strip()
    except (EOFError, KeyboardInterrupt):
        output.console.print("\n[dim]Cancelled.[/dim]")
        return

    if choice.lower() in ("q", ""):
        return

    try:
        idx = int(choice) - 1
        if not 0 <= idx < len(recent):
            output.console.print("[red]Invalid choice.[/red]")
            return
    except ValueError:
        output.console.print("[red]Invalid input.[/red]")
        return

    entry = recent[idx]
    output.console.print()
    label = f"  {entry['timestamp'][:19]}  ·  {entry['model']}{'  ·  brief' if entry.get('brief') else ''}"
    output.console.rule(label, style="dim")
    output.console.print(f"\n[bold red]Error:[/bold red] {entry['error']}\n")
    if entry.get("notes"):
        output.console.print(f"[dim]Note:[/dim] {entry['notes']}\n")
    output.console.print(Markdown(entry["explanation"]))
    output.console.print()


def rate_last(score: int) -> None:
    """Rate the last history entry 1-5 and store the rating."""
    if not 1 <= score <= 5:
        output.err_console.print("[red]errex: --rate expects a score between 1 and 5[/red]")
        sys.exit(1)

    if not HISTORY_FILE.exists():
        output.console.print("[yellow]No history to rate.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        lines = [l for l in f.readlines() if l.strip()]

    if not lines:
        output.console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    last = json.loads(lines[-1])
    last["rating"] = score
    lines[-1] = json.dumps(last) + "\n"

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)

    stars = "★" * score + "☆" * (5 - score)
    err_snippet = last.get("error", "")[:60]
    output.console.print(f"[green]Rated[/green] {stars} ({score}/5)  [dim]{err_snippet}[/dim]")


def add_note(note: str) -> None:
    """Append a personal note to the last history entry."""
    if not HISTORY_FILE.exists():
        output.console.print("[yellow]No history yet.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        lines = [l for l in f.readlines() if l.strip()]

    if not lines:
        output.console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    last = json.loads(lines[-1])
    existing = last.get("notes", "")
    last["notes"] = (existing + "\n" + note).strip() if existing else note
    lines[-1] = json.dumps(last) + "\n"

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)

    err_snippet = last.get("error", "")[:60]
    output.console.print(f"[green]Note added[/green]  [dim]{err_snippet}[/dim]")
    output.console.print(f"[dim]Note:[/dim] {note}")


def find_by_name(name: str) -> None:
    """Find history entries saved with --save-as NAME."""
    from rich.markdown import Markdown
    if not HISTORY_FILE.exists():
        output.console.print("[yellow]No history yet.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    matches = [e for e in entries if e.get("name", "").lower() == name.lower()]

    if not matches:
        output.console.print(f"[yellow]No entries found with name '{name}'.[/yellow]")
        output.console.print("[dim]Tip: save an explanation with: errex --save-as NAME[/dim]")
        sys.exit(0)

    output.console.rule(f"[bold cyan]errex — Saved: {name}[/bold cyan]")
    output.console.print(f"[dim]{len(matches)} entry{'s' if len(matches) != 1 else ''} found[/dim]\n")
    for entry in matches:
        label = f"  {entry['timestamp'][:19]}  ·  {entry['model']}"
        output.console.rule(label, style="dim")
        output.console.print(f"[bold red]Error:[/bold red] {entry['error'][:80]}{'...' if len(entry['error']) > 80 else ''}\n")
        output.console.print(Markdown(entry["explanation"]))
        output.console.print()


def list_named() -> None:
    """List all history entries saved with --save-as."""
    from rich.table import Table
    if not HISTORY_FILE.exists():
        output.console.print("[yellow]No history yet.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    named = [e for e in entries if e.get("name")]

    if not named:
        output.console.print("[yellow]No named entries yet.[/yellow]")
        output.console.print("[dim]Save an explanation with: errex --save-as NAME[/dim]")
        return

    output.console.rule("[bold cyan]errex — Named Entries[/bold cyan]")
    output.console.print(f"[dim]{len(named)} saved entr{'y' if len(named) == 1 else 'ies'}[/dim]\n")

    table = Table(show_header=True, header_style="bold magenta", box=None, show_edge=False)
    table.add_column("Name", style="cyan", min_width=15)
    table.add_column("Date", style="dim", width=17)
    table.add_column("Model", style="dim", width=22)
    table.add_column("Error", style="red")

    for entry in named:
        ts = entry.get("timestamp", "")[:16]
        model = entry.get("model", "")
        error = entry.get("error", "")[:60]
        table.add_row(entry["name"], ts, model, error)

    output.console.print(table)
    output.console.print(f"\n[dim]Retrieve with: errex --find-name NAME[/dim]")


def export_csv(output_path: str) -> None:
    """Export history to a CSV file."""
    import csv
    from pathlib import Path

    if not HISTORY_FILE.exists():
        output.console.print("[yellow]No history to export.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        output.console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    fields = ["timestamp", "model", "error_type", "error", "explanation_length", "rating", "name", "pinned"]
    out = Path(output_path)
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for e in entries:
            writer.writerow({
                "timestamp": e.get("timestamp", "")[:19],
                "model": e.get("model", ""),
                "error_type": extract_error_type(e.get("error", "")),
                "error": e.get("error", "")[:120].replace("\n", " "),
                "explanation_length": len(e.get("explanation", "")),
                "rating": e.get("rating", ""),
                "name": e.get("name", ""),
                "pinned": e.get("pinned", False),
            })

    output.console.print(f"[green]Exported {len(entries)} entries to[/green] [cyan]{out.resolve()}[/cyan]")
    output.console.print(f"[dim]Columns: {', '.join(fields)}[/dim]")


def search_history(term: str) -> None:
    """Full-text search across all history fields: error, explanation, name, notes, model."""
    from rich.markdown import Markdown
    if not HISTORY_FILE.exists():
        output.console.print("[yellow]No history yet.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        output.console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    t = term.lower()

    def _hit_fields(e: dict) -> list:
        hits = []
        for field in ("error", "explanation", "name", "notes"):
            if t in e.get(field, "").lower():
                hits.append(field)
        if t in e.get("model", "").lower():
            hits.append("model")
        if t in extract_error_type(e.get("error", "")).lower():
            hits.append("error_type")
        return hits

    matches = [(e, _hit_fields(e)) for e in entries]
    matches = [(e, fields) for e, fields in matches if fields]

    if not matches:
        output.console.print(f"[yellow]No history entries matching '{term}'.[/yellow]")
        sys.exit(0)

    output.console.rule(f"[bold cyan]errex — Search: {term}[/bold cyan]")
    output.console.print(f"[dim]{len(matches)} result{'s' if len(matches) != 1 else ''} across {len(entries)} entries[/dim]\n")

    for entry, fields in matches:
        ts = entry.get("timestamp", "")[:16]
        model = entry.get("model", "")
        error = entry.get("error", "")
        explanation = entry.get("explanation", "")
        name = entry.get("name", "")
        notes = entry.get("notes", "")

        field_tag = ", ".join(fields)
        output.console.rule(f"  {ts}  ·  {model}  ·  matched: {field_tag}", style="dim")
        if name:
            output.console.print(f"[dim]Name:[/dim] [cyan]{name}[/cyan]")
        output.console.print(f"[bold red]Error:[/bold red] {error[:80]}{'...' if len(error) > 80 else ''}")
        if notes:
            output.console.print(f"[dim]Note:[/dim] {notes[:80]}")
        output.console.print()
        output.console.print(Markdown(explanation))
        output.console.print()


def dedup_history() -> None:
    """Scan history and group near-duplicate errors into clusters."""
    if not HISTORY_FILE.exists():
        output.console.print("[yellow]No history yet.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        output.console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    groups: dict = {}
    for e in entries:
        fp = _error_fingerprint(e.get("error", ""))
        groups.setdefault(fp, []).append(e)

    dupes = [(fp, members) for fp, members in groups.items() if len(members) > 1]
    dupes.sort(key=lambda x: len(x[1]), reverse=True)

    unique_count = len(groups)
    dupe_count = sum(len(m) - 1 for _, m in dupes)

    output.console.rule("[bold cyan]errex — Dedup Report[/bold cyan]")
    output.console.print(
        f"[dim]{len(entries)} total entries · {unique_count} distinct fingerprints · "
        f"{dupe_count} duplicate{'s' if dupe_count != 1 else ''}[/dim]\n"
    )

    if not dupes:
        output.console.print("[green]No duplicate errors found — all history entries are unique.[/green]")
        return

    for _fp, members in dupes:
        representative = members[-1]
        ts_first = members[0].get("timestamp", "")[:10]
        ts_last = members[-1].get("timestamp", "")[:10]
        error = representative.get("error", "")
        models_used = sorted(set(m.get("model", "") for m in members))
        output.console.print(
            f"[bold red]{len(members)}×[/bold red]  {error[:70]}{'...' if len(error) > 70 else ''}"
        )
        output.console.print(
            f"  [dim]first: {ts_first} · last: {ts_last} · models: {', '.join(models_used)}[/dim]"
        )
        output.console.print()

    output.console.print("[dim]Tip: use [cyan]errex --clear-history DAYS[/cyan] to prune old duplicates.[/dim]")


def show_last() -> None:
    """Print the last history entry without re-running Claude."""
    from rich.markdown import Markdown
    if not HISTORY_FILE.exists():
        output.console.print("[yellow]No history yet.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        output.console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    e = entries[-1]
    ts = e.get("timestamp", "")[:19]
    model = e.get("model", "")
    error = e.get("error", "")
    explanation = e.get("explanation", "")
    name = e.get("name", "")
    notes = e.get("notes", "")
    rating = e.get("rating")
    pinned = e.get("pinned", False)

    brief_tag = "  · brief" if e.get("brief") else ""
    name_tag = f"  · [cyan]{name}[/cyan]" if name else ""
    pin_tag = "  · [yellow]pinned[/yellow]" if pinned else ""
    output.console.rule("[bold cyan]errex — Last Explanation[/bold cyan]")
    output.console.print(f"[dim]{ts}  ·  {model}{brief_tag}[/dim]{name_tag}{pin_tag}\n")
    output.console.print(f"[bold red]Error:[/bold red] {error}\n")
    if notes:
        output.console.print(f"[dim]Note:[/dim] {notes}\n")
    if rating:
        stars = "★" * rating + "☆" * (5 - rating)
        output.console.print(f"[dim]Rating:[/dim] {stars}\n")
    output.console.print(Markdown(explanation))
    output.console.rule(style="dim")


def pin_entry(pin: bool) -> None:
    """Pin or unpin the last history entry."""
    if not HISTORY_FILE.exists():
        output.console.print("[yellow]No history yet.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        lines = [ln for ln in f.readlines() if ln.strip()]

    if not lines:
        output.console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    last = json.loads(lines[-1])
    last["pinned"] = pin
    lines[-1] = json.dumps(last) + "\n"

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)

    err_snippet = last.get("error", "")[:60]
    if pin:
        output.console.print(f"[green]Pinned[/green] [dim](protected from --clear-history)[/dim]  [dim]{err_snippet}[/dim]")
    else:
        output.console.print(f"[dim]Unpinned[/dim]  [dim]{err_snippet}[/dim]")
