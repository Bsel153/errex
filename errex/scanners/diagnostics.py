"""Smart-home diagnostics — disk health, startup load, and offline device detection.

These checks run as part of `errex --scan` (a Pro feature) and give RHT customers
a fuller picture of the health of their machine and home network, beyond pure
security findings.
"""
from __future__ import annotations

import datetime
import hashlib
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


# ── Milestone alerts ─────────────────────────────────────────────────────────

_MILESTONE_DAYS = (7, 30, 90, 180, 365)
_MILESTONE_FILE = Path.home() / ".errex_milestones.json"
_BAD_SEVERITIES = ("critical", "high", "medium")


def _load_milestone_state() -> dict:
    if not _MILESTONE_FILE.exists():
        return {}
    try:
        return json.loads(_MILESTONE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return {}


def _save_milestone_state(state: dict) -> None:
    try:
        _MILESTONE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        pass


def check_clean_streak() -> Finding | None:
    """
    Celebrate a meaningful run of clean scans — e.g. "30 days running clean!"
    Each milestone is only announced once, the first time it's crossed.
    """
    try:
        from .._scan_scheduler import _SCAN_LOG
        if not _SCAN_LOG.exists():
            return None
        entries = []
        with open(_SCAN_LOG, encoding="utf-8") as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception:
        return None

    if not entries:
        return None

    streak_start_ts = None
    for entry in reversed(entries):
        sevs = entry.get("severities", {})
        if any(sevs.get(s, 0) for s in _BAD_SEVERITIES):
            break
        ts = entry.get("timestamp")
        if not ts:
            break
        streak_start_ts = ts

    if streak_start_ts is None:
        return None

    try:
        start = datetime.datetime.fromisoformat(streak_start_ts.rstrip("Z"))
    except ValueError:
        return None

    streak_days = (datetime.datetime.utcnow() - start).total_seconds() / 86400
    milestone = max((m for m in _MILESTONE_DAYS if streak_days >= m), default=None)
    if milestone is None:
        return None

    state = _load_milestone_state()
    if state.get("last_milestone", 0) >= milestone:
        return None

    state["last_milestone"] = milestone
    _save_milestone_state(state)
    return Finding(
        id=f"diag-milestone-{milestone}d",
        severity="info",
        category="diagnostic",
        platform="cross",
        title=f"🎉 {milestone} days running clean!",
        detail=(
            f"No critical, high, or medium issues have turned up in scans for "
            f"{milestone}+ days straight. Whatever you're doing, keep doing it."
        ),
    )


_ANNIVERSARY_YEARS = (1, 2, 3, 5)


def check_anniversary() -> Finding | None:
    """
    Celebrate a yearly anniversary of using errex — "1 year with errex —
    here's what got fixed for you" — using the oldest scan-log entry as the
    "first scan" date and the local ticket store for the "what got fixed" tally.
    """
    try:
        from .._scan_scheduler import _SCAN_LOG
        if not _SCAN_LOG.exists():
            return None
        first_ts = None
        with open(_SCAN_LOG, encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = entry.get("timestamp")
                if ts:
                    first_ts = ts
                    break
    except Exception:
        return None
    if not first_ts:
        return None

    try:
        first_seen = datetime.datetime.fromisoformat(first_ts.rstrip("Z"))
    except ValueError:
        return None

    years = (datetime.datetime.utcnow() - first_seen).days / 365.25
    anniversary = max((y for y in _ANNIVERSARY_YEARS if years >= y), default=None)
    if anniversary is None:
        return None

    state = _load_milestone_state()
    if state.get("last_anniversary", 0) >= anniversary:
        return None
    state["last_anniversary"] = anniversary
    _save_milestone_state(state)

    try:
        from ..tickets import load_all
        fixed_count = sum(1 for t in load_all() if t.status == "closed")
    except Exception:
        fixed_count = 0

    plural = "year" if anniversary == 1 else "years"
    fixed_line = (f"In that time errex has helped close out {fixed_count} issue(s) on this machine. "
                  if fixed_count else "")
    return Finding(
        id=f"diag-anniversary-{anniversary}y",
        severity="info",
        category="diagnostic",
        platform="cross",
        title=f"🎂 {anniversary} {plural} with errex!",
        detail=(
            f"It's been {anniversary} {plural} since your first scan. {fixed_line}"
            "Thanks for trusting errex to keep an eye on things."
        ),
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


# ── Predictive failure alerts ────────────────────────────────────────────────

_TREND_MIN_SAMPLES = 3
_TREND_MAX_PROJECTION_DAYS = 30


def _disk_free_history() -> list[tuple[datetime.datetime, float]]:
    """Return [(timestamp, free_pct), ...] from the scan log, oldest first."""
    from .._scan_scheduler import _SCAN_LOG
    if not _SCAN_LOG.exists():
        return []
    samples: list[tuple[datetime.datetime, float]] = []
    try:
        with open(_SCAN_LOG, encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                pct = entry.get("disk_free_pct")
                ts = entry.get("timestamp")
                if pct is None or not ts:
                    continue
                try:
                    when = datetime.datetime.fromisoformat(ts.rstrip("Z"))
                except ValueError:
                    continue
                samples.append((when, float(pct)))
    except OSError:
        return []
    return samples


def check_predictive_disk_failure() -> Finding | None:
    """
    Project disk free space forward using recent scan history and warn before
    the disk actually fills up — not just once it's already critically low.
    """
    try:
        samples = _disk_free_history()
    except Exception:
        return None
    if len(samples) < _TREND_MIN_SAMPLES:
        return None

    first_ts, first_pct = samples[0]
    last_ts, last_pct = samples[-1]
    elapsed_days = (last_ts - first_ts).total_seconds() / 86400
    if elapsed_days < 1:
        return None

    decline_per_day = (first_pct - last_pct) / elapsed_days
    if decline_per_day <= 0.05:
        return None  # not declining meaningfully — nothing to predict

    days_to_full = last_pct / decline_per_day
    if days_to_full > _TREND_MAX_PROJECTION_DAYS:
        return None

    severity = "high" if days_to_full <= 7 else "medium"
    return Finding(
        id="diag-predictive-disk-full",
        severity=severity,
        category="diagnostic",
        platform="cross",
        title=f"Disk projected to fill up in ~{days_to_full:.0f} day(s)",
        detail=(
            f"Free space has dropped from {first_pct:.1f}% to {last_pct:.1f}% over the last "
            f"{elapsed_days:.0f} day(s) of scans (about {decline_per_day:.2f} percentage points/day). "
            f"At that rate, the disk will be full in roughly {days_to_full:.0f} day(s) — "
            "well before it becomes an emergency."
        ),
        fix_cmd="# Free up space now (Trash, downloads, large files) before it runs out.",
    )


# ── Duplicate file detection ─────────────────────────────────────────────────

_DUP_SCAN_DIRS = ("Downloads", "Documents", "Desktop", "Pictures")
_DUP_MAX_FILES = 3000
_DUP_MIN_SIZE = 1024            # ignore tiny files — not worth reporting
_DUP_MIN_RECLAIMABLE_MB = 50.0


def _iter_candidate_files():
    home = Path.home()
    for sub in _DUP_SCAN_DIRS:
        d = home / sub
        if not d.is_dir():
            continue
        try:
            for p in d.rglob("*"):
                if p.is_file() and not p.is_symlink():
                    yield p
        except OSError:
            continue


def _hash_file(path: Path, chunk_size: int = 65536) -> str | None:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def check_duplicate_files() -> Finding | None:
    """Find duplicate files in common user folders and report reclaimable space (report-only)."""
    by_size: dict[int, list[Path]] = {}
    count = 0
    for p in _iter_candidate_files():
        if count >= _DUP_MAX_FILES:
            break
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size < _DUP_MIN_SIZE:
            continue
        by_size.setdefault(size, []).append(p)
        count += 1

    groups: list[list[Path]] = []
    reclaimable = 0
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        by_hash: dict[str, list[Path]] = {}
        for p in paths:
            h = _hash_file(p)
            if h:
                by_hash.setdefault(h, []).append(p)
        for dupes in by_hash.values():
            if len(dupes) > 1:
                groups.append(dupes)
                reclaimable += size * (len(dupes) - 1)

    if not groups:
        return None

    reclaimable_mb = reclaimable / (1024 ** 2)
    if reclaimable_mb < _DUP_MIN_RECLAIMABLE_MB:
        return None

    lines = [f"  {len(dupes)}x {dupes[0].name}" for dupes in sorted(groups, key=len, reverse=True)[:5]]
    severity = "low" if reclaimable_mb < 500 else "medium"
    return Finding(
        id="diag-duplicate-files",
        severity=severity,
        category="diagnostic",
        platform="cross",
        title=f"{len(groups)} group(s) of duplicate files using ~{reclaimable_mb:.0f} MB",
        detail=(
            f"Found {len(groups)} group(s) of identical files in Downloads/Documents/Desktop/Pictures "
            f"that could free up roughly {reclaimable_mb:.0f} MB if the extra copies were removed:\n"
            + "\n".join(lines)
        ),
        fix_cmd="# Review the duplicate groups and delete the extra copies — keep one of each.",
    )


# ── Browser cache / junk ─────────────────────────────────────────────────────

_BROWSER_CACHE_DIRS = {
    "darwin": [
        ("Chrome",  "Library/Caches/Google/Chrome"),
        ("Safari",  "Library/Caches/com.apple.Safari"),
        ("Firefox", "Library/Caches/Firefox/Profiles"),
    ],
    "linux": [
        ("Chrome",   ".cache/google-chrome"),
        ("Chromium", ".cache/chromium"),
        ("Firefox",  ".cache/mozilla/firefox"),
    ],
    "windows": [
        ("Chrome",  "AppData/Local/Google/Chrome/User Data/Default/Cache"),
        ("Edge",    "AppData/Local/Microsoft/Edge/User Data/Default/Cache"),
        ("Firefox", "AppData/Local/Mozilla/Firefox/Profiles"),
    ],
}
_BROWSER_JUNK_MIN_MB = 200.0


def _dir_size(path: Path, max_entries: int = 20000) -> int:
    total = 0
    count = 0
    try:
        for p in path.rglob("*"):
            count += 1
            if count > max_entries:
                break
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def check_browser_junk() -> Finding | None:
    """Report how much space browser caches are using (report-only — never deletes anything)."""
    plat = _sys_platform.system().lower()
    targets = _BROWSER_CACHE_DIRS.get(plat, [])
    home = Path.home()

    found: list[tuple[str, int]] = []
    total_bytes = 0
    for name, rel in targets:
        d = home / rel
        if not d.is_dir():
            continue
        size = _dir_size(d)
        if size > 10 * 1024 * 1024:
            found.append((name, size))
            total_bytes += size

    if not found:
        return None
    total_mb = total_bytes / (1024 ** 2)
    if total_mb < _BROWSER_JUNK_MIN_MB:
        return None

    lines = [f"  {name}: ~{size / (1024 ** 2):.0f} MB" for name, size in found]
    return Finding(
        id="diag-browser-cache",
        severity="low",
        category="diagnostic",
        platform="cross",
        title=f"Browser caches are using ~{total_mb:.0f} MB",
        detail=(
            "Browser cache/temp data found:\n" + "\n".join(lines) +
            "\n\nClearing this won't touch bookmarks, passwords, or history — "
            "just temporary files browsers rebuild automatically."
        ),
        fix_cmd="# Clear cache from each browser's Settings → Privacy → Clear browsing data.",
    )


def get_checks() -> list[tuple[str, callable]]:
    return [
        ("Disk health",       check_disk_health),
        ("Startup load",      check_startup_items),
        ("Memory pressure",   check_memory_pressure),
        ("Network health",    check_network_health),
        ("Disk trend",        check_predictive_disk_failure),
        ("Duplicate files",   check_duplicate_files),
        ("Browser cache",     check_browser_junk),
        ("Clean streak",      check_clean_streak),
        ("Anniversary",       check_anniversary),
    ]


# ── Offline device detection ─────────────────────────────────────────────────


def _load_device_history() -> dict:
    if not _DEVICE_HISTORY_FILE.exists():
        return {}
    try:
        return json.loads(_DEVICE_HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return {}


def _device_display_name(ip: str, record: dict, raw: dict | None = None) -> str:
    """Prefer a customer-given nickname, then hostname, then name, then the bare IP."""
    raw = raw or {}
    return (record.get("nickname") or record.get("hostname") or record.get("name")
            or raw.get("hostname") or raw.get("name") or ip)


def set_device_nickname(ip: str, nickname: str) -> dict:
    """Give a device a friendly name, e.g. 'Living Room TV'. Returns the updated record."""
    history = _load_device_history()
    record = history.setdefault(ip, {"seen_count": 0})
    record["nickname"] = nickname
    _save_device_history(history)
    return record


def list_known_devices() -> list[dict]:
    """Return known devices with ip, nickname, hostname, status — for `errex --devices`."""
    history = _load_device_history()
    out = []
    for ip, record in history.items():
        out.append({
            "ip": ip,
            "nickname": record.get("nickname"),
            "hostname": record.get("hostname") or record.get("name"),
            "status": record.get("status", "unknown"),
            "last_seen": record.get("last_seen"),
        })
    return out


def _save_device_history(history: dict) -> None:
    try:
        _DEVICE_HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
    except OSError:
        pass


def check_offline_devices(current_devices: list[dict]) -> list[Finding]:
    """
    Compare the devices seen in this scan to ones seen in previous scans and flag:
      - any well-established device (seen _OFFLINE_AFTER_SCANS+ times before) that
        has gone missing ("offline"), and
      - any device that has never been seen before, once a baseline of previous
        scans exists ("unauthorized device" alert — a new device joined the LAN).

    Updates and persists the device history as a side effect.
    """
    now = datetime.datetime.utcnow().isoformat() + "Z"
    history = _load_device_history()
    has_baseline = bool(history)  # don't alert on "new" devices during the very first scan
    current_ips = {d["ip"] for d in current_devices if d.get("ip")}

    findings: list[Finding] = []
    for ip, record in history.items():
        if ip in current_ips:
            continue
        if record.get("seen_count", 0) < _OFFLINE_AFTER_SCANS:
            continue
        if record.get("status") == "offline":
            continue  # already flagged; don't re-open every scan
        name = _device_display_name(ip, record)
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
        record = history.get(ip)
        if record is None and has_baseline:
            name = _device_display_name(ip, {}, raw=d)
            findings.append(Finding(
                id=f"diag-device-new-{ip.replace('.', '_')}",
                severity="low",
                category="security",
                platform="network",
                title=f"New device joined the network: '{name}' ({ip})",
                detail=(
                    f"'{name}' at {ip} has not been seen on any previous scan of this network. "
                    "If you don't recognize it, it could be a guest's device, a new gadget — "
                    "or someone unauthorized on your Wi-Fi."
                ),
                fix_cmd=f"# If you don't recognize '{name}', check your router's device list and change your Wi-Fi password if needed.",
            ))

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
