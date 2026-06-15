"""Comprehensive unit tests for errex/scanners/linux.py."""
from __future__ import annotations

from unittest.mock import mock_open, patch

import pytest

import errex.scanners.linux as linux_module
from errex.scanners._base import Finding
from errex.scanners.linux import (
    check_fail2ban,
    check_firewall,
    check_open_ports,
    check_ssh_config,
    check_sudo_nopasswd,
    check_unattended_upgrades,
    check_world_writable,
    get_checks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run(mapping: dict[tuple, tuple[str, int]]):
    """Return a fake _run() that dispatches on the first token of the command."""
    def fake_run(cmd, timeout=15):
        key = tuple(cmd[:2])  # e.g. ("ufw", "status") or ("iptables", "-L")
        # Try progressively shorter prefixes
        for length in (len(cmd), 2, 1):
            k = tuple(cmd[:length])
            if k in mapping:
                return mapping[k]
        # Also try first-element-only key
        k1 = (cmd[0],)
        if k1 in mapping:
            return mapping[k1]
        return ("", -1)
    return fake_run


# ---------------------------------------------------------------------------
# check_firewall
# ---------------------------------------------------------------------------

class TestCheckFirewall:

    def test_ufw_active_returns_none(self, monkeypatch):
        """ufw active → no finding."""
        def fake_run(cmd, timeout=15):
            if cmd[0] == "ufw":
                return ("Status: active\n", 0)
            return ("", -1)
        monkeypatch.setattr(linux_module, "_run", fake_run)
        assert check_firewall() is None

    def test_ufw_inactive_iptables_accept_returns_finding(self, monkeypatch):
        """ufw inactive + iptables ACCEPT policy → Finding."""
        def fake_run(cmd, timeout=15):
            if cmd[0] == "ufw":
                return ("Status: inactive\n", 0)
            if cmd[0] == "iptables":
                return ("Chain INPUT (policy ACCEPT)\nChain FORWARD (policy ACCEPT)\n", 0)
            return ("", -1)
        monkeypatch.setattr(linux_module, "_run", fake_run)
        finding = check_firewall()
        assert isinstance(finding, Finding)
        assert finding.id == "linux-firewall-disabled"
        assert finding.severity == "high"
        assert finding.fix_cmd == "sudo ufw enable"

    def test_ufw_inactive_iptables_restrictive_returns_none(self, monkeypatch):
        """ufw inactive but iptables has a non-ACCEPT policy → None."""
        def fake_run(cmd, timeout=15):
            if cmd[0] == "ufw":
                return ("Status: inactive\n", 0)
            if cmd[0] == "iptables":
                return ("Chain INPUT (policy DROP)\n", 0)
            return ("", -1)
        monkeypatch.setattr(linux_module, "_run", fake_run)
        assert check_firewall() is None

    def test_ufw_inactive_iptables_not_installed_returns_finding(self, monkeypatch):
        """ufw inactive + iptables not available → Finding."""
        def fake_run(cmd, timeout=15):
            if cmd[0] == "ufw":
                return ("Status: inactive\n", 0)
            # iptables not found
            return ("", -1)
        monkeypatch.setattr(linux_module, "_run", fake_run)
        finding = check_firewall()
        assert isinstance(finding, Finding)
        assert finding.id == "linux-firewall-disabled"
        assert finding.severity == "high"
        assert "iptables is not available" in finding.detail

    def test_ufw_not_installed_iptables_accept_returns_finding(self, monkeypatch):
        """ufw not found + iptables ACCEPT → Finding (no fix_cmd because ufw not present)."""
        def fake_run(cmd, timeout=15):
            if cmd[0] == "ufw":
                return ("", -1)
            if cmd[0] == "iptables":
                return ("Chain INPUT (policy ACCEPT)\n", 0)
            return ("", -1)
        monkeypatch.setattr(linux_module, "_run", fake_run)
        finding = check_firewall()
        assert isinstance(finding, Finding)
        assert finding.id == "linux-firewall-disabled"
        assert finding.severity == "high"

    def test_ufw_not_installed_iptables_not_installed_returns_finding(self, monkeypatch):
        """Neither ufw nor iptables → Finding."""
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: ("", -1))
        finding = check_firewall()
        assert isinstance(finding, Finding)
        assert finding.id == "linux-firewall-disabled"
        assert finding.severity == "high"
        assert "Neither ufw nor iptables" in finding.detail

    def test_ufw_not_installed_iptables_restrictive_returns_none(self, monkeypatch):
        """ufw not found + iptables restrictive → None."""
        def fake_run(cmd, timeout=15):
            if cmd[0] == "ufw":
                return ("", -1)
            if cmd[0] == "iptables":
                return ("Chain INPUT (policy DROP)\n", 0)
            return ("", -1)
        monkeypatch.setattr(linux_module, "_run", fake_run)
        assert check_firewall() is None

    def test_finding_has_correct_metadata(self, monkeypatch):
        """Finding carries expected category and platform."""
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: ("", -1))
        finding = check_firewall()
        assert finding.category == "security"
        assert finding.platform == "linux"


