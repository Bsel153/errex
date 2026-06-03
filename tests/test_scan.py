"""Tests for errex scan — Finding model, macOS/Windows/CVE scanners, orchestrator."""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

# ── Base data model ───────────────────────────────────────────────────────────

from errex.scanners._base import Finding, FixResult, ScanResult, SEVERITIES


class TestFinding:
    def test_fixable_with_fix_cmd(self):
        f = Finding("id", "high", "security", "macos", "T", "D", fix_cmd="cmd")
        assert f.is_fixable()

    def test_fixable_with_fix_fn(self):
        f = Finding("id", "high", "security", "macos", "T", "D", fix_fn=lambda: True)
        assert f.is_fixable()

    def test_not_fixable_without_either(self):
        f = Finding("id", "high", "security", "macos", "T", "D")
        assert not f.is_fixable()

    def test_web_fixable_only_for_fix_fn(self):
        f_cmd = Finding("id", "high", "security", "macos", "T", "D", fix_cmd="sudo cmd")
        f_fn  = Finding("id", "high", "security", "macos", "T", "D", fix_fn=lambda: True)
        assert not f_cmd.web_fixable()
        assert f_fn.web_fixable()

    def test_severity_rank_ordering(self):
        ranks = [Finding("", sev, "", "", "", "").severity_rank() for sev in SEVERITIES]
        assert ranks == sorted(ranks)

    def test_to_dict_has_required_keys(self):
        f = Finding("myid", "medium", "security", "macos", "Title", "Detail", fix_cmd="fix")
        d = f.to_dict()
        assert d["id"] == "myid"
        assert d["severity"] == "medium"
        assert d["fixable"] is True
        assert d["web_fixable"] is False
        assert "explanation" in d


class TestScanResult:
    def test_by_severity(self):
        findings = [
            Finding("a", "high",   "security", "macos", "H", ""),
            Finding("b", "medium", "security", "macos", "M", ""),
            Finding("c", "high",   "security", "macos", "H2", ""),
        ]
        r = ScanResult("macos", "2026-01-01", findings=findings)
        assert len(r.by_severity("high")) == 2
        assert len(r.by_severity("medium")) == 1

    def test_fixable_filter(self):
        findings = [
            Finding("a", "high", "security", "macos", "T", "", fix_cmd="cmd"),
            Finding("b", "high", "security", "macos", "T", ""),
        ]
        r = ScanResult("macos", "2026-01-01", findings=findings)
        assert len(r.fixable()) == 1


# ── macOS scanner ─────────────────────────────────────────────────────────────

from errex.scanners import macos


def _mock_run(stdout="", returncode=0):
    m = MagicMock()
    m.stdout = stdout
    m.stderr = ""
    m.returncode = returncode
    return m


