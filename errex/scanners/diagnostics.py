"""Smart-home diagnostics — disk health, startup load, and offline device detection.

These checks run as part of `errex --scan` (a Pro feature) and give RHT customers
a fuller picture of the health of their machine and home network, beyond pure
security findings.
"""
from __future__ import annotations

import datetime
import json
import platform as _sys_platform
import shutil
import subprocess
from pathlib import Path

from ._base import Finding

_DEVICE_HISTORY_FILE = Path.home() / ".errex_devices.json"
_OFFLINE_AFTER_SCANS = 2  # device must have been seen this many times before "missing" counts


# ── Disk health ──────────────────────────────────────────────────────────────


def check_disk_health() -> Finding | None:
    """Flag low free space on the home/startup volume."""
    try:
        usage = shutil.disk_usage(str(Path.home()))
    except OSError:
        return None

    free_pct = (usage.free / usage.total) * 100 if usage.total else 100
    if free_pct >= 15:
        return None

    free_gb = usage.free / (1024 ** 3)
    severity = "critical" if free_pct < 5 else "high" if free_pct < 10 else "medium"
    return Finding(
        id="diag-disk-low-space",
        severity=severity,
        category="diagnostic",
        platform="cross",
        title=f"Only {free_pct:.1f}% disk space free ({free_gb:.1f} GB)",
        detail=(
            f"The startup volume has {free_gb:.1f} GB ({free_pct:.1f}%) free. "
            "Low disk space slows down the system, can prevent updates from "
            "installing, and may cause apps to crash or fail to save data."
        ),
        fix_cmd="# Free up space: empty Trash, clear downloads, remove unused apps/large files.",
    )


# ── Startup load ─────────────────────────────────────────────────────────────


def _macos_startup_items() -> list[str]:
    out = subprocess.run(
        ["launchctl", "list"], capture_output=True, text=True, timeout=15
    ).stdout
    items = []
    for line in out.strip().splitlines()[1:]:
        parts = line.split("\t")
        label = parts[-1].strip() if parts else ""
        if label and not label.startswith("com.apple."):
            items.append(label)
    return items


def _linux_startup_items() -> list[str]:
    items: list[str] = []
    for d in (Path("/etc/xdg/autostart"), Path.home() / ".config/autostart"):
        if d.is_dir():
            items.extend(p.stem for p in d.glob("*.desktop"))
    return items


def _windows_startup_items() -> list[str]:
    script = (
        "Get-CimInstance Win32_StartupCommand | "
        "Select-Object -ExpandProperty Name"
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True, text=True, timeout=20,
    ).stdout
    return [l.strip() for l in out.splitlines() if l.strip()]


def check_startup_items() -> Finding | None:
    """Flag a heavy login/startup item load that slows boot time."""
    try:
        plat = _sys_platform.system().lower()
        if plat == "darwin":
            items = _macos_startup_items()
        elif plat == "windows":
            items = _windows_startup_items()
        else:
            items = _linux_startup_items()
    except Exception:
        return None

    count = len(items)
    if count < 15:
        return None

    severity = "high" if count >= 30 else "medium"
    return Finding(
        id="diag-startup-load",
        severity=severity,
        category="diagnostic",
        platform="cross",
        title=f"{count} item(s) launch at startup",
        detail=(
            f"{count} programs/services are configured to start automatically:\n"
            + "\n".join(f"  • {name}" for name in items[:10])
            + ("\n  …" if count > 10 else "")
            + "\n\nA heavy startup load is one of the most common causes of a slow boot."
        ),
        fix_cmd="# Review login items / startup apps and disable the ones you don't need running constantly.",
    )


def get_checks() -> list[tuple[str, callable]]:
    return [
        ("Disk health",   check_disk_health),
        ("Startup load",  check_startup_items),
    ]


# ── Offline device detection ─────────────────────────────────────────────────


def _load_device_history() -> dict:
    if not _DEVICE_HISTORY_FILE.exists():
        return {}
    try:
        return json.loads(_DEVICE_HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return {}


def _save_device_history(history: dict) -> None:
    try:
        _DEVICE_HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
    except OSError:
        pass


def check_offline_devices(current_devices: list[dict]) -> list[Finding]:
    """
    Compare the devices seen in this scan to ones seen in previous scans and
    flag any well-established device (seen _OFFLINE_AFTER_SCANS+ times before)
    that has gone missing.

    Updates and persists the device history as a side effect.
    """
    now = datetime.datetime.utcnow().isoformat() + "Z"
    history = _load_device_history()
    current_ips = {d["ip"] for d in current_devices if d.get("ip")}

    findings: list[Finding] = []
    for ip, record in history.items():
        if ip in current_ips:
            continue
        if record.get("seen_count", 0) < _OFFLINE_AFTER_SCANS:
            continue
        if record.get("status") == "offline":
            continue  # already flagged; don't re-open every scan
        name = record.get("hostname") or record.get("name") or ip
        findings.append(Finding(
            id=f"diag-device-offline-{ip.replace('.', '_')}",
            severity="medium",
            category="diagnostic",
            platform="network",
            title=f"Device '{name}' ({ip}) is no longer responding",
            detail=(
                f"'{name}' at {ip} was seen on {record.get('seen_count')} previous scan(s) "
                f"(last seen {record.get('last_seen', 'recently')}) but did not respond this time. "
                "It may be powered off, disconnected, or have changed IP address."
            ),
            fix_cmd=f"# Check that '{name}' is powered on and connected to the network.",
        ))
        record["status"] = "offline"

    for d in current_devices:
        ip = d.get("ip")
        if not ip:
            continue
        record = history.setdefault(ip, {"seen_count": 0})
        record["seen_count"] = record.get("seen_count", 0) + 1
        record["last_seen"] = now
        record["status"] = "online"
        if d.get("hostname"):
            record["hostname"] = d["hostname"]
        if d.get("name"):
            record["name"] = d["name"]

    _save_device_history(history)
    return findings