# ---------------------------------------------------------------------------
# check_ssh_config
# ---------------------------------------------------------------------------

class TestCheckSshConfig:

    def test_permit_root_login_yes_returns_finding(self):
        """PermitRootLogin yes triggers a high-severity finding."""
        config = "PermitRootLogin yes\nPasswordAuthentication no\n"
        with patch("builtins.open", mock_open(read_data=config)):
            finding = check_ssh_config()
        assert isinstance(finding, Finding)
        assert finding.id == "linux-ssh-permit-root-login"
        assert finding.severity == "high"
        assert finding.fix_cmd is not None

    def test_permit_root_login_case_insensitive(self):
        """PermitRootLogin matching is case-insensitive."""
        config = "permitrootlogin YES\n"
        with patch("builtins.open", mock_open(read_data=config)):
            finding = check_ssh_config()
        assert isinstance(finding, Finding)
        assert finding.id == "linux-ssh-permit-root-login"

    def test_commented_permit_root_login_returns_none(self):
        """Commented-out PermitRootLogin yes should not trigger a finding."""
        config = "#PermitRootLogin yes\nPasswordAuthentication no\n"
        with patch("builtins.open", mock_open(read_data=config)):
            assert check_ssh_config() is None

    def test_password_auth_yes_returns_finding(self):
        """PasswordAuthentication yes triggers a medium-severity finding."""
        config = "PermitRootLogin no\nPasswordAuthentication yes\n"
        with patch("builtins.open", mock_open(read_data=config)):
            finding = check_ssh_config()
        assert isinstance(finding, Finding)
        assert finding.id == "linux-ssh-password-auth"
        assert finding.severity == "medium"
        assert finding.fix_cmd is not None

    def test_password_auth_case_insensitive(self):
        """PasswordAuthentication matching is case-insensitive."""
        config = "passwordauthentication YES\n"
        with patch("builtins.open", mock_open(read_data=config)):
            finding = check_ssh_config()
        assert isinstance(finding, Finding)
        assert finding.id == "linux-ssh-password-auth"

    def test_commented_password_auth_returns_none(self):
        """Commented-out PasswordAuthentication yes should not trigger a finding."""
        config = "# PasswordAuthentication yes\n"
        with patch("builtins.open", mock_open(read_data=config)):
            assert check_ssh_config() is None

    def test_file_not_found_returns_none(self):
        """OSError when opening config file → None."""
        with patch("builtins.open", side_effect=OSError("no such file")):
            assert check_ssh_config() is None

    def test_permission_error_returns_none(self):
        """PermissionError when opening config file → None."""
        with patch("builtins.open", side_effect=PermissionError("permission denied")):
            assert check_ssh_config() is None

    def test_clean_config_returns_none(self):
        """A config with safe settings returns None."""
        config = (
            "PermitRootLogin no\n"
            "PasswordAuthentication no\n"
            "PubkeyAuthentication yes\n"
        )
        with patch("builtins.open", mock_open(read_data=config)):
            assert check_ssh_config() is None

    def test_permit_root_login_takes_priority_over_password_auth(self):
        """When both issues present, PermitRootLogin finding is returned first."""
        config = "PermitRootLogin yes\nPasswordAuthentication yes\n"
        with patch("builtins.open", mock_open(read_data=config)):
            finding = check_ssh_config()
        assert finding.id == "linux-ssh-permit-root-login"

    def test_finding_metadata(self):
        """SSH findings carry expected platform and category."""
        config = "PermitRootLogin yes\n"
        with patch("builtins.open", mock_open(read_data=config)):
            finding = check_ssh_config()
        assert finding.platform == "linux"
        assert finding.category == "security"


