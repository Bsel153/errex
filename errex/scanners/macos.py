"""macOS security scanner — all checks via subprocess, no extra dependencies."""
from __future__ import annotations

import re
import subprocess
from ._base import Finding

_FW = "/usr/libexec/ApplicationFirewall/socketfilterfw"


def _run(cmd: list[str], timeout: int = 15) -> tuple[str, int]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout + r.stderr, r.returncode
    except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError, OSError):
        return "", -1


def _fix(cmd: list[str]) -> bool:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=15).returncode == 0
    except Exception:
        return False


def check_firewall() -> Finding | None:
    out, rc = _run([_FW, "--getglobalstate"])
    if rc == -1 or "disabled" not in out.lower():
        return None
    return Finding(
        id="macos-firewall-disabled",
        severity="high",
        category="security",
        platform="macos",
        title="Application firewall is disabled",
        detail="The macOS application firewall is not running. Incoming connections from unauthorized apps are not blocked.",
        fix_cmd=f"sudo {_FW} --setglobalstate on",
    )


def check_sip() -> Finding | None:
    out, rc = _run(["csrutil", "status"])
    if rc == -1 or "disabled" not in out.lower():
        return None
    return Finding(
        id="macos-sip-disabled",
        severity="critical",
        category="security",
        platform="macos",
        title="System Integrity Protection (SIP) is disabled",
        detail=(
            "SIP prevents malicious software from modifying protected files and processes. "
            "It can only be re-enabled from macOS Recovery mode (hold Power on boot)."
        ),
    )


def check_gatekeeper() -> Finding | None:
    out, rc = _run(["spctl", "--status"])
    if rc == -1 or "disabled" not in out.lower():
        return None
    return Finding(
        id="macos-gatekeeper-disabled",
        severity="high",
        category="security",
        platform="macos",
        title="Gatekeeper is disabled",
        detail="Gatekeeper verifies downloaded apps are signed by identified developers and checked for malware before running.",
        fix_cmd="sudo spctl --master-enable",
    )


def check_filevault() -> Finding | None:
    out, rc = _run(["fdesetup", "status"])
    if rc == -1 or "off" not in out.lower():
        return None
    return Finding(
        id="macos-filevault-off",
        severity="medium",
        category="security",
        platform="macos",
        title="FileVault disk encryption is off",
        detail=(
            "FileVault encrypts the startup disk. Without it, data can be read directly from "
            "the drive if physical access is obtained (e.g., stolen laptop)."
        ),
        # User must enable via System Settings > Privacy & Security > FileVault
    )


def check_ssh() -> Finding | None:
    out, rc = _run(["launchctl", "list", "com.openssh.sshd"])
    if rc != 0:
        return None
    lines = [l for l in out.strip().splitlines() if l.strip()]
    if lines and not lines[0].startswith("-"):
        return Finding(
            id="macos-ssh-exposed",
            severity="medium",
            category="security",
            platform="macos",
            title="SSH (Remote Login) is enabled",
            detail="Port 22 is open and accepting SSH connections. This increases the attack surface if credentials are weak.",
            fix_cmd="sudo launchctl unload -w /System/Library/LaunchDaemons/ssh.plist",
        )
    return None


def check_screen_sharing() -> Finding | None:
    out, rc = _run(["launchctl", "list", "com.apple.screensharing"])
    if rc != 0:
        return None
    lines = [l for l in out.strip().splitlines() if l.strip()]
    if lines and not lines[0].startswith("-"):
        return Finding(
            id="macos-screensharing-on",
            severity="medium",
            category="security",
            platform="macos",
            title="Screen Sharing is enabled",
            detail="Screen Sharing (VNC) allows remote graphical access. Disable it if not actively needed.",
            fix_cmd="sudo launchctl unload -w /System/Library/LaunchDaemons/com.apple.screensharing.plist",
        )
    return None


def check_open_ports() -> Finding | None:
    out, rc = _run(["lsof", "-i", "-P", "-n"])
    if rc == -1:
        return None
    # Ports commonly used by macOS system services (benign)
    _safe = {22, 53, 88, 443, 445, 5353, 5354, 7000, 7001, 7100}
    suspicious = []
    for line in out.splitlines():
        if "LISTEN" not in line:
            continue
        m = re.search(r'(?:[\*0-9.]+):(\d+) \(LISTEN\)', line)
        if m:
            port = int(m.group(1))
            if port not in _safe and port > 1023:
                proc = line.split()[0]
                suspicious.append(f"port {port} ({proc})")
    if suspicious:
        return Finding(
            id="macos-open-ports",
            severity="low",
            category="security",
            platform="macos",
            title=f"{len(suspicious)} unexpected port(s) listening",
            detail="Processes accepting inbound connections on non-standard ports:\n  " + "\n  ".join(suspicious[:10]),
        )
    return None


def check_recent_faults() -> Finding | None:
    out, rc = _run(
        ["log", "show", "--style", "compact",
         "--predicate", "eventType == fault",
         "--last", "24h"],
        timeout=25,
    )
    if rc == -1:
        return None
    lines = [l for l in out.strip().splitlines()[1:] if l.strip()]  # skip header
    count = len(lines)
    if count < 5:
        return None
    severity = "medium" if count >= 20 else "low"
    return Finding(
        id="macos-recent-faults",
        severity=severity,
        category="error",
        platform="macos",
        title=f"{count} system fault(s) in the last 24 hours",
        detail="\n".join(lines[:10]),
    )


def check_auto_update() -> Finding | None:
    out, rc = _run(["defaults", "read", "com.apple.SoftwareUpdate", "AutomaticCheckEnabled"])
    if rc == -1 or out.strip() != "0":
        return None
    return Finding(
        id="macos-autoupdate-off",
        severity="medium",
        category="misconfiguration",
        platform="macos",
        title="Automatic software update checks are disabled",
        detail="macOS is not checking for security updates. Vulnerabilities may go unpatched.",
        fix_cmd="defaults write com.apple.SoftwareUpdate AutomaticCheckEnabled -bool true",
        fix_fn=lambda: _fix(["defaults", "write", "com.apple.SoftwareUpdate", "AutomaticCheckEnabled", "-bool", "true"]),
        backup_paths=("/Library/Preferences/com.apple.SoftwareUpdate.plist",),
    )


def get_checks() -> list[tuple[str, callable]]:
    return [
        ("Firewall",        check_firewall),
        ("SIP",             check_sip),
        ("Gatekeeper",      check_gatekeeper),
        ("FileVault",       check_filevault),
        ("SSH",             check_ssh),
        ("Screen Sharing",  check_screen_sharing),
        ("Open Ports",      check_open_ports),
        ("Recent Faults",   check_recent_faults),
        ("Auto Update",     check_auto_update),
    ]
