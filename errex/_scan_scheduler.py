"""Scan scheduler — set up automatic periodic scans via system scheduler."""
from __future__ import annotations
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_SCAN_LOG = Path.home() / ".errex_scan_log.jsonl"


def _disk_free_pct() -> float | None:
    try:
        usage = shutil.disk_usage(str(Path.home()))
        if not usage.total:
            return None
        return round((usage.free / usage.total) * 100, 2)
    except OSError:
        return None


def log_scan_result(result) -> dict:
    """Append a scan result summary to the scan log. Returns the logged entry."""
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "platform": result.platform,
        "finding_count": len(result.findings),
        "severities": {s: sum(1 for f in result.findings if f.severity == s)
                       for s in ("critical", "high", "medium", "low", "info") if any(f.severity == s for f in result.findings)},
        "categories": {c: sum(1 for f in result.findings if f.category == c)
                       for c in ("security", "misconfiguration", "error", "diagnostic")
                       if any(f.category == c for f in result.findings)},
        "disk_free_pct": _disk_free_pct(),
    }
    with open(_SCAN_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def get_last_scan_info() -> dict | None:
    """Return the most recent scan log entry."""
    if not _SCAN_LOG.exists():
        return None
    last = None
    try:
        with open(_SCAN_LOG) as f:
            for line in f:
                try:
                    last = json.loads(line)
                except Exception:
                    continue
    except Exception:
        return None
    return last


_STREAK_BAD_SEVERITIES = ("critical", "high", "medium")


def current_health_streak_days() -> float | None:
    """
    How many days since the most recent scan that found a critical/high/medium issue.

    Powers the gamified "health streak" shown in --scan-status — a running
    counter that resets the moment something serious turns up again.
    """
    if not _SCAN_LOG.exists():
        return None
    entries = []
    try:
        with open(_SCAN_LOG, encoding="utf-8") as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return None
    if not entries:
        return None

    streak_start_ts = None
    for entry in reversed(entries):
        sevs = entry.get("severities", {})
        if any(sevs.get(s, 0) for s in _STREAK_BAD_SEVERITIES):
            break
        ts = entry.get("timestamp")
        if not ts:
            break
        streak_start_ts = ts
    if streak_start_ts is None:
        return None
    try:
        start = datetime.fromisoformat(streak_start_ts.rstrip("Z"))
    except ValueError:
        return None
    return round((datetime.utcnow() - start).total_seconds() / 86400, 1)


def setup_cron(frequency: str = "daily", platform: str | None = None) -> str:
    """Return cron/launchd/task-scheduler setup instructions."""
    import platform as _plat
    plat = platform or _plat.system().lower()
    cmd = f"{sys.executable} -m errex --scan --scan-no-explain"

    schedules = {
        "hourly": "0 * * * *",
        "daily": "0 8 * * *",
        "weekly": "0 8 * * 1",
    }
    cron = schedules.get(frequency, "0 8 * * *")

    if "darwin" in plat:
        # launchd plist
        plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.errex.scan</string>
    <key>ProgramArguments</key>
    <array><string>{sys.executable}</string><string>-m</string><string>errex</string>
    <string>--scan</string><string>--scan-no-explain</string></array>
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
    <key>RunAtLoad</key><true/>
    <key>StandardErrorPath</key><string>{Path.home()}/.errex_scan.log</string>
</dict>
</plist>"""
        plist_path = Path.home() / "Library/LaunchAgents/com.errex.scan.plist"
        return (f"# macOS launchd — save to {plist_path} and run:\n"
                f"# launchctl load {plist_path}\n\n{plist}")
    elif "windows" in plat:
        return (f"# Windows Task Scheduler\n"
                f'schtasks /create /tn "errex scan" /tr "{cmd}" '
                f"/sc {'HOURLY' if frequency == 'hourly' else 'DAILY'} /st 08:00 /f")
    else:
        return f"# Add to crontab (crontab -e):\n{cron} {cmd}"


def print_scan_status() -> None:
    from rich.console import Console
    console = Console()
    last = get_last_scan_info()
    if not last:
        console.print("[dim]No scans on record yet. Run [bold]errex --scan[/bold] to start.[/dim]")
        return
    ts = last.get("timestamp", "unknown")
    count = last.get("finding_count", 0)
    sevs = last.get("severities", {})
    sev_str = ", ".join(f"{v} {k}" for k, v in sevs.items()) if sevs else "none"
    console.print(f"\n[bold]Last scan:[/bold] {ts}")
    console.print(f"[bold]Findings:[/bold] {count} total — {sev_str}")
    cats = last.get("categories", {})
    if cats:
        cat_str = ", ".join(f"{v} {k}" for k, v in cats.items())
        console.print(f"[bold]Categories:[/bold] {cat_str}")
    streak = current_health_streak_days()
    if streak is not None and streak >= 1:
        console.print(f"[bold]Health streak:[/bold] 🔥 {int(streak)} day(s) clean — keep it going!")
    console.print()
