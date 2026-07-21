"""Diff the current scan against the last auto-scan state."""
from __future__ import annotations

from pathlib import Path

from . import output
from .scan import run_scan, detect_platform
from .scanners._base import SEVERITIES
from .auto_scan import _load_last_findings

_STATE_FILE = Path.home() / ".errex_autoscan_state.json"


def scan_diff(severity: str | None = None) -> None:
    """
    Compare the current scan result to the previous state saved by auto_scan.

    Prints NEW findings (in current but not previous) and RESOLVED findings
    (in previous but not current).  If no previous state exists, all current
    findings are shown as new.
    """

    prev_ids = _load_last_findings(_STATE_FILE)

    output.console.print("[dim]Running current scan…[/dim]")
    plat = detect_platform()
    result = run_scan(plat, progress_cb=None)

    sev_idx = (
        SEVERITIES.index(severity)
        if severity and severity in SEVERITIES
        else len(SEVERITIES) - 1
    )
    current_findings = {
        f.id: f
        for f in result.findings
        if SEVERITIES.index(f.severity) <= sev_idx
    }
    current_ids = set(current_findings.keys())

    new_ids = current_ids - prev_ids
    resolved_ids = prev_ids - current_ids

    output.console.rule("[bold cyan]errex — Scan Diff[/bold cyan]")
    output.console.print()

    if not prev_ids:
        output.console.print(
            "[dim]No previous scan state found "
            f"({_STATE_FILE}) — showing all current findings as new.[/dim]\n"
        )
        if not current_findings:
            output.console.print("[green]✓ No findings.[/green]")
            output.console.rule(style="dim")
            return
        for fid, f in sorted(current_findings.items(), key=lambda kv: kv[1].severity_rank()):
            output.console.print(
                f"  [bold red]NEW[/bold red] [{f.severity.upper()}] {f.title}"
            )
            if f.detail:
                for line in f.detail.splitlines()[:2]:
                    output.console.print(f"    [dim]{line}[/dim]")
        output.console.print(
            f"\n[dim]{len(current_findings)} finding(s) total[/dim]"
        )
        output.console.rule(style="dim")
        return

    if new_ids:
        output.console.print(
            f"[bold red]{len(new_ids)} new finding(s):[/bold red]\n"
        )
        for fid in sorted(new_ids, key=lambda i: current_findings[i].severity_rank()):
            f = current_findings[fid]
            output.console.print(
                f"  [bold red]+[/bold red] [{f.severity.upper()}] {f.title}"
            )
            if f.detail:
                for line in f.detail.splitlines()[:2]:
                    output.console.print(f"    [dim]{line}[/dim]")
        output.console.print()
    else:
        output.console.print("[green]✓ No new findings since last scan.[/green]")

    if resolved_ids:
        output.console.print(
            f"[bold green]{len(resolved_ids)} resolved finding(s):[/bold green]\n"
        )
        for fid in sorted(resolved_ids):
            output.console.print(f"  [bold green]-[/bold green] {fid}")
        output.console.print()
    else:
        output.console.print("[dim]No findings resolved since last scan.[/dim]")

    output.console.print(
        f"\n[dim]Open: {len(current_ids)}  |  New: {len(new_ids)}  "
        f"|  Resolved: {len(resolved_ids)}[/dim]"
    )
    output.console.rule(style="dim")
