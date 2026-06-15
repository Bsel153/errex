"""Comprehensive unit tests for errex/scanners/windows.py.

Running on Linux: `winreg` is unavailable, so `_reg_get` always returns None.
This means:
  - check_remote_desktop() → None  (val is None → val != 0 is True → early return None)
  - check_autorun()        → Finding  (val is None → condition `val is not None and val >= 0x91`
                                       is False → falls through to Finding)

All subprocess calls are intercepted by monkeypatching `errex.scanners.windows._run`
(or `errex.scanners.windows.subprocess.run` where noted).
"""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from errex.scanners import windows
from errex.scanners._base import Finding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_result(stdout: str = "", returncode: int = 0) -> tuple[str, int]:
    """Return value shape that matches windows._run."""
    return stdout, returncode


def _mock_subprocess(stdout: str = "", returncode: int = 0) -> MagicMock:
    """Build a mock suitable for patching subprocess.run inside windows._run."""
    m = MagicMock()
    m.stdout = stdout
    m.stderr = ""
    m.returncode = returncode
    return m


# ---------------------------------------------------------------------------
# check_firewall
# ---------------------------------------------------------------------------

class TestCheckFirewall:
    def test_state_off_returns_high_finding(self, monkeypatch):
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result(
                "Domain Profile:\nState                                 OFF\n"
            ),
        )
        f = windows.check_firewall()
        assert f is not None
        assert f.id == "win-firewall-disabled"
        assert f.severity == "high"

    def test_state_off_case_insensitive(self, monkeypatch):
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result(
                "State\t\t\toff\n"
            ),
        )
        f = windows.check_firewall()
        assert f is not None
        assert f.id == "win-firewall-disabled"

    def test_state_on_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result(
                "Domain Profile:\nState                                 ON\n"
            ),
        )
        assert windows.check_firewall() is None

    def test_rc_minus_one_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result("", -1),
        )
        assert windows.check_firewall() is None

    def test_empty_output_returns_none(self, monkeypatch):
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result(""))
        assert windows.check_firewall() is None

    def test_finding_has_fix_cmd(self, monkeypatch):
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result("State  OFF"),
        )
        f = windows.check_firewall()
        assert f is not None
        assert f.fix_cmd is not None
        assert "netsh" in f.fix_cmd

    def test_finding_platform_is_windows(self, monkeypatch):
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result("State  OFF"),
        )
        f = windows.check_firewall()
        assert f is not None
        assert f.platform == "windows"

    def test_multiple_profiles_only_one_off_returns_finding(self, monkeypatch):
        output = (
            "Domain Profile:\nState  ON\n"
            "Private Profile:\nState  OFF\n"
            "Public Profile:\nState  ON\n"
        )
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result(output))
        f = windows.check_firewall()
        assert f is not None
        assert f.id == "win-firewall-disabled"


# ---------------------------------------------------------------------------
# check_defender
# ---------------------------------------------------------------------------

class TestCheckDefender:
    def test_true_in_output_returns_critical_finding(self, monkeypatch):
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result("True\n"))
        f = windows.check_defender()
        assert f is not None
        assert f.id == "win-defender-disabled"
        assert f.severity == "critical"

    def test_true_mixed_case_in_output(self, monkeypatch):
        # PowerShell output is always "True" or "False"; test exact casing
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result("True\r\n"))
        f = windows.check_defender()
        assert f is not None

    def test_false_in_output_returns_none(self, monkeypatch):
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result("False\n"))
        assert windows.check_defender() is None

    def test_rc_minus_one_returns_none(self, monkeypatch):
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result("True\n", -1))
        assert windows.check_defender() is None

    def test_empty_output_returns_none(self, monkeypatch):
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result(""))
        assert windows.check_defender() is None

    def test_finding_has_powershell_fix_cmd(self, monkeypatch):
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result("True\n"))
        f = windows.check_defender()
        assert f is not None
        assert f.fix_cmd is not None
        assert "powershell" in f.fix_cmd.lower() or "Set-MpPreference" in f.fix_cmd

    def test_finding_platform_is_windows(self, monkeypatch):
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result("True\n"))
        f = windows.check_defender()
        assert f is not None
        assert f.platform == "windows"

    def test_output_with_true_embedded_returns_finding(self, monkeypatch):
        # "True" appearing in output among other text
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result("DisableRealtimeMonitoring : True\n"),
        )
        f = windows.check_defender()
        assert f is not None


# ---------------------------------------------------------------------------
# check_smb1
# ---------------------------------------------------------------------------