# ---------------------------------------------------------------------------
# check_world_writable
# ---------------------------------------------------------------------------

class TestCheckWorldWritable:

    def test_no_files_returns_none(self, monkeypatch):
        """find returns no output → None."""
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: ("", 0))
        assert check_world_writable() is None

    def test_files_found_returns_finding(self, monkeypatch):
        """find returns writable files → Finding."""
        monkeypatch.setattr(
            linux_module, "_run",
            lambda cmd, timeout=15: ("/etc/foo.conf\n/etc/bar.conf\n", 0),
        )
        finding = check_world_writable()
        assert isinstance(finding, Finding)
        assert finding.id == "linux-world-writable-etc"
        assert finding.severity == "high"
        assert finding.fix_cmd is not None
        assert "chmod" in finding.fix_cmd

    def test_finding_lists_file_names(self, monkeypatch):
        """The finding detail contains the offending file paths."""
        monkeypatch.setattr(
            linux_module, "_run",
            lambda cmd, timeout=15: ("/etc/danger\n", 0),
        )
        finding = check_world_writable()
        assert "/etc/danger" in finding.detail

    def test_capped_at_ten_files(self, monkeypatch):
        """Only the first 10 files are included even if more are found."""
        many_files = "\n".join(f"/etc/file{i}" for i in range(20))
        monkeypatch.setattr(
            linux_module, "_run",
            lambda cmd, timeout=15: (many_files, 0),
        )
        finding = check_world_writable()
        # Title mentions at most 10
        assert int(finding.title.split()[0]) <= 10

    def test_find_not_available_returns_none(self, monkeypatch):
        """find returns rc=-1 (not available) → None."""
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: ("", -1))
        assert check_world_writable() is None

    def test_finding_metadata(self, monkeypatch):
        monkeypatch.setattr(
            linux_module, "_run",
            lambda cmd, timeout=15: ("/etc/writable\n", 0),
        )
        finding = check_world_writable()
        assert finding.category == "security"
        assert finding.platform == "linux"


# ---------------------------------------------------------------------------
# check_fail2ban
# ---------------------------------------------------------------------------

class TestCheckFail2ban:

    def test_active_returns_none(self, monkeypatch):
        """systemctl reports active → None."""
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: ("active\n", 0))
        assert check_fail2ban() is None

    def test_inactive_returns_finding(self, monkeypatch):
        """systemctl reports inactive → Finding."""
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: ("inactive\n", 3))
        finding = check_fail2ban()
        assert isinstance(finding, Finding)
        assert finding.id == "linux-fail2ban-inactive"
        assert finding.severity == "low"

    def test_inactive_finding_has_fix_cmd(self, monkeypatch):
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: ("inactive\n", 3))
        finding = check_fail2ban()
        assert finding.fix_cmd is not None
        assert "fail2ban" in finding.fix_cmd

    def test_systemctl_not_found_returns_none(self, monkeypatch):
        """systemctl unavailable (rc=-1) → None."""
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: ("", -1))
        assert check_fail2ban() is None

    def test_unexpected_output_returns_finding(self, monkeypatch):
        """Any output other than 'active' triggers a finding."""
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: ("failed\n", 0))
        finding = check_fail2ban()
        assert isinstance(finding, Finding)
        assert finding.id == "linux-fail2ban-inactive"

    def test_finding_metadata(self, monkeypatch):
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: ("inactive\n", 3))
        finding = check_fail2ban()
        assert finding.category == "security"
        assert finding.platform == "linux"


# ---------------------------------------------------------------------------
# check_unattended_upgrades
# ---------------------------------------------------------------------------

