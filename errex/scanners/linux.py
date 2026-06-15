"""Linux security scanner — all checks via subprocess/file reads, no extra dependencies."""
from __future__ import annotations

import re
import subprocess
from typing import Callable

from ._base import Finding


def _run(cmd: list[str], timeout: int = 15) -> tuple[str, int]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout + r.stderr, r.returncode
    except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError, OSError):
        return "", -1


def check_firewall() -> Finding | None:
    # Try ufw first
    ufw_out, ufw_rc = _run(["ufw", "status"])
    if ufw_rc != -1:
        # ufw is installed
        if "active" in ufw_out.lower() and "inactive" not in ufw_out.lower():
            return None  # ufw is active, no finding
        # ufw is inactive — also check iptables before flagging
        iptables_out, iptables_rc = _run(["iptables", "-L", "-n"])
        if iptables_rc != -1 and "policy ACCEPT" in iptables_out:
            # iptables is also permissive
            return Finding(
                id="linux-firewall-disabled",
                severity="high",
                category="security",
                platform="linux",
                title="No active firewall detected",
                detail=(
                    "ufw is installed but inactive, and iptables INPUT chain has a default ACCEPT policy. "
                    "Incoming connections are not being filtered."
                ),
                fix_cmd="sudo ufw enable",
            )
        elif iptables_rc == -1:
            # iptables not available either
            return Finding(
                id="linux-firewall-disabled",
                severity="high",
                category="security",
                platform="linux",
                title="No active firewall detected",
                detail="ufw is installed but inactive and iptables is not available.",
                fix_cmd="sudo ufw enable",
            )
        # iptables has non-ACCEPT policy — firewall is handled elsewhere
        return None
    else:
        # ufw not installed, check iptables
        iptables_out, iptables_rc = _run(["iptables", "-L", "-n"])
        if iptables_rc == -1:
            # Neither ufw nor iptables available
            return Finding(
                id="linux-firewall-disabled",
                severity="high",
                category="security",
                platform="linux",
                title="No active firewall detected",
                detail="Neither ufw nor iptables is available on this system.",
            )
        if "policy ACCEPT" in iptables_out:
            return Finding(
                id="linux-firewall-disabled",
                severity="high",
                category="security",
                platform="linux",
                title="No active firewall detected",
                detail=(
                    "iptables INPUT chain has a default ACCEPT policy. "
                    "Incoming connections are not being filtered."
                ),
            )
        return None


def check_ssh_config() -> Finding | None:
    try:
        with open("/etc/ssh/sshd_config", "r") as f:
            content = f.read()
    except (OSError, PermissionError):
        return None

    # Check for PermitRootLogin yes (case-insensitive, not a comment) — report first
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if re.match(r"(?i)PermitRootLogin\s+yes\b", stripped):
            return Finding(
                id="linux-ssh-permit-root-login",
                severity="high",
                category="security",
                platform="linux",
                title="SSH permits root login",
                detail=(
                    "sshd_config has 'PermitRootLogin yes'. Direct root login over SSH "
                    "allows attackers to compromise the system with a single credential."
                ),
                fix_cmd=(
                    "sed -i 's/^PermitRootLogin yes/PermitRootLogin no/' "
                    "/etc/ssh/sshd_config && systemctl reload sshd"
                ),
            )

    # Check for PasswordAuthentication yes
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if re.match(r"(?i)PasswordAuthentication\s+yes\b", stripped):
            return Finding(
                id="linux-ssh-password-auth",
                severity="medium",
                category="security",
                platform="linux",
                title="SSH allows password authentication",
                detail=(
                    "sshd_config has 'PasswordAuthentication yes'. "
                    "Password-based SSH authentication is vulnerable to brute-force attacks. "
                    "Key-based authentication is strongly preferred."
                ),
                fix_cmd=(
                    "sed -i 's/^PasswordAuthentication yes/PasswordAuthentication no/' "
                    "/etc/ssh/sshd_config && systemctl reload sshd"
                ),
            )

    return None