class TestCheckSmb1:
    def test_true_in_output_returns_critical_finding(self, monkeypatch):
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result("True\n"))
        f = windows.check_smb1()
        assert f is not None
        assert f.id == "win-smb1-enabled"
        assert f.severity == "critical"

    def test_false_in_output_returns_none(self, monkeypatch):
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result("False\n"))
        assert windows.check_smb1() is None

    def test_rc_minus_one_returns_none(self, monkeypatch):
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result("True\n", -1))
        assert windows.check_smb1() is None

    def test_empty_output_returns_none(self, monkeypatch):
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result(""))
        assert windows.check_smb1() is None

    def test_finding_mentions_smb1_disable_in_fix_cmd(self, monkeypatch):
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result("True\n"))
        f = windows.check_smb1()
        assert f is not None
        assert f.fix_cmd is not None
        assert "SMB1" in f.fix_cmd or "smb1" in f.fix_cmd.lower()

    def test_finding_platform_is_windows(self, monkeypatch):
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result("True\n"))
        f = windows.check_smb1()
        assert f is not None
        assert f.platform == "windows"

    def test_cve_context_in_detail(self, monkeypatch):
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result("True\n"))
        f = windows.check_smb1()
        assert f is not None
        # The detail should mention a known exploit family
        detail_lower = f.detail.lower()
        assert any(k in detail_lower for k in ("wannacry", "eternalblue", "notpetya", "smb"))


# ---------------------------------------------------------------------------
# check_remote_desktop
# ---------------------------------------------------------------------------

class TestCheckRemoteDesktop:
    def test_on_linux_winreg_unavailable_returns_none(self):
        # On Linux, _reg_get raises ImportError → returns None → val != 0 → returns None
        result = windows.check_remote_desktop()
        assert result is None

    def test_val_zero_rdp_enabled_returns_medium_finding(self):
        with patch("errex.scanners.windows._reg_get", return_value=0):
            f = windows.check_remote_desktop()
        assert f is not None
        assert f.id == "win-rdp-exposed"
        assert f.severity == "medium"

    def test_val_one_rdp_disabled_returns_none(self):
        with patch("errex.scanners.windows._reg_get", return_value=1):
            assert windows.check_remote_desktop() is None

    def test_val_none_from_reg_returns_none(self):
        # val=None → val != 0 is True → returns None
        with patch("errex.scanners.windows._reg_get", return_value=None):
            assert windows.check_remote_desktop() is None

    def test_finding_has_fix_fn(self):
        with patch("errex.scanners.windows._reg_get", return_value=0):
            f = windows.check_remote_desktop()
        assert f is not None
        assert f.fix_fn is not None
        assert callable(f.fix_fn)

    def test_finding_has_reg_fix_cmd(self):
        with patch("errex.scanners.windows._reg_get", return_value=0):
            f = windows.check_remote_desktop()
        assert f is not None
        assert f.fix_cmd is not None
        assert "fDenyTSConnections" in f.fix_cmd

    def test_finding_platform_is_windows(self):
        with patch("errex.scanners.windows._reg_get", return_value=0):
            f = windows.check_remote_desktop()
        assert f is not None
        assert f.platform == "windows"

    def test_val_two_nonzero_returns_none(self):
        with patch("errex.scanners.windows._reg_get", return_value=2):
            assert windows.check_remote_desktop() is None


# ---------------------------------------------------------------------------
# check_guest_account
# ---------------------------------------------------------------------------

class TestCheckGuestAccount:
    def test_guest_active_yes_returns_high_finding(self, monkeypatch):
        output = "User name                    Guest\nAccount active               Yes\n"
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result(output))
        f = windows.check_guest_account()
        assert f is not None
        assert f.id == "win-guest-active"
        assert f.severity == "high"

    def test_guest_active_no_returns_none(self, monkeypatch):
        output = "User name                    Guest\nAccount active               No\n"
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result(output))
        assert windows.check_guest_account() is None

    def test_rc_minus_one_returns_none(self, monkeypatch):
        output = "Account active               Yes\n"
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result(output, -1))
        assert windows.check_guest_account() is None

    def test_empty_output_returns_none(self, monkeypatch):
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result(""))
        assert windows.check_guest_account() is None

    def test_account_active_but_no_yes_returns_none(self, monkeypatch):
        output = "Account active               \n"
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result(output))
        assert windows.check_guest_account() is None

    def test_yes_without_account_active_returns_none(self, monkeypatch):
        output = "Some other field             Yes\n"
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result(output))
        assert windows.check_guest_account() is None

    def test_finding_has_net_user_fix_cmd(self, monkeypatch):
        output = "Account active               Yes\n"
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result(output))
        f = windows.check_guest_account()
        assert f is not None
        assert f.fix_cmd is not None
        assert "net user guest" in f.fix_cmd

    def test_finding_platform_is_windows(self, monkeypatch):
        output = "Account active               Yes\n"
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result(output))
        f = windows.check_guest_account()
        assert f is not None
        assert f.platform == "windows"


