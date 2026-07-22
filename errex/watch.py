from __future__ import annotations

import os
import sys
import time

from . import output, _constants
from .utils import _error_fingerprint, notify


def watch_file(path: str, model: str, brief: bool, lang: str | None) -> None:
    """Tail a log file and explain errors as they appear, deduplicating repeats."""
    from .core import explain_error

    if not os.path.exists(path):
        output.err_console.print(f"[red]errex: file not found: {path}[/red]")
        sys.exit(1)

    output.console.print(f"[bold]Watching[/bold] [cyan]{path}[/cyan] [dim](Ctrl+C to stop | duplicates suppressed)[/dim]")

    seen_fingerprints: set = set()
    COOLDOWN = 30.0  # seconds before re-explaining a similar error

    with open(path, encoding="utf-8", errors="replace") as f:
        f.seek(0, 2)
        buffer: list = []
        has_error = False
        last_activity: float | None = None
        fingerprint_times: dict = {}

        try:
            while True:
                line = f.readline()
                if line:
                    buffer.append(line)
                    last_activity = time.time()
                    if any(p in line.lower() for p in _constants.ERROR_PATTERNS):
                        has_error = True
                elif has_error and last_activity and time.time() - last_activity > 2.0:
                    text = "".join(buffer).strip()
                    fp = _error_fingerprint(text)
                    now = time.time()
                    last_seen = fingerprint_times.get(fp, 0)

                    if now - last_seen < COOLDOWN:
                        output.console.print(f"\n[dim]Duplicate error suppressed (seen {int(now - last_seen)}s ago)[/dim]")
                    else:
                        fingerprint_times[fp] = now
                        output.console.print("\n[bold yellow]New error detected[/bold yellow]")
                        notify("errex — error detected", path)
                        explain_error(text, model=model, brief=brief, lang=lang, do_notify=False)

                    buffer = []
                    has_error = False
                    last_activity = None
                else:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            output.console.print("\n[dim]Stopped watching.[/dim]")


def watch_directory(path: str) -> None:
    """Poll DIR every 2s for new .log files; display new files in a rich panel."""
    import os
    from rich.panel import Panel

    if not os.path.isdir(path):
        output.err_console.print(f"[red]errex: directory not found: {path}[/red]")
        sys.exit(1)

    output.console.print(
        f"[bold]Watching directory[/bold] [cyan]{path}[/cyan] "
        f"[dim]for new .log files (Ctrl+C to stop)[/dim]"
    )

    seen: set[str] = set()

    # Seed with existing log files so we don't re-report them
    for root, _dirs, files in os.walk(path):
        for fname in files:
            if fname.endswith(".log"):
                seen.add(os.path.join(root, fname))

    try:
        while True:
            time.sleep(2)
            for root, _dirs, files in os.walk(path):
                for fname in files:
                    if not fname.endswith(".log"):
                        continue
                    fpath = os.path.join(root, fname)
                    if fpath in seen:
                        continue
                    seen.add(fpath)
                    try:
                        with open(fpath, encoding="utf-8", errors="replace") as f:
                            first_lines = "".join(f.readline() for _ in range(10))
                    except OSError:
                        first_lines = "(could not read file)"
                    output.console.print(
                        Panel(
                            first_lines.rstrip() or "(empty file)",
                            title=f"[bold yellow]New log file: {fpath}[/bold yellow]",
                            expand=False,
                        )
                    )
    except KeyboardInterrupt:
        output.console.print("\n[dim]Stopped watching directory.[/dim]")
