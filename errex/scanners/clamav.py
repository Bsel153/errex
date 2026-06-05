"""ClamAV wrapper — uses the clamscan binary if installed."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from ._base import Finding


def _clamscan_available() -> bool:
    return shutil.which("clamscan") is not None


def _run_clamscan(path: str, timeout: int = 120) -> tuple[str, int]:
    try:
        r = subprocess.run(
            ["clamscan", "--recursive", "--infected", "--no-summary", path],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.stdout + r.stderr, r.returncode
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        return str(e), -1


def check_clamav_installed() -> Finding | None:
    """Warn when ClamAV is not installed (info-level, not a threat)."""
    if _clamscan_available():
        return None
    return Finding(
        id="clamav-not-installed",
        severity="info",
        category="security",
        platform="cross",
        title="ClamAV not installed — signature-based malware scanning unavailable",
        detail=(
            "errex can run ClamAV (open-source antivirus) when it is installed.\n"
            "Install: apt install clamav  |  brew install clamav  |  dnf install clamav"
        ),
        fix_cmd=_install_hint(),
        explanation=(
            "ClamAV provides signature-based malware detection. Without it errex "
            "falls back to heuristic checks only."
        ),
    )


def _install_hint() -> str:
    import platform
    s = platform.system()
    if s == "Darwin":
        return "brew install clamav && freshclam"
    if s == "Windows":
        return "winget install ClamAV"
    # Detect distro
    try:
        txt = Path("/etc/os-release").read_text()
        if "debian" in txt.lower() or "ubuntu" in txt.lower():
            return "sudo apt install -y clamav && sudo freshclam"
        if "fedora" in txt.lower() or "rhel" in txt.lower() or "centos" in txt.lower():
            return "sudo dnf install -y clamav clamav-update && sudo freshclam"
    except OSError:
        pass
    return "apt/dnf/brew install clamav && freshclam"


def scan_path(path: str = str(Path.home())) -> Finding | None:
    """Run clamscan on *path* and return a Finding if infected files are detected."""
    if not _clamscan_available():
        return check_clamav_installed()

    output, rc = _run_clamscan(path)

    if rc == -1:
        return Finding(
            id="clamav-error",
            severity="info",
            category="error",
            platform="cross",
            title="ClamAV scan failed",
            detail=output[:500],
            explanation="clamscan exited with an error. Check that virus definitions are up to date (run freshclam).",
        )

    # rc == 0: clean, rc == 1: infected, rc == 2: scan error
    if rc == 0:
        return None  # clean

    infected_lines = [l for l in output.splitlines() if "FOUND" in l]
    count = len(infected_lines)

    return Finding(
        id="clamav-infected",
        severity="critical",
        category="security",
        platform="cross",
        title=f"ClamAV detected {count} infected file(s)",
        detail="\n".join(infected_lines[:20]),
        explanation=(
            "ClamAV matched one or more files against its virus signature database. "
            "Quarantine or delete the listed files and run freshclam to update definitions."
        ),
    )


def get_checks(path: str | None = None) -> list[tuple[str, Callable[[], Finding | None]]]:
    """Return ClamAV checks. *path* defaults to home directory."""
    scan_target = path or str(Path.home())
    return [
        ("ClamAV Installed", check_clamav_installed),
        ("ClamAV Scan", lambda: scan_path(scan_target)),
    ]