# ---------------------------------------------------------------------------
# check_autorun
# ---------------------------------------------------------------------------

class TestCheckAutorun:
    def test_on_linux_reg_get_returns_none_yields_finding(self):
        # On Linux, _reg_get → None → condition is False → Finding returned
        f = windows.check_autorun()
        assert f is not None
        assert f.id == "win-autorun-enabled"
        assert f.severity == "medium"

    def test_val_none_yields_finding(self):
        with patch("errex.scanners.windows._reg_get", return_value=None):
            f = windows.check_autorun()
        assert f is not None
        assert f.id == "win-autorun-enabled"

    def test_val_0xff_all_drives_disabled_returns_none(self):
        with patch("errex.scanners.windows._reg_get", return_value=0xFF):
            assert windows.check_autorun() is None

    def test_val_0x91_removable_disabled_returns_none(self):
        with patch("errex.scanners.windows._reg_get", return_value=0x91):
            assert windows.check_autorun() is None

    def test_val_above_0x91_returns_none(self):
        with patch("errex.scanners.windows._reg_get", return_value=0xA0):
            assert windows.check_autorun() is None

    def test_val_below_0x91_yields_finding(self):
        with patch("errex.scanners.windows._reg_get", return_value=0x10):
            f = windows.check_autorun()
        assert f is not None
        assert f.id == "win-autorun-enabled"

    def test_val_zero_yields_finding(self):
        with patch("errex.scanners.windows._reg_get", return_value=0):
            f = windows.check_autorun()
        assert f is not None

    def test_finding_has_fix_fn(self):
        with patch("errex.scanners.windows._reg_get", return_value=None):
            f = windows.check_autorun()
        assert f is not None
        assert f.fix_fn is not None
        assert callable(f.fix_fn)

    def test_finding_has_reg_add_fix_cmd(self):
        with patch("errex.scanners.windows._reg_get", return_value=None):
            f = windows.check_autorun()
        assert f is not None
        assert f.fix_cmd is not None
        assert "NoDriveTypeAutoRun" in f.fix_cmd

    def test_finding_platform_is_windows(self):
        f = windows.check_autorun()
        assert f is not None
        assert f.platform == "windows"


# ---------------------------------------------------------------------------
# check_open_ports
# ---------------------------------------------------------------------------

# Build a helper that produces netstat-like output with N unique non-safe LISTENING ports.
_SAFE_PORTS = {80, 135, 139, 443, 445, 3389, 5040, 7680, 49152}


def _netstat_output(*ports: int) -> str:
    lines = ["Active Connections", ""]
    for p in ports:
        lines.append(f"  TCP    0.0.0.0:{p}             0.0.0.0:0              LISTENING")
    return "\n".join(lines)


def _unsafe_ports(n: int) -> list[int]:
    """Return n unique unsafe ports (low, non-safe)."""
    result = []
    p = 1024
    while len(result) < n:
        if p not in _SAFE_PORTS and p < 10000:
            result.append(p)
        p += 1
    return result


