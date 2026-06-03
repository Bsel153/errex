"""Windows security scanner — subprocess + winreg (built-in on Windows)."""
from __future__ import annotations

import re
import subprocess
from ._base import Finding


def _run(cmd: list[str], timeout: int = 15) -> tuple[str, int]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout + r.stderr, r.returncode
    except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError, OSError):
        return "", -1


def _ps(script: str, timeout: int = 20) -> tuple[str, int]:
    return _run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        timeout=timeout,
    )


def _reg_get(key_path: str, value_name: str) -> object:
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        value, _ = winreg.QueryValueEx(key, value_name)
        winreg.CloseKey(key)
        return value
    except Exception:
        return None


def _reg_set(key_path: str, value_name: str, value: int) -> bool:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, value_name, 0, winreg.REG_DWORD, value)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def check_firewall() -> Finding | None:
    out, rc = _run(["netsh", "advfirewall", "show", "allprofiles"])
    if rc == -1:
        return None
    # Any "State                                 OFF" line means a profile is disabled
    if re.search(r"State\s+OFF", out, re.IGNORECASE):
        return Finding(
            id="win-firewall-disabled",
            severity="high",
            category="security",
            platform="windows",
            title="Windows Firewall is disabled on one or more profiles",
            detail="One or more Windows Firewall profiles (Domain/Private/Public) are turned off.",
            fix_cmd="netsh advfirewall set allprofiles state on",
        )
    return None


def check_defender() -> Finding | None:
    out, rc = _ps("(Get-MpPreference).DisableRealtimeMonitoring")
    if rc == -1 or "True" not in out:
        return None
    return Finding(
        id="win-defender-disabled",
        severity="critical",
        category="security",
        platform="windows",
        title="Windows Defender real-time protection is disabled",
        detail="Real-time protection is the primary defense against malware. It should always be enabled.",
        fix_cmd='powershell -Command "Set-MpPreference -DisableRealtimeMonitoring $false"',
    )


def check_smb1() -> Finding | None:
    out, rc = _ps("(Get-SmbServerConfiguration).EnableSMB1Protocol")
    if rc == -1 or "True" not in out:
        return None
    return Finding(
        id="win-smb1-enabled",
        severity="critical",
        category="security",
        platform="windows",
        title="SMBv1 is enabled",
        detail=(
            "SMBv1 is an obsolete protocol exploited by EternalBlue/WannaCry/NotPetya. "
            "Disable it on all modern Windows systems."
        ),
        fix_cmd='powershell -Command "Set-SmbServerConfiguration -EnableSMB1Protocol $false -Force"',
    )


def check_remote_desktop() -> Finding | None:
    # fDenyTSConnections = 0 means RDP is ENABLED
    val = _reg_get(
        r"System\CurrentControlSet\Control\Terminal Server",
        "fDenyTSConnections",
    )
    if val != 0:
        return None
    return Finding(
        id="win-rdp-exposed",
        severity="medium",
        category="security",
        platform="windows",
        title="Remote Desktop (RDP) is enabled",
        detail="RDP is enabled on port 3389. Brute-force and RDP exploit attacks are extremely common.",
        fix_cmd=r'reg add "HKLM\System\CurrentControlSet\Control\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 1 /f',
        fix_fn=lambda: _reg_set(
            r"System\CurrentControlSet\Control\Terminal Server",
            "fDenyTSConnections", 1,
        ),
    )


def check_guest_account() -> Finding | None:
    out, rc = _run(["net", "user", "guest"])
    if rc == -1:
        return None
    if "Account active" in out and "Yes" in out:
        return Finding(
            id="win-guest-active",
            severity="high",
            category="security",
            platform="windows",
            title="Guest account is active",
            detail="The built-in Guest account is enabled, allowing limited unauthenticated access.",
            fix_cmd="net user guest /active:no",
        )
    return None


def check_autorun() -> Finding | None:
    val = _reg_get(
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer",
        "NoDriveTypeAutoRun",
    )
    # 0xFF (255) = all drives disabled; 0x91 = removable only; None = not set (enabled)
    if val is not None and val >= 0x91:
        return None
    return Finding(
        id="win-autorun-enabled",
        severity="medium",
        category="security",
        platform="windows",
        title="AutoRun is not fully disabled",
        detail="AutoRun can execute malicious code when an infected USB drive or disc is inserted.",
        fix_cmd=r'reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer" /v NoDriveTypeAutoRun /t REG_DWORD /d 255 /f',
        fix_fn=lambda: _reg_set(
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer",
            "NoDriveTypeAutoRun", 0xFF,
        ),
    )


def check_open_ports() -> Finding | None:
    out, rc = _run(["netstat", "-an"])
    if rc == -1:
        return None
    _safe = {80, 135, 139, 443, 445, 3389, 5040, 7680, 49152}
    listening = []
    for line in out.splitlines():
        if "LISTENING" not in line:
            continue
        m = re.search(r'0\.0\.0\.0:(\d+)|:::(\d+)', line)
        if m:
            port = int(m.group(1) or m.group(2))
            if port not in _safe and port < 10000:
                listening.append(f"port {port}")
    if len(listening) > 3:
        return Finding(
            id="win-open-ports",
            severity="low",
            category="security",
            platform="windows",
            title=f"{len(listening)} ports listening on all interfaces",
            detail="Ports accepting connections from any address:\n  " + "\n  ".join(listening[:10]),
        )
    return None


def check_event_log_errors() -> Finding | None:
    out, rc = _run([
        "wevtutil", "qe", "System",
        "/q:*[System[(Level=1 or Level=2) and TimeCreated[timediff(@SystemTime) <= 86400000]]]",
        "/c:20", "/f:Text",
    ], timeout=20)
    if rc == -1:
        return None
    count = out.count("Log Name:")
    if count < 3:
        return None
    severity = "medium" if count >= 10 else "low"
    return Finding(
        id="win-event-log-errors",
        severity=severity,
        category="error",
        platform="windows",
        title=f"{count} critical/error event(s) in System log (last 24h)",
        detail="\n".join(out.splitlines()[:25]),
    )


def get_checks() -> list[tuple[str, callable]]:
    return [
        ("Firewall",          check_firewall),
        ("Windows Defender",  check_defender),
        ("SMBv1",             check_smb1),
        ("Remote Desktop",    check_remote_desktop),
        ("Guest Account",     check_guest_account),
        ("AutoRun",           check_autorun),
        ("Open Ports",        check_open_ports),
        ("Event Log Errors",  check_event_log_errors),
    ]
