"""Auto-scan daemon — run scans on an interval, alert on changes."""
from __future__ import annotations

import json
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from . import output


def _load_last_findings(state_file: Path) -> set[str]:
    if not state_file.exists():
        return set()
    try:
        data = json.loads(state_file.read_text())
        return set(data.get("finding_ids", []))
    except Exception:
        return set()


def _save_findings(state_file: Path, finding_ids: set[str]) -> None:
    state_file.write_text(json.dumps({
        "finding_ids": sorted(finding_ids),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }))


def auto_scan(
    interval_minutes: int = 60,
    severity: str | None = None,
    no_explain: bool = True,
    slack_webhook: str | None = None,
    discord_webhook: str | None = None,
    quiet: bool = False,
) -> None:
    from .scan import run_scan, detect_platform
    from .scanners._base import SEVERITIES

    state_file = Path.home() / ".errex_autoscan_state.json"
    sev_idx = SEVERITIES.index(severity) if severity and severity in SEVERITIES else len(SEVERITIES) - 1

    running = True

    def _stop(sig, frame):
        nonlocal running
        running = False
        output.console.print("\n[dim]Auto-scan stopped.[/dim]")

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    output.console.print(f"[green]✓ Auto-scan started[/green] — scanning every {interval_minutes} minutes")
    output.console.print("[dim]Press Ctrl+C to stop.[/dim]\n")

    while running:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        if not quiet:
            output.console.print(f"[dim]─── scan at {now} ───[/dim]")

        try:
            plat = detect_platform()
            result = run_scan(plat, progress_cb=None)
        except Exception as e:
            output.err_console.print(f"[red]Scan error: {e}[/red]")
            _sleep(interval_minutes * 60, lambda: running)
            continue

        current_ids = set()
        for f in result.findings:
            sev_i = SEVERITIES.index(f.severity) if f.severity in SEVERITIES else 999
            if sev_i <= sev_idx:
                current_ids.add(f.id)

        prev_ids = _load_last_findings(state_file)
        new_ids = current_ids - prev_ids
        resolved_ids = prev_ids - current_ids
        _save_findings(state_file, current_ids)

        if not quiet:
            output.console.print(
                f"  Open: {len(current_ids)}  |  New: {len(new_ids)}  |  Resolved: {len(resolved_ids)}"
            )

        if new_ids:
            new_findings = [f for f in result.findings if f.id in new_ids]
            for f in new_findings:
                output.console.print(f"  [bold red]NEW[/bold red] [{f.severity.upper()}] {f.title}")

            if slack_webhook:
                from .slack_notify import notify_scan_summary
                notify_scan_summary(
                    len(current_ids),
                    sum(1 for f in result.findings if f.id in current_ids and f.severity in ("critical", "high")),
                    len(new_ids),
                    webhook_url=slack_webhook,
                )

            if discord_webhook:
                from .discord_notify import notify_scan_summary
                notify_scan_summary(
                    len(current_ids),
                    sum(1 for f in result.findings if f.id in current_ids and f.severity in ("critical", "high")),
                    len(new_ids),
                    webhook_url=discord_webhook,
                )

        elif resolved_ids and not quiet:
            output.console.print(f"  [green]✓ {len(resolved_ids)} issue(s) resolved since last scan[/green]")

        if not quiet:
            output.console.print()

        _sleep(interval_minutes * 60, lambda: running)

    sys.exit(0)


def _sleep(seconds: float, check_fn) -> None:
    end = time.time() + seconds
    while time.time() < end and check_fn():
        time.sleep(min(2.0, end - time.time()))
