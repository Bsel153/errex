"""First-run detection — trigger an automatic scan on first invocation."""
from __future__ import annotations
from pathlib import Path
from ._paths import CONFIG_FILE

_FLAG = Path.home() / ".errex_first_scan_done"


def is_first_run() -> bool:
    return not _FLAG.exists()


def mark_first_run_done() -> None:
    _FLAG.touch()


def run_first_scan() -> None:
    """Run a quick scan (no network, no explain) and show results. Called once on first invocation."""
    from rich.console import Console
    console = Console()
    console.print("\n[bold cyan]errex[/bold cyan] — running your first security scan...\n")

    try:
        from .scan import run_scan
        from .scanners._base import SEVERITIES
        result = run_scan(network=False)
        if not result.findings:
            console.print("[green]✓ No security issues found on this device.[/green]\n")
        else:
            crit_high = [f for f in result.findings if f.severity in ("critical", "high")]
            console.print(f"[yellow]Found {len(result.findings)} issue(s)[/yellow] "
                          f"({len(crit_high)} critical/high)\n")
            for f in result.findings[:5]:
                icons = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}
                icon = icons.get(f.severity, "•")
                console.print(f"  {icon} [bold]{f.title}[/bold]")
                console.print(f"     [dim]{f.detail[:100]}[/dim]")
            if len(result.findings) > 5:
                console.print(f"  [dim]...and {len(result.findings) - 5} more. Run [bold]errex --scan[/bold] for full details.[/dim]")
        console.print("\n[dim]Run [bold]errex --scan[/bold] anytime for a full scan with explanations.[/dim]\n")
    except Exception as e:
        console.print(f"[dim]First scan skipped: {e}[/dim]\n")
    finally:
        mark_first_run_done()
