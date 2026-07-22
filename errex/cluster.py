"""Cluster log lines by fingerprint and report error frequency."""
from __future__ import annotations

import re
import sys

from rich.table import Table

from . import output

# Patterns to strip from lines before fingerprinting
_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?")
_HEX_RE = re.compile(r"0x[0-9a-fA-F]+")
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
_IP_RE = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
_LINENUM_RE = re.compile(r":\d+")
_NUM_RE = re.compile(r"\b\d+\b")


def _fingerprint(line: str) -> str:
    """Strip variable parts from a log line to produce a stable fingerprint."""
    s = _TS_RE.sub("<TS>", line)
    s = _UUID_RE.sub("<UUID>", s)
    s = _IP_RE.sub("<IP>", s)
    s = _HEX_RE.sub("<HEX>", s)
    s = _LINENUM_RE.sub(":<LINE>", s)
    s = _NUM_RE.sub("<N>", s)
    return s.strip()


def cluster_errors(path: str) -> None:
    """Read log file (or stdin if path is '-'), group lines by fingerprint, print table."""
    if path == "-":
        try:
            lines = sys.stdin.read().splitlines()
        except KeyboardInterrupt:
            return
    else:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except FileNotFoundError:
            output.err_console.print(f"[red]errex: file not found: {path}[/red]")
            sys.exit(1)
        except OSError as e:
            output.err_console.print(f"[red]errex: cannot read {path}: {e}[/red]")
            sys.exit(1)

    if not lines:
        output.console.print("[yellow]No lines to cluster.[/yellow]")
        return

    # Group lines by fingerprint; track first occurrence (line number 1-based)
    groups: dict[str, list] = {}  # fp -> [count, first_line_num, first_line_text]
    for i, line in enumerate(lines, 1):
        fp = _fingerprint(line)
        if not fp:
            continue
        if fp not in groups:
            groups[fp] = [0, i, line]
        groups[fp][0] += 1

    if not groups:
        output.console.print("[yellow]No clusters found.[/yellow]")
        return

    # Sort by count descending
    sorted_groups = sorted(groups.items(), key=lambda kv: -kv[1][0])

    output.console.rule("[bold cyan]errex — Error Clusters[/bold cyan]")
    output.console.print()

    tbl = Table(show_header=True, header_style="bold", show_lines=False, box=None)
    tbl.add_column("COUNT", style="bold red", width=7, justify="right")
    tbl.add_column("FIRST SEEN", style="dim", width=10, justify="right")
    tbl.add_column("ERROR PATTERN", style="cyan")

    for fp, (count, first_line, first_text) in sorted_groups[:50]:
        pattern = fp[:120] + ("…" if len(fp) > 120 else "")
        tbl.add_row(str(count), f"line {first_line}", pattern)

    output.console.print(tbl)
    output.console.print(
        f"\n[dim]{len(groups)} distinct pattern(s) across {len(lines)} lines.[/dim]\n"
    )
