"""System restore points — best-effort wrappers around the OS's own snapshot tools.

errex never invents its own rollback mechanism here; it just asks the
operating system to take a checkpoint (Time Machine, VSS, btrfs/LVM/timeshift)
before a risky change, the same way a cautious admin would by hand.
"""
from __future__ import annotations

import platform
import shutil
import subprocess


def _run(cmd: list[str], timeout: int = 120) -> tuple[str, int]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (proc.stdout.strip() or proc.stderr.strip()), proc.returncode
    except FileNotFoundError:
        return "command not found", -1
    except subprocess.SubprocessError as e:
        return str(e), -1


def is_supported() -> bool:
    """True if errex knows how to ask this OS for a restore point."""
    system = platform.system()
    if system == "Darwin":
        return shutil.which("tmutil") is not None
    if system == "Windows":
        return shutil.which("powershell") is not None
    if system == "Linux":
        return shutil.which("timeshift") is not None
    return False


def create_restore_point(reason: str = "errex checkpoint") -> dict:
    """
    Ask the OS to take a restore point / local snapshot before a risky change.

    Returns {"ok": True, "tool": ..., "message": ...} on apparent success,
    or {"error": ...} if unsupported or the OS tool failed.
    """
    system = platform.system()

    if system == "Darwin":
        if shutil.which("tmutil") is None:
            return {"error": "Time Machine (tmutil) is not available on this Mac."}
        out, rc = _run(["tmutil", "localsnapshot"])
        if rc != 0:
            return {"error": f"tmutil localsnapshot failed: {out}"}
        return {"ok": True, "tool": "Time Machine (local snapshot)", "message": out or "Snapshot created"}

    if system == "Windows":
        if shutil.which("powershell") is None:
            return {"error": "PowerShell is not available."}
        ps = f'Checkpoint-Computer -Description "{reason}" -RestorePointType "MODIFY_SETTINGS"'
        out, rc = _run(["powershell", "-Command", ps])
        if rc != 0:
            return {"error": f"Checkpoint-Computer failed: {out or 'System Restore may be disabled'}"}
        return {"ok": True, "tool": "Windows System Restore", "message": out or "Restore point created"}

    if system == "Linux":
        if shutil.which("timeshift") is None:
            return {"error": "timeshift is not installed — install it to enable restore points on Linux "
                             "(e.g. `sudo apt install timeshift`)."}
        out, rc = _run(["sudo", "timeshift", "--create", "--comments", reason, "--scripted"])
        if rc != 0:
            return {"error": f"timeshift snapshot failed: {out}"}
        return {"ok": True, "tool": "timeshift", "message": out or "Snapshot created"}

    return {"error": f"System restore points are not supported on {system}."}