class TestCheckOpenPorts:
    def test_four_unsafe_ports_returns_low_finding(self, monkeypatch):
        ports = _unsafe_ports(4)
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result(_netstat_output(*ports)),
        )
        f = windows.check_open_ports()
        assert f is not None
        assert f.id == "win-open-ports"
        assert f.severity == "low"

    def test_ten_unsafe_ports_returns_finding_with_count(self, monkeypatch):
        ports = _unsafe_ports(10)
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result(_netstat_output(*ports)),
        )
        f = windows.check_open_ports()
        assert f is not None
        assert "10" in f.title

    def test_three_unsafe_ports_returns_none(self, monkeypatch):
        ports = _unsafe_ports(3)
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result(_netstat_output(*ports)),
        )
        assert windows.check_open_ports() is None

    def test_zero_unsafe_ports_returns_none(self, monkeypatch):
        # Only safe ports listening
        safe_output = _netstat_output(80, 443, 135)
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result(safe_output))
        assert windows.check_open_ports() is None

    def test_rc_minus_one_returns_none(self, monkeypatch):
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result("", -1))
        assert windows.check_open_ports() is None

    def test_empty_output_returns_none(self, monkeypatch):
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result(""))
        assert windows.check_open_ports() is None

    def test_high_port_numbers_excluded(self, monkeypatch):
        # Ports >= 10000 are excluded from the count
        output = "\n".join(
            f"  TCP    0.0.0.0:{p}    0.0.0.0:0    LISTENING"
            for p in [10000, 11000, 12000, 13000, 14000]
        )
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result(output))
        assert windows.check_open_ports() is None

    def test_safe_ports_not_counted(self, monkeypatch):
        # 4 safe ports should NOT trigger a finding
        safe_output = _netstat_output(80, 443, 135, 139)
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result(safe_output))
        assert windows.check_open_ports() is None

    def test_ipv6_any_address_also_detected(self, monkeypatch):
        output = "\n".join(
            f"  TCP    :::{p}    :::0    LISTENING"
            for p in _unsafe_ports(4)
        )
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result(output))
        f = windows.check_open_ports()
        assert f is not None

    def test_non_listening_lines_ignored(self, monkeypatch):
        output = "\n".join(
            f"  TCP    0.0.0.0:{p}    192.168.1.1:80    ESTABLISHED"
            for p in _unsafe_ports(10)
        )
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result(output))
        assert windows.check_open_ports() is None

    def test_finding_platform_is_windows(self, monkeypatch):
        ports = _unsafe_ports(4)
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result(_netstat_output(*ports)),
        )
        f = windows.check_open_ports()
        assert f is not None
        assert f.platform == "windows"

    def test_exactly_four_unsafe_ports_triggers_finding(self, monkeypatch):
        ports = _unsafe_ports(4)
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result(_netstat_output(*ports)),
        )
        f = windows.check_open_ports()
        assert f is not None

    def test_detail_lists_ports(self, monkeypatch):
        ports = _unsafe_ports(4)
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result(_netstat_output(*ports)),
        )
        f = windows.check_open_ports()
        assert f is not None
        assert "port" in f.detail


# ---------------------------------------------------------------------------
# check_event_log_errors
# ---------------------------------------------------------------------------

def _event_log_output(count: int) -> str:
    """Generate wevtutil-like output with `count` occurrences of 'Log Name:'."""
    block = "Log Name:      System\nSource:        EventLog\nLevel:         Error\n\n"
    return block * count


class TestCheckEventLogErrors:
    def test_ten_log_entries_returns_medium_finding(self, monkeypatch):
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result(_event_log_output(10)),
        )
        f = windows.check_event_log_errors()
        assert f is not None
        assert f.id == "win-event-log-errors"
        assert f.severity == "medium"

    def test_fifteen_log_entries_returns_medium_finding(self, monkeypatch):
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result(_event_log_output(15)),
        )
        f = windows.check_event_log_errors()
        assert f is not None
        assert f.severity == "medium"

    def test_five_log_entries_returns_low_finding(self, monkeypatch):
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result(_event_log_output(5)),
        )
        f = windows.check_event_log_errors()
        assert f is not None
        assert f.id == "win-event-log-errors"
        assert f.severity == "low"

    def test_three_log_entries_returns_low_finding(self, monkeypatch):
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result(_event_log_output(3)),
        )
        f = windows.check_event_log_errors()
        assert f is not None
        assert f.severity == "low"

    def test_nine_log_entries_returns_low_finding(self, monkeypatch):
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result(_event_log_output(9)),
        )
        f = windows.check_event_log_errors()
        assert f is not None
        assert f.severity == "low"

    def test_two_log_entries_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result(_event_log_output(2)),
        )
        assert windows.check_event_log_errors() is None

    def test_zero_log_entries_returns_none(self, monkeypatch):
        monkeypatch.setattr(windows, "_run", lambda *a, **kw: _run_result(""))
        assert windows.check_event_log_errors() is None

    def test_rc_minus_one_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result(_event_log_output(20), -1),
        )
        assert windows.check_event_log_errors() is None

    def test_finding_title_contains_count(self, monkeypatch):
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result(_event_log_output(10)),
        )
        f = windows.check_event_log_errors()
        assert f is not None
        assert "10" in f.title

    def test_finding_platform_is_windows(self, monkeypatch):
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result(_event_log_output(5)),
        )
        f = windows.check_event_log_errors()
        assert f is not None
        assert f.platform == "windows"

    def test_finding_category_is_error(self, monkeypatch):
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result(_event_log_output(5)),
        )
        f = windows.check_event_log_errors()
        assert f is not None
        assert f.category == "error"

    def test_boundary_exactly_10_is_medium(self, monkeypatch):
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result(_event_log_output(10)),
        )
        f = windows.check_event_log_errors()
        assert f is not None
        assert f.severity == "medium"

    def test_boundary_exactly_3_is_low(self, monkeypatch):
        monkeypatch.setattr(
            windows, "_run",
            lambda *a, **kw: _run_result(_event_log_output(3)),
        )
        f = windows.check_event_log_errors()
        assert f is not None
        assert f.severity == "low"