class TestCheckUnattendedUpgrades:

    def test_dpkg_installed_returns_none(self, monkeypatch):
        """dpkg shows 'ii unattended-upgrades' → None."""
        def fake_run(cmd, timeout=15):
            if cmd[0] == "dpkg":
                return ("ii  unattended-upgrades  2.8  all\n", 0)
            return ("", -1)
        monkeypatch.setattr(linux_module, "_run", fake_run)
        assert check_unattended_upgrades() is None

    def test_rpm_installed_returns_none(self, monkeypatch):
        """dpkg not found, rpm exit 0 → None."""
        def fake_run(cmd, timeout=15):
            if cmd[0] == "dpkg":
                return ("", -1)
            if cmd[0] == "rpm":
                return ("unattended-upgrades-2.0\n", 0)
            return ("", -1)
        monkeypatch.setattr(linux_module, "_run", fake_run)
        assert check_unattended_upgrades() is None

    def test_dpkg_not_installed_rpm_not_found_returns_finding(self, monkeypatch):
        """Both dpkg and rpm unavailable → Finding."""
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: ("", -1))
        finding = check_unattended_upgrades()
        assert isinstance(finding, Finding)
        assert finding.id == "linux-no-unattended-upgrades"
        assert finding.severity == "medium"

    def test_dpkg_rc_ok_but_no_ii_marker_then_rpm_not_found_returns_finding(self, monkeypatch):
        """dpkg runs OK but 'ii' not in output, rpm also not found → Finding."""
        def fake_run(cmd, timeout=15):
            if cmd[0] == "dpkg":
                # package not installed, dpkg exits 1
                return ("no packages found matching unattended-upgrades\n", 1)
            return ("", -1)
        monkeypatch.setattr(linux_module, "_run", fake_run)
        finding = check_unattended_upgrades()
        assert isinstance(finding, Finding)
        assert finding.id == "linux-no-unattended-upgrades"

    def test_finding_has_fix_cmd(self, monkeypatch):
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: ("", -1))
        finding = check_unattended_upgrades()
        assert finding.fix_cmd is not None
        assert "apt" in finding.fix_cmd

    def test_finding_metadata(self, monkeypatch):
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: ("", -1))
        finding = check_unattended_upgrades()
        assert finding.category == "misconfiguration"
        assert finding.platform == "linux"


# ---------------------------------------------------------------------------
# check_open_ports
# ---------------------------------------------------------------------------

class TestCheckOpenPorts:

    _SS_HEADER = "Netid  State   Recv-Q  Send-Q  Local Address:Port\n"

    def test_no_output_returns_none(self, monkeypatch):
        """ss returns no port lines → None."""
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: (self._SS_HEADER, 0))
        assert check_open_ports() is None

    def test_known_safe_port_returns_none(self, monkeypatch):
        """A port in the safe set (8080) → None."""
        output = self._SS_HEADER + "tcp    LISTEN  0  128  0.0.0.0:8080  0.0.0.0:*\n"
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: (output, 0))
        assert check_open_ports() is None

    def test_unexpected_high_port_returns_finding(self, monkeypatch):
        """An unexpected high port → Finding."""
        output = self._SS_HEADER + 'tcp    LISTEN  0  128  0.0.0.0:9999  0.0.0.0:*  users:(("myapp",pid=123,fd=4))\n'
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: (output, 0))
        finding = check_open_ports()
        assert isinstance(finding, Finding)
        assert finding.id == "linux-open-ports"
        assert finding.severity == "info"

    def test_finding_includes_port_and_process(self, monkeypatch):
        """Finding detail mentions the port number and process name."""
        output = self._SS_HEADER + 'tcp    LISTEN  0  128  0.0.0.0:9999  0.0.0.0:*  users:(("myapp",pid=1,fd=3))\n'
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: (output, 0))
        finding = check_open_ports()
        assert "9999" in finding.detail
        assert "myapp" in finding.detail

    def test_low_port_below_1024_is_ignored(self, monkeypatch):
        """Ports ≤ 1023 are not flagged (well-known services)."""
        output = self._SS_HEADER + "tcp    LISTEN  0  128  0.0.0.0:22  0.0.0.0:*\n"
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: (output, 0))
        assert check_open_ports() is None

    def test_ss_not_available_returns_none(self, monkeypatch):
        """ss and netstat both unavailable → None."""
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: ("", -1))
        assert check_open_ports() is None

    def test_ss_not_available_fallback_netstat(self, monkeypatch):
        """ss unavailable, netstat works and returns unexpected port → Finding."""
        def fake_run(cmd, timeout=15):
            if cmd[0] == "ss":
                return ("", -1)
            # netstat output format
            return (
                "Proto Recv-Q Send-Q Local Address           Foreign Address  State\n"
                "tcp        0      0 0.0.0.0:9876            0.0.0.0:*        LISTEN\n",
                0,
            )
        monkeypatch.setattr(linux_module, "_run", fake_run)
        finding = check_open_ports()
        assert isinstance(finding, Finding)
        assert finding.id == "linux-open-ports"

    def test_multiple_unexpected_ports_all_listed(self, monkeypatch):
        """Multiple unexpected ports are all captured in the finding."""
        output = (
            self._SS_HEADER
            + "tcp    LISTEN  0  128  0.0.0.0:9001  0.0.0.0:*\n"
            + "tcp    LISTEN  0  128  0.0.0.0:9002  0.0.0.0:*\n"
        )
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: (output, 0))
        finding = check_open_ports()
        assert isinstance(finding, Finding)
        assert "9001" in finding.detail
        assert "9002" in finding.detail

    def test_finding_metadata(self, monkeypatch):
        output = self._SS_HEADER + "tcp    LISTEN  0  128  0.0.0.0:9999  0.0.0.0:*\n"
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: (output, 0))
        finding = check_open_ports()
        assert finding.category == "security"
        assert finding.platform == "linux"


