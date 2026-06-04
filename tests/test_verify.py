import pytest
import subprocess
from unittest.mock import patch, MagicMock
from errex.verify import verify_fix, show_verify_result

def test_verify_success():
    with patch("errex.verify.subprocess.run") as m:
        m.return_value = MagicMock(returncode=0, stdout="all good", stderr="")
        r = verify_fix("echo hello", "original error")
    assert r["success"] is True
    assert r["exit_code"] == 0

def test_verify_same_error():
    with patch("errex.verify.subprocess.run") as m:
        m.return_value = MagicMock(returncode=1, stdout="", stderr="NameError: name 'foo' is not defined")
        r = verify_fix("python script.py", "NameError: name 'foo' is not defined")
    assert r["success"] is False
    assert r["same_error"] is True

def test_verify_different_error():
    with patch("errex.verify.subprocess.run") as m:
        m.return_value = MagicMock(returncode=1, stdout="", stderr="TypeError: something else")
        r = verify_fix("python script.py", "NameError: name 'foo' is not defined")
    assert r["success"] is False
    assert r["same_error"] is False

def test_verify_command_not_found():
    with patch("errex.verify.subprocess.run", side_effect=FileNotFoundError):
        r = verify_fix("nonexistent_cmd arg", "some error")
    assert r["success"] is False
    assert r["same_error"] is True

def test_verify_timeout():
    with patch("errex.verify.subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 60)):
        r = verify_fix("sleep 999", "error")
    assert r["success"] is False

def test_verify_scan_resolves():
    from errex.scan import verify_scan
    from errex.scanners._base import ScanResult, Finding

    before = ScanResult(platform="linux", started_at="2026-01-01T00:00:00Z")
    before.findings = [
        Finding(id="linux-fail2ban-inactive", severity="low", category="security",
                platform="linux", title="fail2ban not running", detail="inactive")
    ]
    after = ScanResult(platform="linux", started_at="2026-01-01T00:01:00Z")
    after.findings = []

    with patch("errex.scan.run_scan", return_value=after):
        result = verify_scan(before)

    assert "linux-fail2ban-inactive" in result["resolved"]
    assert result["still_present"] == []
    assert result["new_issues"] == []

def test_show_verify_result_success():
    from rich.console import Console
    import io
    buf = io.StringIO()
    console = Console(file=buf, no_color=True)
    show_verify_result({"success": True, "same_error": False, "output": "", "exit_code": 0}, console)
    assert "verified" in buf.getvalue().lower()

def test_show_verify_result_failure():
    from rich.console import Console
    import io
    buf = io.StringIO()
    console = Console(file=buf, no_color=True)
    show_verify_result({"success": False, "same_error": True, "output": "still broken", "exit_code": 1}, console)
    assert "did not resolve" in buf.getvalue().lower() or "✗" in buf.getvalue()
