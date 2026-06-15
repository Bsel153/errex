"""Comprehensive unit tests for errex/scanners/macos.py.

All subprocess calls are intercepted by monkeypatching the private
``_run`` helper so tests are self-contained and fast.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from errex.scanners import macos
from errex.scanners._base import Finding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_run(monkeypatch, stdout: str, returncode: int = 0):
    """Replace ``macos._run`` with a callable returning (stdout, returncode)."""
    monkeypatch.setattr(macos, "_run", lambda *a, **kw: (stdout, returncode))


# ---------------------------------------------------------------------------
# check_firewall
# ---------------------------------------------------------------------------

class TestCheckFirewall:
    def test_disabled_output_returns_finding(self, monkeypatch):
        _patch_run(monkeypatch, "Firewall disabled! (State = 0)\n")
        f = macos.check_firewall()
        assert isinstance(f, Finding)
        assert f.id == "macos-firewall-disabled"
        assert f.severity == "high"

    def test_disabled_case_insensitive(self, monkeypatch):
        _patch_run(monkeypatch, "Firewall is DISABLED.\n")
        f = macos.check_firewall()
        assert f is not None
        assert f.id == "macos-firewall-disabled"

    def test_enabled_returns_none(self, monkeypatch):
        _patch_run(monkeypatch, "Firewall is enabled. (State = 1)\n")
        assert macos.check_firewall() is None

    def test_rc_minus1_returns_none(self, monkeypatch):
        _patch_run(monkeypatch, "", returncode=-1)
        assert macos.check_firewall() is None

    def test_rc_minus1_even_with_disabled_text(self, monkeypatch):
        # rc=-1 must short-circuit regardless of content
        _patch_run(monkeypatch, "Firewall disabled", returncode=-1)
        assert macos.check_firewall() is None

    def test_finding_has_fix_cmd(self, monkeypatch):
        _patch_run(monkeypatch, "disabled")
        f = macos.check_firewall()
        assert f is not None
        assert f.fix_cmd is not None
        assert "socketfilterfw" in f.fix_cmd


# ---------------------------------------------------------------------------
# check_sip
# ---------------------------------------------------------------------------

class TestCheckSip:
    def test_enabled_returns_none(self, monkeypatch):
        _patch_run(monkeypatch, "System Integrity Protection status: enabled.\n")
        assert macos.check_sip() is None

    def test_disabled_returns_finding(self, monkeypatch):
        _patch_run(monkeypatch, "System Integrity Protection status: disabled.\n")
        f = macos.check_sip()
        assert isinstance(f, Finding)
        assert f.id == "macos-sip-disabled"
        assert f.severity == "critical"

    def test_disabled_case_insensitive(self, monkeypatch):
        _patch_run(monkeypatch, "System Integrity Protection status: DISABLED.\n")
        f = macos.check_sip()
        assert f is not None

    def test_rc_minus1_returns_none(self, monkeypatch):
        _patch_run(monkeypatch, "System Integrity Protection status: disabled.\n", returncode=-1)
        assert macos.check_sip() is None

    def test_no_fix_cmd_because_recovery_required(self, monkeypatch):
        # SIP can only be re-enabled from Recovery — no automated fix
        _patch_run(monkeypatch, "System Integrity Protection status: disabled.\n")
        f = macos.check_sip()
        assert f is not None
        assert f.fix_cmd is None
        assert f.fix_fn is None


# ---------------------------------------------------------------------------
# check_gatekeeper
# ---------------------------------------------------------------------------

class TestCheckGatekeeper:
    def test_assessments_enabled_returns_none(self, monkeypatch):
        _patch_run(monkeypatch, "assessments enabled\n")
        assert macos.check_gatekeeper() is None

    def test_assessments_disabled_returns_finding(self, monkeypatch):
        _patch_run(monkeypatch, "assessments disabled\n")
        f = macos.check_gatekeeper()
        assert isinstance(f, Finding)
        assert f.id == "macos-gatekeeper-disabled"
        assert f.severity == "high"

    def test_fix_cmd_contains_spctl(self, monkeypatch):
        _patch_run(monkeypatch, "assessments disabled\n")
        f = macos.check_gatekeeper()
        assert f is not None
        assert "spctl" in f.fix_cmd

    def test_rc_minus1_returns_none(self, monkeypatch):
        _patch_run(monkeypatch, "assessments disabled\n", returncode=-1)
        assert macos.check_gatekeeper() is None


# ---------------------------------------------------------------------------
# check_filevault
# ---------------------------------------------------------------------------

class TestCheckFilevault:
    def test_filevault_on_returns_none(self, monkeypatch):
        _patch_run(monkeypatch, "FileVault is On.\n")
        assert macos.check_filevault() is None

    def test_filevault_off_returns_finding(self, monkeypatch):
        _patch_run(monkeypatch, "FileVault is Off.\n")
        f = macos.check_filevault()
        assert isinstance(f, Finding)
        assert f.id == "macos-filevault-off"
        assert f.severity == "medium"

    def test_filevault_off_case_insensitive(self, monkeypatch):
        _patch_run(monkeypatch, "FileVault is OFF.\n")
        f = macos.check_filevault()
        assert f is not None

    def test_filevault_off_no_fix_cmd(self, monkeypatch):
        # Must be enabled manually via System Settings — no CLI shortcut
        _patch_run(monkeypatch, "FileVault is Off.\n")
        f = macos.check_filevault()
        assert f is not None
        assert f.fix_cmd is None

    def test_rc_minus1_returns_none(self, monkeypatch):
        _patch_run(monkeypatch, "FileVault is Off.\n", returncode=-1)
        assert macos.check_filevault() is None


# ---------------------------------------------------------------------------
# check_ssh
# ---------------------------------------------------------------------------

class TestCheckSsh:
    def test_not_running_rc1_returns_none(self, monkeypatch):
        _patch_run(monkeypatch, "", returncode=1)
        assert macos.check_ssh() is None

    def test_running_first_line_not_dash_returns_finding(self, monkeypatch):
        # launchctl list shows PID when service is running
        _patch_run(monkeypatch, "1234\t0\tcom.openssh.sshd\n", returncode=0)
        f = macos.check_ssh()
        assert isinstance(f, Finding)
        assert f.id == "macos-ssh-exposed"
        assert f.severity == "medium"

    def test_running_first_line_dash_returns_none(self, monkeypatch):
        # "-" in first column means not loaded / PID absent
        _patch_run(monkeypatch, "-\t0\tcom.openssh.sshd\n", returncode=0)
        assert macos.check_ssh() is None

    def test_empty_output_rc0_returns_none(self, monkeypatch):
        _patch_run(monkeypatch, "", returncode=0)
        assert macos.check_ssh() is None

    def test_finding_has_fix_cmd(self, monkeypatch):
        _patch_run(monkeypatch, "1234\t0\tcom.openssh.sshd\n", returncode=0)
        f = macos.check_ssh()
        assert f is not None
        assert f.fix_cmd is not None
        assert "launchctl" in f.fix_cmd


# ---------------------------------------------------------------------------
# check_screen_sharing
# ---------------------------------------------------------------------------

class TestCheckScreenSharing:
    def test_not_running_rc1_returns_none(self, monkeypatch):
        _patch_run(monkeypatch, "", returncode=1)
        assert macos.check_screen_sharing() is None

    def test_running_first_line_not_dash_returns_finding(self, monkeypatch):
        _patch_run(monkeypatch, "5678\t0\tcom.apple.screensharing\n", returncode=0)
        f = macos.check_screen_sharing()
        assert isinstance(f, Finding)
        assert f.id == "macos-screensharing-on"
        assert f.severity == "medium"

    def test_running_first_line_dash_returns_none(self, monkeypatch):
        _patch_run(monkeypatch, "-\t0\tcom.apple.screensharing\n", returncode=0)
        assert macos.check_screen_sharing() is None

    def test_finding_has_fix_cmd(self, monkeypatch):
        _patch_run(monkeypatch, "5678\t0\tcom.apple.screensharing\n", returncode=0)
        f = macos.check_screen_sharing()
        assert f is not None
        assert f.fix_cmd is not None


# ---------------------------------------------------------------------------
# check_open_ports
# ---------------------------------------------------------------------------

class TestCheckOpenPorts:
    def test_no_listen_lines_returns_none(self, monkeypatch):
        output = (
            "COMMAND  PID   USER   FD  TYPE DEVICE SIZE/OFF NODE NAME\n"
            "Google   123   user   23u IPv4  12345      0t0  TCP 1.2.3.4:55123->5.6.7.8:443 (ESTABLISHED)\n"
        )
        _patch_run(monkeypatch, output)
        assert macos.check_open_ports() is None

    def test_suspicious_listen_port_returns_finding(self, monkeypatch):
        output = (
            "COMMAND  PID   USER   FD  TYPE DEVICE SIZE/OFF NODE NAME\n"
            "badapp   999   user   10u IPv4  99999      0t0  TCP *:8888 (LISTEN)\n"
        )
        _patch_run(monkeypatch, output)
        f = macos.check_open_ports()
        assert isinstance(f, Finding)
        assert f.id == "macos-open-ports"

    def test_safe_port_not_flagged(self, monkeypatch):
        # Port 443 is in the safe set
        output = (
            "COMMAND  PID USER FD TYPE DEVICE SIZE NODE NAME\n"
            "nginx    100 root  6u IPv4 11111   0t0  TCP *:443 (LISTEN)\n"
        )
        _patch_run(monkeypatch, output)
        assert macos.check_open_ports() is None

    def test_low_port_below_1024_not_flagged(self, monkeypatch):
        # Ports <= 1023 are skipped (privileged)
        output = (
            "COMMAND  PID USER FD TYPE DEVICE SIZE NODE NAME\n"
            "httpd    100 root  6u IPv4 11111   0t0  TCP *:80 (LISTEN)\n"
        )
        _patch_run(monkeypatch, output)
        assert macos.check_open_ports() is None

    def test_rc_minus1_returns_none(self, monkeypatch):
        _patch_run(monkeypatch, "TCP *:8888 (LISTEN)\n", returncode=-1)
        assert macos.check_open_ports() is None

    def test_finding_severity_is_low(self, monkeypatch):
        output = "myapp  42 user 3u IPv4 1 0t0 TCP *:9999 (LISTEN)\n"
        _patch_run(monkeypatch, output)
        f = macos.check_open_ports()
        assert f is not None
        assert f.severity == "low"


# ---------------------------------------------------------------------------
# check_recent_faults
# ---------------------------------------------------------------------------

class TestCheckRecentFaults:
    def _make_output(self, n_fault_lines: int) -> str:
        """Return a log output string with a header line plus n fault lines."""
        header = "Timestamp                       Thread     Type        Activity             PID    TTL\n"
        lines = [f"2026-06-15 00:00:{i:02d} some fault message" for i in range(n_fault_lines)]
        return header + "\n".join(lines)

    def test_zero_fault_lines_returns_none(self, monkeypatch):
        _patch_run(monkeypatch, self._make_output(0))
        assert macos.check_recent_faults() is None

    def test_four_fault_lines_returns_none(self, monkeypatch):
        _patch_run(monkeypatch, self._make_output(4))
        assert macos.check_recent_faults() is None

    def test_five_fault_lines_returns_low_finding(self, monkeypatch):
        _patch_run(monkeypatch, self._make_output(5))
        f = macos.check_recent_faults()
        assert isinstance(f, Finding)
        assert f.severity == "low"

    def test_nineteen_fault_lines_returns_low_finding(self, monkeypatch):
        _patch_run(monkeypatch, self._make_output(19))
        f = macos.check_recent_faults()
        assert f is not None
        assert f.severity == "low"

    def test_twenty_fault_lines_returns_medium_finding(self, monkeypatch):
        _patch_run(monkeypatch, self._make_output(20))
        f = macos.check_recent_faults()
        assert isinstance(f, Finding)
        assert f.severity == "medium"

    def test_many_fault_lines_returns_medium_finding(self, monkeypatch):
        _patch_run(monkeypatch, self._make_output(50))
        f = macos.check_recent_faults()
        assert f is not None
        assert f.severity == "medium"

    def test_rc_minus1_returns_none(self, monkeypatch):
        _patch_run(monkeypatch, self._make_output(30), returncode=-1)
        assert macos.check_recent_faults() is None

    def test_finding_id(self, monkeypatch):
        _patch_run(monkeypatch, self._make_output(5))
        f = macos.check_recent_faults()
        assert f is not None
        assert f.id == "macos-recent-faults"

    def test_finding_title_contains_count(self, monkeypatch):
        _patch_run(monkeypatch, self._make_output(7))
        f = macos.check_recent_faults()
        assert f is not None
        assert "7" in f.title


# ---------------------------------------------------------------------------
# check_auto_update
# ---------------------------------------------------------------------------

class TestCheckAutoUpdate:
    def test_output_zero_returns_finding(self, monkeypatch):
        _patch_run(monkeypatch, "0\n")
        f = macos.check_auto_update()
        assert isinstance(f, Finding)
        assert f.id == "macos-autoupdate-off"
        assert f.severity == "medium"

    def test_output_one_returns_none(self, monkeypatch):
        _patch_run(monkeypatch, "1\n")
        assert macos.check_auto_update() is None

    def test_output_other_returns_none(self, monkeypatch):
        # Anything that isn't exactly "0" should not trigger
        _patch_run(monkeypatch, "2\n")
        assert macos.check_auto_update() is None

    def test_rc_minus1_returns_none(self, monkeypatch):
        _patch_run(monkeypatch, "0\n", returncode=-1)
        assert macos.check_auto_update() is None

    def test_finding_has_fix_fn(self, monkeypatch):
        # Auto-update can be re-enabled via a Python callable
        _patch_run(monkeypatch, "0\n")
        f = macos.check_auto_update()
        assert f is not None
        assert f.fix_fn is not None

    def test_finding_has_fix_cmd(self, monkeypatch):
        _patch_run(monkeypatch, "0\n")
        f = macos.check_auto_update()
        assert f is not None
        assert f.fix_cmd is not None


# ---------------------------------------------------------------------------
# get_checks
# ---------------------------------------------------------------------------

class TestGetChecks:
    def test_returns_nine_tuples(self):
        checks = macos.get_checks()
        assert len(checks) == 9

    def test_each_entry_is_name_callable_pair(self):
        for name, fn in macos.get_checks():
            assert isinstance(name, str), f"Expected str name, got {type(name)}"
            assert callable(fn), f"Expected callable for {name!r}"

    def test_all_expected_names_present(self):
        names = {name for name, _ in macos.get_checks()}
        assert "Firewall"       in names
        assert "SIP"            in names
        assert "Gatekeeper"     in names
        assert "FileVault"      in names
        assert "SSH"            in names
        assert "Screen Sharing" in names
        assert "Open Ports"     in names
        assert "Recent Faults"  in names
        assert "Auto Update"    in names

    def test_callables_are_the_check_functions(self):
        fn_map = {name: fn for name, fn in macos.get_checks()}
        assert fn_map["Firewall"]       is macos.check_firewall
        assert fn_map["SIP"]            is macos.check_sip
        assert fn_map["Gatekeeper"]     is macos.check_gatekeeper
        assert fn_map["FileVault"]      is macos.check_filevault
        assert fn_map["SSH"]            is macos.check_ssh
        assert fn_map["Screen Sharing"] is macos.check_screen_sharing
        assert fn_map["Open Ports"]     is macos.check_open_ports
        assert fn_map["Recent Faults"]  is macos.check_recent_faults
        assert fn_map["Auto Update"]    is macos.check_auto_update