# ---------------------------------------------------------------------------
# check_sudo_nopasswd
# ---------------------------------------------------------------------------

class TestCheckSudoNopasswd:

    def test_no_nopasswd_returns_none(self, monkeypatch):
        """grep finds nothing → None."""
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: ("", 1))
        assert check_sudo_nopasswd() is None

    def test_nopasswd_found_returns_finding(self, monkeypatch):
        """grep finds NOPASSWD entry → Finding."""
        output = "%wheel ALL=(ALL) NOPASSWD: ALL\n"
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: (output, 0))
        finding = check_sudo_nopasswd()
        assert isinstance(finding, Finding)
        assert finding.id == "linux-sudo-nopasswd"
        assert finding.severity == "high"

    def test_finding_detail_contains_matched_line(self, monkeypatch):
        """The matched sudoers line appears in the finding detail."""
        output = "alice ALL=(ALL) NOPASSWD: /usr/bin/apt\n"
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: (output, 0))
        finding = check_sudo_nopasswd()
        assert "alice" in finding.detail

    def test_comment_lines_are_filtered(self, monkeypatch):
        """Lines starting with # are not treated as NOPASSWD matches."""
        output = "# %wheel ALL=(ALL) NOPASSWD: ALL\n"
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: (output, 0))
        assert check_sudo_nopasswd() is None

    def test_grep_not_available_returns_none(self, monkeypatch):
        """grep not available (rc=-1) → None."""
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: ("", -1))
        assert check_sudo_nopasswd() is None

    def test_mixed_commented_and_real_returns_finding(self, monkeypatch):
        """A mix of comment and real NOPASSWD line → Finding."""
        output = "# commented out\nbob ALL=(ALL) NOPASSWD: ALL\n"
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: (output, 0))
        finding = check_sudo_nopasswd()
        assert isinstance(finding, Finding)
        assert finding.id == "linux-sudo-nopasswd"

    def test_finding_metadata(self, monkeypatch):
        output = "user ALL=(ALL) NOPASSWD: ALL\n"
        monkeypatch.setattr(linux_module, "_run", lambda cmd, timeout=15: (output, 0))
        finding = check_sudo_nopasswd()
        assert finding.category == "security"
        assert finding.platform == "linux"


# ---------------------------------------------------------------------------
# get_checks
# ---------------------------------------------------------------------------

class TestGetChecks:

    def test_returns_seven_tuples(self):
        checks = get_checks()
        assert len(checks) == 7

    def test_all_second_elements_are_callable(self):
        checks = get_checks()
        for name, fn in checks:
            assert callable(fn), f"{name!r} check is not callable"

    def test_all_names_are_strings(self):
        checks = get_checks()
        for name, _ in checks:
            assert isinstance(name, str)
            assert name  # non-empty

    def test_expected_check_names_present(self):
        checks = get_checks()
        names = [name for name, _ in checks]
        assert "Firewall" in names
        assert "SSH Config" in names
        assert "World-Writable /etc" in names
        assert "fail2ban" in names
        assert "Unattended Upgrades" in names
        assert "Open Ports" in names
        assert "Sudo NOPASSWD" in names

    def test_checks_are_the_correct_functions(self):
        checks = get_checks()
        fn_map = {name: fn for name, fn in checks}
        assert fn_map["Firewall"] is check_firewall
        assert fn_map["SSH Config"] is check_ssh_config
        assert fn_map["World-Writable /etc"] is check_world_writable
        assert fn_map["fail2ban"] is check_fail2ban
        assert fn_map["Unattended Upgrades"] is check_unattended_upgrades
        assert fn_map["Open Ports"] is check_open_ports
        assert fn_map["Sudo NOPASSWD"] is check_sudo_nopasswd
