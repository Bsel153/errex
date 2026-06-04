import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_is_first_run_true(tmp_path, monkeypatch):
    flag = tmp_path / ".errex_first_scan_done"
    monkeypatch.setattr("errex._first_run._FLAG", flag)
    from errex._first_run import is_first_run
    assert is_first_run() is True


def test_is_first_run_false_after_mark(tmp_path, monkeypatch):
    flag = tmp_path / ".errex_first_scan_done"
    monkeypatch.setattr("errex._first_run._FLAG", flag)
    from errex._first_run import mark_first_run_done, is_first_run
    mark_first_run_done()
    assert is_first_run() is False


def test_run_first_scan_no_findings(tmp_path, monkeypatch):
    flag = tmp_path / ".errex_first_scan_done"
    monkeypatch.setattr("errex._first_run._FLAG", flag)
    from errex.scanners._base import ScanResult
    mock_result = ScanResult(platform="linux", started_at="2026-01-01T00:00:00Z")
    with patch("errex.scan.run_scan", return_value=mock_result):
        from errex._first_run import run_first_scan
        run_first_scan()
    assert flag.exists()


def test_run_first_scan_with_findings(tmp_path, monkeypatch):
    flag = tmp_path / ".errex_first_scan_done"
    monkeypatch.setattr("errex._first_run._FLAG", flag)
    from errex.scanners._base import ScanResult, Finding
    result = ScanResult(platform="linux", started_at="2026-01-01T00:00:00Z")
    result.findings = [
        Finding(id="f1", severity="high", category="security", platform="linux",
                title="Firewall off", detail="No ufw active")
    ]
    with patch("errex.scan.run_scan", return_value=result):
        from errex._first_run import run_first_scan
        run_first_scan()
    assert flag.exists()


def test_scan_scheduler_cron_linux():
    from errex._scan_scheduler import setup_cron
    out = setup_cron("daily", platform="linux")
    assert "crontab" in out or "cron" in out.lower()
    assert "errex" in out


def test_scan_scheduler_cron_macos():
    from errex._scan_scheduler import setup_cron
    out = setup_cron("daily", platform="darwin")
    assert "launchd" in out or "launchctl" in out or "plist" in out


def test_scan_scheduler_windows():
    from errex._scan_scheduler import setup_cron
    out = setup_cron("daily", platform="windows")
    assert "schtasks" in out or "Task Scheduler" in out


def test_log_and_get_scan_info(tmp_path, monkeypatch):
    log = tmp_path / ".errex_scan_log.jsonl"
    monkeypatch.setattr("errex._scan_scheduler._SCAN_LOG", log)
    from errex.scanners._base import ScanResult, Finding
    from errex._scan_scheduler import log_scan_result, get_last_scan_info
    result = ScanResult(platform="linux", started_at="2026-01-01T00:00:00Z")
    result.findings = [
        Finding(id="f1", severity="high", category="security", platform="linux",
                title="Issue", detail="detail")
    ]
    log_scan_result(result)
    info = get_last_scan_info()
    assert info is not None
    assert info["finding_count"] == 1
    assert "high" in info["severities"]


def test_get_last_scan_info_none_when_no_log(tmp_path, monkeypatch):
    log = tmp_path / "nonexistent.jsonl"
    monkeypatch.setattr("errex._scan_scheduler._SCAN_LOG", log)
    from errex._scan_scheduler import get_last_scan_info
    assert get_last_scan_info() is None
