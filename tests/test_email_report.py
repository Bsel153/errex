import pytest
from unittest.mock import patch, MagicMock
from errex.email_report import build_html_report, gather_report_data, print_report

def test_build_html_report_structure():
    html = build_html_report(
        period="weekly",
        scan_findings=[
            {"id": "f1", "severity": "high", "title": "Firewall off", "detail": "No ufw"},
            {"id": "f2", "severity": "medium", "title": "SSH weak", "detail": "Password auth"},
        ],
        fixed_findings=[{"id": "f1"}],
        error_count=12,
        period_label="Weekly",
    )
    assert "errex Device Health Report" in html
    assert "Firewall off" in html
    assert "Fixed" in html  # f1 was fixed
    assert "12" in html  # error count

def test_build_html_report_no_findings():
    html = build_html_report("daily", [], [], 0, "Daily")
    assert "No security findings" in html

def test_build_html_report_severity_classes():
    html = build_html_report(
        "weekly",
        [{"id": "c1", "severity": "critical", "title": "Critical issue", "detail": ""}],
        [],
        0,
        "Weekly",
    )
    assert 'class="finding critical"' in html

def test_gather_report_data_returns_dict():
    with patch("errex.email_report.run_scan") as mock_scan:
        from errex.scanners._base import ScanResult
        mock_scan.return_value = ScanResult(platform="linux", started_at="2026-01-01T00:00:00Z")
        data = gather_report_data("weekly")
    assert "scan_findings" in data
    assert "error_count" in data
    assert data["period"] == "weekly"

def test_print_report_stdout(capsys):
    with patch("errex.email_report.run_scan") as mock_scan:
        from errex.scanners._base import ScanResult
        mock_scan.return_value = ScanResult(platform="linux", started_at="2026-01-01T00:00:00Z")
        print_report("daily")
    captured = capsys.readouterr()
    assert "errex Device Health Report" in captured.out

def test_print_report_to_file(tmp_path):
    with patch("errex.email_report.run_scan") as mock_scan:
        from errex.scanners._base import ScanResult
        mock_scan.return_value = ScanResult(platform="linux", started_at="2026-01-01T00:00:00Z")
        out = str(tmp_path / "report.html")
        print_report("weekly", output_file=out)
    content = open(out).read()
    assert "errex Device Health Report" in content

def test_send_email_report_calls_smtp():
    with patch("errex.email_report.run_scan") as mock_scan, \
         patch("errex.email_report.smtplib.SMTP") as mock_smtp:
        from errex.scanners._base import ScanResult
        mock_scan.return_value = ScanResult(platform="linux", started_at="2026-01-01T00:00:00Z")
        ctx = MagicMock()
        mock_smtp.return_value.__enter__ = lambda s: ctx
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        from errex.email_report import send_email_report
        send_email_report("user@example.com", "smtp.example.com", 587, "user", "pass", "weekly", use_tls=False)
    mock_smtp.assert_called_once()


def test_send_email_report_port_465_uses_smtp_ssl():
    """Port 465 must use SMTP_SSL (implicit TLS), not STARTTLS."""
    with patch("errex.email_report.run_scan") as mock_scan, \
         patch("errex.email_report.smtplib.SMTP_SSL") as mock_ssl, \
         patch("errex.email_report.smtplib.SMTP") as mock_plain:
        from errex.scanners._base import ScanResult
        mock_scan.return_value = ScanResult(platform="linux", started_at="2026-01-01T00:00:00Z")
        ctx = MagicMock()
        mock_ssl.return_value.__enter__ = lambda s: ctx
        mock_ssl.return_value.__exit__ = MagicMock(return_value=False)
        from errex.email_report import send_email_report
        send_email_report("u@e.com", "smtp.example.com", 465, "u", "p", use_tls=True)
    mock_ssl.assert_called_once()
    mock_plain.assert_not_called()


def test_build_html_report_escapes_xss():
    """Finding titles with HTML special chars must be escaped."""
    html = build_html_report(
        "weekly",
        [{"id": "x", "severity": "high", "title": "<script>alert(1)</script>", "detail": ""}],
        [],
        0,
        "Weekly",
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_build_html_report_caps_at_15_findings():
    findings = [
        {"id": f"f{i}", "severity": "low", "title": f"Issue {i}", "detail": ""}
        for i in range(20)
    ]
    html = build_html_report("weekly", findings, [], 0, "Weekly")
    # Only 15 should appear
    assert "Issue 14" in html
    assert "Issue 15" not in html


def test_build_html_report_all_severity_classes():
    for sev in ("critical", "high", "medium", "low"):
        html = build_html_report(
            "weekly",
            [{"id": "x", "severity": sev, "title": f"{sev} issue", "detail": ""}],
            [],
            0,
            "Weekly",
        )
        assert f'class="finding {sev}"' in html


def test_build_html_report_fixed_badge_only_for_fixed():
    html = build_html_report(
        "weekly",
        [
            {"id": "f1", "severity": "high", "title": "Fixed one", "detail": ""},
            {"id": "f2", "severity": "medium", "title": "Not fixed", "detail": ""},
        ],
        [{"id": "f1"}],
        0,
        "Weekly",
    )
    # The fixed badge span should appear exactly once (CSS class appears separately)
    assert html.count('<span class="fixed-badge">') == 1


def test_gather_report_data_handles_scan_exception():
    """If run_scan raises, scan_findings should be empty (not crash)."""
    with patch("errex.email_report.run_scan", side_effect=RuntimeError("scan broke")):
        data = gather_report_data("daily")
    assert data["scan_findings"] == []
    assert "error_count" in data


def test_gather_report_data_monthly_period():
    with patch("errex.email_report.run_scan") as mock_scan:
        from errex.scanners._base import ScanResult
        mock_scan.return_value = ScanResult(platform="linux", started_at="2026-01-01T00:00:00Z")
        data = gather_report_data("monthly")
    assert data["period"] == "monthly"
    assert data["period_label"] == "Monthly"


def test_gather_report_data_counts_history(tmp_path, monkeypatch):
    import json as _json
    import datetime

    history_file = tmp_path / ".errex_history"
    recent = (datetime.datetime.utcnow() - datetime.timedelta(hours=1)).isoformat() + "Z"
    history_file.write_text(_json.dumps({"timestamp": recent, "error": "oops"}) + "\n")

    monkeypatch.setattr("errex.email_report.HISTORY_FILE", history_file)
    with patch("errex.email_report.run_scan") as mock_scan:
        from errex.scanners._base import ScanResult
        mock_scan.return_value = ScanResult(platform="linux", started_at="2026-01-01T00:00:00Z")
        data = gather_report_data("daily")
    assert data["error_count"] == 1