def check_world_writable() -> Finding | None:
    out, rc = _run(
        ["find", "/etc", "-maxdepth", "2", "-perm", "-o+w", "-type", "f"],
        timeout=20,
    )
    if rc == -1:
        return None
    files = [f for f in out.strip().splitlines() if f.strip()]
    if not files:
        return None
    files = files[:10]
    fix_files = " ".join(files[:3])
    return Finding(
        id="linux-world-writable-etc",
        severity="high",
        category="security",
        platform="linux",
        title=f"{len(files)} world-writable file(s) found in /etc",
        detail=(
            "The following files in /etc are world-writable and could be modified by any user:\n  "
            + "\n  ".join(files)
        ),
        fix_cmd=f"chmod o-w {fix_files}",
    )


def check_fail2ban() -> Finding | None:
    out, rc = _run(["systemctl", "is-active", "fail2ban"])
    if rc == -1:
        return None
    if out.strip() == "active":
        return None
    return Finding(
        id="linux-fail2ban-inactive",
        severity="low",
        category="security",
        platform="linux",
        title="fail2ban is not running",
        detail=(
            "fail2ban monitors log files and bans IPs that show malicious signs "
            "(e.g., too many failed login attempts). It is not currently active."
        ),
        fix_cmd="sudo systemctl enable --now fail2ban",
    )


def check_unattended_upgrades() -> Finding | None:
    # Try dpkg first (Debian/Ubuntu)
    dpkg_out, dpkg_rc = _run(["dpkg", "-l", "unattended-upgrades"])
    if dpkg_rc != -1 and "ii" in dpkg_out:
        return None

    # Try rpm (RHEL/CentOS/Fedora)
    rpm_out, rpm_rc = _run(["rpm", "-q", "unattended-upgrades"])
    if rpm_rc != -1 and rpm_rc == 0:
        return None

    return Finding(
        id="linux-no-unattended-upgrades",
        severity="medium",
        category="misconfiguration",
        platform="linux",
        title="Automatic security updates are not configured",
        detail=(
            "The 'unattended-upgrades' package was not found. "
            "Without automatic security updates, known vulnerabilities may go unpatched."
        ),
        fix_cmd="sudo apt-get install -y unattended-upgrades",
    )


def check_open_ports() -> Finding | None:
    out, rc = _run(["ss", "-tlnp"])
    if rc == -1:
        # Fallback to netstat
        out, rc = _run(["netstat", "-tlnp"])
        if rc == -1:
            return None

    # Ports considered expected/safe
    _safe = {8080, 8443, 3000, 5000, 8000}
    unexpected = []
    for line in out.splitlines():
        # Skip header lines
        if "Local" in line or "Netid" in line or "Proto" in line:
            continue
        # Find address:port patterns
        m = re.search(r'(?:[\*0-9.:]+):(\d+)\s', line)
        if not m:
            continue
        port = int(m.group(1))
        if port > 1023 and port not in _safe:
            # Try to extract process name from ss output: users:(("name",...))
            proc_m = re.search(r'users:\(\("([^"]+)"', line)
            proc = proc_m.group(1) if proc_m else "unknown"
            entry = f"port {port} ({proc})"
            if entry not in unexpected:
                unexpected.append(entry)

    if unexpected:
        return Finding(
            id="linux-open-ports",
            severity="info",
            category="security",
            platform="linux",
            title=f"{len(unexpected)} unexpected port(s) listening",
            detail=(
                "Processes accepting inbound connections on non-standard ports:\n  "
                + "\n  ".join(unexpected[:10])
            ),
        )
    return None


def check_sudo_nopasswd() -> Finding | None:
    out, rc = _run(["grep", "-r", "NOPASSWD", "/etc/sudoers", "/etc/sudoers.d/"])
    if rc == -1:
        return None
    # Filter out comment lines
    matches = [
        line for line in out.strip().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not matches:
        return None
    return Finding(
        id="linux-sudo-nopasswd",
        severity="high",
        category="security",
        platform="linux",
        title="Passwordless sudo (NOPASSWD) is configured",
        detail=(
            "The following sudoers entries allow commands without a password:\n  "
            + "\n  ".join(matches[:10])
        ),
    )


def get_checks() -> list[tuple[str, Callable[[], Finding | None]]]:
    return [
        ("Firewall",              check_firewall),
        ("SSH Config",            check_ssh_config),
        ("World-Writable /etc",   check_world_writable),
        ("fail2ban",              check_fail2ban),
        ("Unattended Upgrades",   check_unattended_upgrades),
        ("Open Ports",            check_open_ports),
        ("Sudo NOPASSWD",         check_sudo_nopasswd),
    ]
