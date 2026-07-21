"""Unit tests for errex/scan_diff.py — no real scans."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------

def _make_finding(id: str, title: str, severity: str = "medium", detail: str = "detail"):
    from errex.scanners._base import SEVERITIES
    f = MagicMock()
    f.id = id
    f.title = title
    f.severity = severity
    f.detail = detail
    f.severity_rank = MagicMock(return_value=SEVERITIES.index(severity))
    return f


def _make_scan_result(findings):
    r = MagicMock()
    r.findings = findings
    return r


# ---------------------------------------------------------------------------
# No previous state — all findings shown as new
# ---------------------------------------------------------------------------

def test_scan_diff_no_prev_state(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("errex.scan_diff._STATE_FILE", tmp_path / "state.json")
    findings = [_make_finding("f1", "Open port 22", "high")]

    with patch("errex.scan_diff.run_scan", return_value=_make_scan_result(findings)), \
         patch("errex.scan_diff.detect_platform", return_value="linux"):
        from errex.scan_diff import scan_diff
        scan_diff()

    captured = capsys.readouterr()
    assert "NEW" in captured.out
    assert "Open port 22" in captured.out


def test_scan_diff_no_prev_state_no_findings(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("errex.scan_diff._STATE_FILE", tmp_path / "missing.json")

    with patch("errex.scan_diff.run_scan", return_value=_make_scan_result([])), \
         patch("errex.scan_diff.detect_platform", return_value="linux"):
        from errex.scan_diff import scan_diff
        scan_diff()

    captured = capsys.readouterr()
    assert "No findings" in captured.out


# ---------------------------------------------------------------------------
# With previous state — diff detection
# ---------------------------------------------------------------------------

def test_scan_diff_detects_new(tmp_path, monkeypatch, capsys):
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({"finding_ids": ["f1"], "timestamp": "2026-01-01T00:00:00Z"}))
    monkeypatch.setattr("errex.scan_diff._STATE_FILE", state_file)

    findings = [
        _make_finding("f1", "Known issue"),
        _make_finding("f2", "New issue", "high"),
    ]

    with patch("errex.scan_diff.run_scan", return_value=_make_scan_result(findings)), \
         patch("errex.scan_diff.detect_platform", return_value="linux"):
        from errex.scan_diff import scan_diff
        scan_diff()

    captured = capsys.readouterr()
    assert "1 new finding" in captured.out
    assert "New issue" in captured.out


def test_scan_diff_detects_resolved(tmp_path, monkeypatch, capsys):
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({"finding_ids": ["f1", "f2"], "timestamp": "2026-01-01T00:00:00Z"}))
    monkeypatch.setattr("errex.scan_diff._STATE_FILE", state_file)

    findings = [_make_finding("f1", "Still present")]

    with patch("errex.scan_diff.run_scan", return_value=_make_scan_result(findings)), \
         patch("errex.scan_diff.detect_platform", return_value="linux"):
        from errex.scan_diff import scan_diff
        scan_diff()

    captured = capsys.readouterr()
    assert "1 resolved finding" in captured.out
    assert "f2" in captured.out


def test_scan_diff_no_changes(tmp_path, monkeypatch, capsys):
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({"finding_ids": ["f1"], "timestamp": "2026-01-01T00:00:00Z"}))
    monkeypatch.setattr("errex.scan_diff._STATE_FILE", state_file)

    findings = [_make_finding("f1", "Same issue")]

    with patch("errex.scan_diff.run_scan", return_value=_make_scan_result(findings)), \
         patch("errex.scan_diff.detect_platform", return_value="linux"):
        from errex.scan_diff import scan_diff
        scan_diff()

    captured = capsys.readouterr()
    assert "No new findings" in captured.out
    assert "No findings resolved" in captured.out


# ---------------------------------------------------------------------------
# Severity filtering
# ---------------------------------------------------------------------------

def test_scan_diff_severity_filter(tmp_path, monkeypatch, capsys):
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({"finding_ids": [], "timestamp": "2026-01-01T00:00:00Z"}))
    monkeypatch.setattr("errex.scan_diff._STATE_FILE", state_file)

    findings = [
        _make_finding("f1", "Critical thing", "critical"),
        _make_finding("f2", "Info note", "info"),
    ]

    with patch("errex.scan_diff.run_scan", return_value=_make_scan_result(findings)), \
         patch("errex.scan_diff.detect_platform", return_value="linux"):
        from errex.scan_diff import scan_diff
        scan_diff(severity="critical")

    captured = capsys.readouterr()
    assert "Critical thing" in captured.out
    # Info finding filtered out
    assert "Info note" not in captured.out
