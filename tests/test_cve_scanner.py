"""Tests for the CVE scanner (NVD + OSV lookups)."""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from errex.scanners.cve import lookup_nvd, check_python_packages


# ── lookup_nvd ─────────────────────────────────────────────────────────────────

def _nvd_response(cve_id="CVE-2024-1234", severity="HIGH", score=8.5, desc="A bad bug."):
    return {
        "vulnerabilities": [
            {
                "cve": {
                    "id": cve_id,
                    "published": "2024-01-15T00:00:00.000",
                    "descriptions": [{"lang": "en", "value": desc}],
                    "metrics": {
                        "cvssMetricV31": [
                            {"cvssData": {"baseSeverity": severity, "baseScore": score}}
                        ]
                    },
                }
            }
        ]
    }


class _FakeHTTPResp:
    def __init__(self, data: dict):
        self._data = json.dumps(data).encode()

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def test_lookup_nvd_returns_results(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout: _FakeHTTPResp(_nvd_response()),
    )
    results = lookup_nvd("openssl")
    assert len(results) == 1
    assert results[0]["id"] == "CVE-2024-1234"
    assert results[0]["severity"] == "HIGH"
    assert results[0]["score"] == 8.5


def test_lookup_nvd_returns_empty_on_network_error(monkeypatch):
    def boom(req, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert lookup_nvd("anything") == []


def test_lookup_nvd_truncates_description(monkeypatch):
    long_desc = "X" * 500
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout: _FakeHTTPResp(_nvd_response(desc=long_desc)),
    )
    results = lookup_nvd("test")
    assert len(results[0]["summary"]) <= 300


def test_lookup_nvd_empty_response(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout: _FakeHTTPResp({"vulnerabilities": []}),
    )
    assert lookup_nvd("obscure-package-xyz") == []


def test_lookup_nvd_falls_back_when_no_cvss(monkeypatch):
    resp = {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2024-9999",
                    "published": "2024-06-01T00:00:00.000",
                    "descriptions": [{"lang": "en", "value": "Some issue."}],
                    "metrics": {},
                }
            }
        ]
    }
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout: _FakeHTTPResp(resp),
    )
    results = lookup_nvd("test")
    assert results[0]["severity"] == "UNKNOWN"
    assert results[0]["score"] == 0.0


# ── check_python_packages ──────────────────────────────────────────────────────

def _osv_batch_response(vuln_ids=None):
    """One vulnerable package result, rest clean."""
    if vuln_ids is None:
        vuln_ids = ["GHSA-xxxx-yyyy-zzzz"]
    return {
        "results": [
            {
                "vulns": [
                    {
                        "id": vuln_ids[0],
                        "aliases": ["CVE-2024-5555"],
                        "database_specific": {"severity": "HIGH"},
                    }
                ]
            }
        ]
    }


def _pip_list_output(packages=None):
    if packages is None:
        packages = [{"name": "requests", "version": "2.28.0"}]
    return json.dumps(packages).encode()


def test_check_python_packages_returns_finding_when_vulnerable(monkeypatch):
    def fake_run(cmd, capture_output, text, timeout):
        m = MagicMock()
        m.stdout = json.dumps([{"name": "requests", "version": "2.28.0"}])
        m.returncode = 0
        return m

    monkeypatch.setattr(subprocess, "run", fake_run)

    class FakeOSVResp:
        def read(self):
            return json.dumps(_osv_batch_response()).encode()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_urlopen(req, timeout):
        return FakeOSVResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = check_python_packages()
    assert result is not None
    assert result.id == "cve-python-packages"
    assert result.severity in ("high", "medium")
    assert "requests" in result.detail


def test_check_python_packages_returns_none_when_clean(monkeypatch):
    def fake_run(cmd, capture_output, text, timeout):
        m = MagicMock()
        m.stdout = json.dumps([{"name": "requests", "version": "2.32.0"}])
        m.returncode = 0
        return m

    monkeypatch.setattr(subprocess, "run", fake_run)

    class FakeOSVClean:
        def read(self):
            return json.dumps({"results": [{"vulns": []}]}).encode()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout: FakeOSVClean())
    result = check_python_packages()
    assert result is None


def test_check_python_packages_handles_pip_failure(monkeypatch):
    def fake_run(cmd, capture_output, text, timeout):
        raise FileNotFoundError("pip not found")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = check_python_packages()
    assert result is None


def test_check_python_packages_handles_osv_error(monkeypatch):
    def fake_run(cmd, capture_output, text, timeout):
        m = MagicMock()
        m.stdout = json.dumps([{"name": "requests", "version": "2.28.0"}])
        m.returncode = 0
        return m

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout: (_ for _ in ()).throw(OSError("timeout")))
    result = check_python_packages()
    assert result is None


def test_check_python_packages_empty_package_list(monkeypatch):
    def fake_run(cmd, capture_output, text, timeout):
        m = MagicMock()
        m.stdout = "[]"
        m.returncode = 0
        return m

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = check_python_packages()
    assert result is None


def test_check_python_packages_severity_critical_when_critical_vuln(monkeypatch):
    def fake_run(cmd, capture_output, text, timeout):
        m = MagicMock()
        m.stdout = json.dumps([{"name": "django", "version": "3.0.0"}])
        m.returncode = 0
        return m

    monkeypatch.setattr(subprocess, "run", fake_run)

    critical_osv = {
        "results": [
            {
                "vulns": [
                    {
                        "id": "GHSA-crit-0001",
                        "aliases": ["CVE-2024-0001"],
                        "database_specific": {"severity": "CRITICAL"},
                    }
                ]
            }
        ]
    }

    class FakeCritResp:
        def read(self): return json.dumps(critical_osv).encode()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout: FakeCritResp())
    result = check_python_packages()
    assert result is not None
    assert result.severity == "high"


def test_check_python_packages_includes_cve_ids(monkeypatch):
    def fake_run(cmd, capture_output, text, timeout):
        m = MagicMock()
        m.stdout = json.dumps([{"name": "pillow", "version": "9.0.0"}])
        m.returncode = 0
        return m

    monkeypatch.setattr(subprocess, "run", fake_run)

    osv = {
        "results": [
            {
                "vulns": [
                    {
                        "id": "GHSA-abcd-1234-efgh",
                        "aliases": ["CVE-2024-7777"],
                        "database_specific": {"severity": "HIGH"},
                    }
                ]
            }
        ]
    }

    class FakeResp:
        def read(self): return json.dumps(osv).encode()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout: FakeResp())
    result = check_python_packages()
    assert result is not None
    assert "CVE-2024-7777" in result.cve_ids
