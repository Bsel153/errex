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
