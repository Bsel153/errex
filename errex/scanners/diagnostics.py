"""Smart-home diagnostics — disk health, startup load, and offline device detection.

These checks run as part of `errex --scan` (a Pro feature) and give RHT customers
a fuller picture of the health of their machine and home network, beyond pure
security findings.
"""
from __future__ import annotations

import datetime
import json
import platform as _sys_platform
import re
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


# ── Memory pressure ──────────────────────────────────────────────────────────


def _macos_memory() -> tuple[float, float] | None:
    """Return (used_pct, swap_used_mb) from `vm_stat` / `sysctl`, or None."""
    out = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=10).stdout
    page_size = 4096
    m = re.search(r"page size of (\d+) bytes", out)
    if m:
        page_size = int(m.group(1))
    pages = {}
    for line in out.splitlines():
        m = re.match(r"Pages (\w[\w ]*):\s+(\d+)\.", line)
        if m:
            pages[m.group(1).strip()] = int(m.group(2))
    if not pages:
        return None
    free = pages.get("free", 0) + pages.get("speculative", 0)
    total_active = sum(pages.values())
    if total_active == 0:
        return None
    used_pct = (1 - free / total_active) * 100

    swap_out = subprocess.run(["sysctl", "vm.swapusage"], capture_output=True, text=True, timeout=10).stdout
    swap_mb = 0.0
    m = re.search(r"used\s*=\s*([\d.]+)M", swap_out)
    if m:
        swap_mb = float(m.group(1))
    return used_pct, swap_mb


def _linux_memory() -> tuple[float, float] | None:
    info = {}
    with open("/proc/meminfo", encoding="utf-8") as f:
        for line in f:
            parts = line.split(":")
            if len(parts) == 2:
                m = re.match(r"\s*(\d+)", parts[1])
                if m:
                    info[parts[0].strip()] = int(m.group(1))
    total = info.get("MemTotal")
    available = info.get("MemAvailable")
    if not total or available is None:
        return None
    used_pct = (1 - available / total) * 100
    swap_total = info.get("SwapTotal", 0)
    swap_free = info.get("SwapFree", 0)
    swap_used_mb = (swap_total - swap_free) / 1024
    return used_pct, swap_used_mb


def _windows_memory() -> tuple[float, float] | None:
    script = (
        "$os = Get-CimInstance Win32_OperatingSystem; "
        "Write-Output \"$($os.TotalVisibleMemorySize) $($os.FreePhysicalMemory)\""
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True, text=True, timeout=20,
    ).stdout.strip()
    parts = out.split()
    if len(parts) != 2:
        return None
    total_kb, free_kb = float(parts[0]), float(parts[1])
    if total_kb == 0:
        return None
    used_pct = (1 - free_kb / total_kb) * 100
    return used_pct, 0.0


def check_memory_pressure() -> Finding | None:
    """Flag sustained high memory usage / heavy swap use (a common 'memory leak' symptom)."""
    try:
        plat = _sys_platform.system().lower()
        if plat == "darwin":
            stats = _macos_memory()
        elif plat == "windows":
            stats = _windows_memory()
        else:
            stats = _linux_memory()
    except Exception:
        return None

    if stats is None:
        return None
    used_pct, swap_mb = stats
    if used_pct < 85 and swap_mb < 1024:
        return None

    severity = "high" if used_pct >= 95 or swap_mb >= 4096 else "medium"
    return Finding(
        id="diag-memory-pressure",
        severity=severity,
        category="diagnostic",
        platform="cross",
        title=f"High memory pressure ({used_pct:.0f}% used, {swap_mb:.0f} MB swapped)",
        detail=(
            f"{used_pct:.0f}% of physical memory is in use"
            + (f" and {swap_mb:.0f} MB has been swapped to disk" if swap_mb >= 1024 else "")
            + ". Sustained high memory pressure causes sluggishness and can be a sign "
              "of a memory leak in a running app or browser tab."
        ),
        fix_cmd="# Check Activity Monitor / Task Manager for the heaviest processes and quit ones you don't need.",
    )


# ── Network health ───────────────────────────────────────────────────────────


def _ping(host: str, count: int = 4, timeout_s: int = 8) -> tuple[float | None, float | None]:
    """Return (loss_pct, avg_ms) for pinging host, or (None, None) on failure."""
    plat = _sys_platform.system().lower()
    if plat == "windows":
        cmd = ["ping", "-n", str(count), "-w", "1000", host]
    else:
        cmd = ["ping", "-c", str(count), "-W" if plat == "linux" else "-t", "1", host]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s).stdout
    except Exception:
        return None, None

    loss = None
    m = re.search(r"([\d.]+)%\s*(?:packet )?loss", out)
    if m:
        loss = float(m.group(1))

    avg = None
    m = re.search(r"(?:=|/)\s*([\d.]+)/([\d.]+)/([\d.]+)", out)  # min/avg/max
    if m:
        avg = float(m.group(2))
    else:
        m = re.search(r"Average = (\d+)ms", out)  # Windows summary line
        if m:
            avg = float(m.group(1))

    return loss, avg


def check_network_health() -> Finding | None:
    """Ping a reliable external host and flag high latency or packet loss."""
    loss, avg_ms = _ping("1.1.1.1")
    if loss is None and avg_ms is None:
        return None

    bad_loss = loss is not None and loss >= 25
    bad_latency = avg_ms is not None and avg_ms >= 150

    if not bad_loss and not bad_latency:
        return None

    severity = "high" if (loss is not None and loss >= 50) else "medium"
    parts = []
    if loss is not None:
        parts.append(f"{loss:.0f}% packet loss")
    if avg_ms is not None:
        parts.append(f"{avg_ms:.0f} ms average latency")
    summary = " and ".join(parts)
    return Finding(
        id="diag-network-health",
        severity=severity,
        category="diagnostic",
        platform="network",
        title=f"Network connection looks unstable ({summary})",
        detail=(
            f"A ping test to a reliable external host showed {summary}. "
            "This usually points to Wi-Fi interference, an overloaded router, "
            "or an ISP issue, and can cause buffering, dropped calls, and slow page loads."
        ),
        fix_cmd="# Try moving closer to the router, restarting it, or running a wired speed test to isolate the cause.",
    )


def get_checks() -> list[tuple[str, callable]]:
    return [
        ("Disk health",     check_disk_health),
        ("Startup load",    check_startup_items),
        ("Memory pressure", check_memory_pressure),
        ("Network health",  check_network_health),
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