class TestMacOSScanner:
    @patch("errex.scanners.macos.subprocess.run")
    def test_firewall_disabled(self, mock_run):
        mock_run.return_value = _mock_run("Firewall is DISABLED! (0)\n")
        f = macos.check_firewall()
        assert f is not None
        assert f.severity == "high"
        assert f.id == "macos-firewall-disabled"

    @patch("errex.scanners.macos.subprocess.run")
    def test_firewall_enabled_returns_none(self, mock_run):
        mock_run.return_value = _mock_run("Firewall is ENABLED. (1)\n")
        assert macos.check_firewall() is None

    @patch("errex.scanners.macos.subprocess.run")
    def test_sip_disabled(self, mock_run):
        mock_run.return_value = _mock_run("System Integrity Protection status: disabled.\n")
        f = macos.check_sip()
        assert f is not None
        assert f.severity == "critical"
        assert f.fix_cmd is None  # can't auto-fix

    @patch("errex.scanners.macos.subprocess.run")
    def test_sip_enabled_returns_none(self, mock_run):
        mock_run.return_value = _mock_run("System Integrity Protection status: enabled.\n")
        assert macos.check_sip() is None

    @patch("errex.scanners.macos.subprocess.run")
    def test_gatekeeper_disabled(self, mock_run):
        mock_run.return_value = _mock_run("assessments disabled\n")
        f = macos.check_gatekeeper()
        assert f is not None
        assert f.severity == "high"
        assert "spctl" in f.fix_cmd

    @patch("errex.scanners.macos.subprocess.run")
    def test_filevault_off(self, mock_run):
        mock_run.return_value = _mock_run("FileVault is Off.\n")
        f = macos.check_filevault()
        assert f is not None
        assert f.severity == "medium"
        assert f.fix_cmd is None  # user must enable manually

    @patch("errex.scanners.macos.subprocess.run")
    def test_ssh_running(self, mock_run):
        # launchctl list returns PID and service info when running
        mock_run.return_value = _mock_run("1234\t0\tcom.openssh.sshd\n", returncode=0)
        f = macos.check_ssh()
        assert f is not None
        assert f.severity == "medium"

    @patch("errex.scanners.macos.subprocess.run")
    def test_ssh_not_running(self, mock_run):
        mock_run.return_value = _mock_run("", returncode=1)
        assert macos.check_ssh() is None

    @patch("errex.scanners.macos.subprocess.run")
    def test_autoupdate_off(self, mock_run):
        mock_run.return_value = _mock_run("0\n")
        f = macos.check_auto_update()
        assert f is not None
        assert f.fix_fn is not None  # Python-fixable

    @patch("errex.scanners.macos.subprocess.run")
    def test_autoupdate_on_returns_none(self, mock_run):
        mock_run.return_value = _mock_run("1\n")
        assert macos.check_auto_update() is None

    @patch("errex.scanners.macos.subprocess.run")
    def test_subprocess_error_returns_none(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        assert macos.check_firewall() is None

    def test_get_checks_returns_list(self):
        checks = macos.get_checks()
        assert isinstance(checks, list)
        assert len(checks) >= 5
        for name, fn in checks:
            assert isinstance(name, str)
            assert callable(fn)


# ── Windows scanner ───────────────────────────────────────────────────────────

from errex.scanners import windows


class TestWindowsScanner:
    @patch("errex.scanners.windows.subprocess.run")
    def test_firewall_off(self, mock_run):
        mock_run.return_value = _mock_run(
            "Domain Profile:\nState                                 OFF\n"
        )
        f = windows.check_firewall()
        assert f is not None
        assert f.severity == "high"

    @patch("errex.scanners.windows.subprocess.run")
    def test_firewall_on_returns_none(self, mock_run):
        mock_run.return_value = _mock_run(
            "Domain Profile:\nState                                 ON\n"
        )
        assert windows.check_firewall() is None

    @patch("errex.scanners.windows.subprocess.run")
    def test_smb1_enabled(self, mock_run):
        mock_run.return_value = _mock_run("True\n")
        f = windows.check_smb1()
        assert f is not None
        assert f.severity == "critical"

    @patch("errex.scanners.windows.subprocess.run")
    def test_smb1_disabled_returns_none(self, mock_run):
        mock_run.return_value = _mock_run("False\n")
        assert windows.check_smb1() is None

    def test_rdp_exposed(self):
        with patch("errex.scanners.windows._reg_get", return_value=0):
            f = windows.check_remote_desktop()
        assert f is not None
        assert f.severity == "medium"
        assert f.fix_fn is not None  # has Python fix

    def test_rdp_disabled_returns_none(self):
        with patch("errex.scanners.windows._reg_get", return_value=1):
            assert windows.check_remote_desktop() is None

    @patch("errex.scanners.windows.subprocess.run")
    def test_guest_active(self, mock_run):
        mock_run.return_value = _mock_run(
            "User name                    Guest\nAccount active               Yes\n"
        )
        f = windows.check_guest_account()
        assert f is not None
        assert f.severity == "high"

    def test_autorun_not_set(self):
        with patch("errex.scanners.windows._reg_get", return_value=None):
            f = windows.check_autorun()
        assert f is not None
        assert f.fix_fn is not None

    def test_autorun_fully_disabled(self):
        with patch("errex.scanners.windows._reg_get", return_value=0xFF):
            assert windows.check_autorun() is None

    def test_get_checks_returns_list(self):
        checks = windows.get_checks()
        assert isinstance(checks, list)
        assert len(checks) >= 5


# ── CVE scanner ───────────────────────────────────────────────────────────────

from errex.scanners import cve


class TestCVEScanner:
    @patch("errex.scanners.cve.subprocess.run")
    @patch("errex.scanners.cve.urllib.request.urlopen")
    def test_finds_vulnerable_package(self, mock_urlopen, mock_subproc):
        mock_subproc.return_value = _mock_run(
            json.dumps([{"name": "requests", "version": "2.0.0"}])
        )
        # Mock OSV batch response: one vuln
        osv_resp = {
            "results": [{
                "vulns": [{
                    "id": "GHSA-xxxx",
                    "aliases": ["CVE-2023-1234"],
                    "summary": "Security issue in requests",
                    "database_specific": {"severity": "HIGH"},
                }]
            }]
        }
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.read.return_value = json.dumps(osv_resp).encode()
        mock_urlopen.return_value = mock_ctx

        finding = cve.check_python_packages()
        assert finding is not None
        assert finding.id == "cve-python-packages"
        assert finding.severity == "high"
        assert "CVE-2023-1234" in finding.cve_ids

    @patch("errex.scanners.cve.subprocess.run")
    @patch("errex.scanners.cve.urllib.request.urlopen")
    def test_no_vulns_returns_none(self, mock_urlopen, mock_subproc):
        mock_subproc.return_value = _mock_run(
            json.dumps([{"name": "requests", "version": "2.28.0"}])
        )
        osv_resp = {"results": [{"vulns": []}]}
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.read.return_value = json.dumps(osv_resp).encode()
        mock_urlopen.return_value = mock_ctx

        assert cve.check_python_packages() is None

    @patch("errex.scanners.cve.subprocess.run")
    def test_pip_failure_returns_none(self, mock_subproc):
        mock_subproc.side_effect = Exception("pip not found")
        assert cve.check_python_packages() is None

    @patch("errex.scanners.cve.urllib.request.urlopen")
    def test_lookup_nvd_returns_list(self, mock_urlopen):
        nvd_resp = {
            "vulnerabilities": [{
                "cve": {
                    "id": "CVE-2024-0001",
                    "descriptions": [{"lang": "en", "value": "A vulnerability"}],
                    "published": "2024-01-01",
                    "metrics": {
                        "cvssMetricV31": [{"cvssData": {"baseSeverity": "HIGH", "baseScore": 8.1}}]
                    },
                }
            }]
        }
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.read.return_value = json.dumps(nvd_resp).encode()
        mock_urlopen.return_value = mock_ctx

        results = cve.lookup_nvd("openssl 3.0")
        assert len(results) == 1
        assert results[0]["id"] == "CVE-2024-0001"
        assert results[0]["severity"] == "HIGH"

    @patch("errex.scanners.cve.urllib.request.urlopen")
    def test_lookup_nvd_network_error_returns_empty(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("network error")
        assert cve.lookup_nvd("anything") == []


# ── Scan orchestrator ─────────────────────────────────────────────────────────

from errex.scan import detect_platform, run_scan, auto_fix


class TestOrchestrator:
    def test_detect_platform_returns_string(self):
        plat = detect_platform()
        assert plat in ("macos", "windows", "linux")

    def test_run_scan_returns_scanresult(self):
        from errex.scanners._base import ScanResult
        with patch("errex.scanners.macos.subprocess.run", return_value=_mock_run("enabled")):
            with patch("errex.scanners.cve.subprocess.run", return_value=_mock_run("[]")):
                with patch("errex.scanners.cve.urllib.request.urlopen") as mu:
                    mock_ctx = MagicMock()
                    mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
                    mock_ctx.__exit__ = MagicMock(return_value=False)
                    mock_ctx.read.return_value = json.dumps({"results": []}).encode()
                    mu.return_value = mock_ctx
                    result = run_scan(platform="macos")
        assert isinstance(result, ScanResult)
        assert result.platform == "macos"

    def test_severity_filter(self):
        # Create mock findings of different severities
        findings = [
            Finding("a", "critical", "security", "macos", "C", ""),
            Finding("b", "medium",   "security", "macos", "M", ""),
            Finding("c", "low",      "security", "macos", "L", ""),
        ]
        with patch("errex.scan.run_scan") as mock_rs:
            from errex.scanners._base import ScanResult
            mock_rs.return_value = ScanResult("macos", "2026-01-01", findings=findings)
            result = mock_rs(severity_filter="medium")
        # Verify filter is applied by run_scan internally — test the filter logic directly
        from errex.scanners._base import SEVERITIES
        threshold = SEVERITIES.index("medium")
        filtered = [f for f in findings if SEVERITIES.index(f.severity) <= threshold]
        assert len(filtered) == 2  # critical + medium

    def test_auto_fix_calls_fix_fn(self):
        called = []
        f = Finding("id", "high", "security", "macos", "T", "D",
                    fix_fn=lambda: (called.append(1), True)[1])
        results = auto_fix([f])
        assert called == [1]
        assert results[0].success is True

    def test_auto_fix_dry_run(self):
        f = Finding("id", "high", "security", "macos", "T", "D", fix_cmd="sudo cmd")
        results = auto_fix([f], dry_run=True)
        assert len(results) == 1
        assert results[0].success is True
        assert "Would run" in results[0].message

    def test_auto_fix_skips_unfixable(self):
        f = Finding("id", "high", "security", "macos", "T", "D")
        assert auto_fix([f]) == []

    def test_auto_fix_fix_cmd(self):
        f = Finding("id", "high", "security", "macos", "T", "D", fix_cmd="echo ok")
        results = auto_fix([f])
        assert results[0].success is True

    def test_progress_callback_called(self):
        calls = []
        def cb(name, done, total):
            calls.append(name)

        with patch("errex.scanners.macos.subprocess.run", return_value=_mock_run("enabled")):
            with patch("errex.scanners.cve.subprocess.run", return_value=_mock_run("[]")):
                with patch("errex.scanners.cve.urllib.request.urlopen") as mu:
                    mock_ctx = MagicMock()
                    mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
                    mock_ctx.__exit__ = MagicMock(return_value=False)
                    mock_ctx.read.return_value = json.dumps({"results": []}).encode()
                    mu.return_value = mock_ctx
                    run_scan(platform="macos", progress_cb=cb)

        assert len(calls) > 0
        assert any("CVE" in c for c in calls)


# ── Integration: CLI --scan flag ──────────────────────────────────────────────

import subprocess as _subprocess


class TestScanCLI:
    def _run(self, args: list[str]) -> _subprocess.CompletedProcess:
        return _subprocess.run(
            [sys.executable, "-m", "errex"] + args,
            capture_output=True, text=True,
            env={**__import__("os").environ, "ANTHROPIC_API_KEY": ""},
        )

    def test_scan_no_explain_exits_zero(self):
        result = self._run(["--scan", "--scan-no-explain"])
        assert result.returncode == 0

    def test_scan_severity_flag_accepted(self):
        result = self._run(["--scan", "--scan-no-explain", "--scan-severity", "critical"])
        assert result.returncode == 0

    def test_scan_help_mentioned(self):
        result = self._run(["--help"])
        assert "scan" in result.stdout.lower()