# ---------------------------------------------------------------------------
# get_checks
# ---------------------------------------------------------------------------

class TestGetChecks:
    def test_returns_list_of_tuples(self):
        checks = windows.get_checks()
        assert isinstance(checks, list)

    def test_returns_exactly_eight_checks(self):
        checks = windows.get_checks()
        assert len(checks) == 8

    def test_all_entries_are_two_tuples(self):
        for entry in windows.get_checks():
            assert len(entry) == 2

    def test_first_element_is_string(self):
        for name, _ in windows.get_checks():
            assert isinstance(name, str)
            assert len(name) > 0

    def test_second_element_is_callable(self):
        for _, fn in windows.get_checks():
            assert callable(fn)

    def test_check_names_are_unique(self):
        names = [name for name, _ in windows.get_checks()]
        assert len(names) == len(set(names))

    def test_expected_check_functions_present(self):
        fns = {fn for _, fn in windows.get_checks()}
        assert windows.check_firewall in fns
        assert windows.check_defender in fns
        assert windows.check_smb1 in fns
        assert windows.check_remote_desktop in fns
        assert windows.check_guest_account in fns
        assert windows.check_autorun in fns
        assert windows.check_open_ports in fns
        assert windows.check_event_log_errors in fns

    def test_expected_names_present(self):
        names = {name for name, _ in windows.get_checks()}
        assert "Firewall" in names
        assert "Windows Defender" in names
        assert "SMBv1" in names
        assert "Remote Desktop" in names
        assert "Guest Account" in names
        assert "AutoRun" in names
        assert "Open Ports" in names
        assert "Event Log Errors" in names


# ---------------------------------------------------------------------------
# _run helper (subprocess integration)
# ---------------------------------------------------------------------------

class TestRunHelper:
    @patch("errex.scanners.windows.subprocess.run")
    def test_returns_combined_stdout_stderr(self, mock_subproc):
        mock_subproc.return_value = _mock_subprocess("out", returncode=0)
        mock_subproc.return_value.stderr = "err"
        out, rc = windows._run(["cmd"])
        assert "out" in out
        assert rc == 0

    @patch("errex.scanners.windows.subprocess.run")
    def test_file_not_found_returns_minus_one(self, mock_subproc):
        mock_subproc.side_effect = FileNotFoundError
        out, rc = windows._run(["nonexistent"])
        assert rc == -1
        assert out == ""

    @patch("errex.scanners.windows.subprocess.run")
    def test_timeout_returns_minus_one(self, mock_subproc):
        mock_subproc.side_effect = subprocess.TimeoutExpired(cmd=["cmd"], timeout=5)
        out, rc = windows._run(["cmd"])
        assert rc == -1

    @patch("errex.scanners.windows.subprocess.run")
    def test_permission_error_returns_minus_one(self, mock_subproc):
        mock_subproc.side_effect = PermissionError
        out, rc = windows._run(["cmd"])
        assert rc == -1

    @patch("errex.scanners.windows.subprocess.run")
    def test_os_error_returns_minus_one(self, mock_subproc):
        mock_subproc.side_effect = OSError
        out, rc = windows._run(["cmd"])
        assert rc == -1


# ---------------------------------------------------------------------------
# _reg_get helper (Linux: always returns None)
# ---------------------------------------------------------------------------

class TestRegGetOnLinux:
    def test_reg_get_returns_none_on_linux(self):
        # winreg is not available on Linux, so ImportError → returns None
        result = windows._reg_get(
            r"System\CurrentControlSet\Control\Terminal Server",
            "fDenyTSConnections",
        )
        assert result is None

    def test_reg_get_any_path_returns_none_on_linux(self):
        result = windows._reg_get(
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer",
            "NoDriveTypeAutoRun",
        )
        assert result is None
