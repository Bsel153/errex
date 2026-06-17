import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from errex.prometheus import generate_metrics, _count_history_errors, _streak_days


def test_generate_metrics_returns_string():
    with patch("errex.prometheus._count_history_errors", return_value=0), \
         patch("errex.prometheus._scan_metrics", return_value={
             "open_total": 0, "by_severity": {}, "total_tickets": 0
         }), \
         patch("errex.prometheus._streak_days", return_value=0):
        result = generate_metrics()
    assert isinstance(result, str)
    assert "errex_errors_24h" in result


def test_generate_metrics_has_ticket_gauges():
    with patch("errex.prometheus._count_history_errors", return_value=5), \
         patch("errex.prometheus._scan_metrics", return_value={
             "open_total": 3, "by_severity": {"high": 2, "low": 1}, "total_tickets": 10
         }), \
         patch("errex.prometheus._streak_days", return_value=7):
        result = generate_metrics()
    assert "errex_tickets_open 3" in result
    assert "errex_tickets_total 10" in result
    assert 'errex_tickets_by_severity{severity="high"} 2' in result
    assert "errex_health_streak_days 7" in result
    assert "errex_errors_24h 5" in result


def test_generate_metrics_all_severities_present():
    with patch("errex.prometheus._count_history_errors", return_value=0), \
         patch("errex.prometheus._scan_metrics", return_value={
             "open_total": 0, "by_severity": {}, "total_tickets": 0
         }), \
         patch("errex.prometheus._streak_days", return_value=0):
        result = generate_metrics()
    for sev in ("critical", "high", "medium", "low", "info"):
        assert f'severity="{sev}"' in result


def test_generate_metrics_has_help_and_type():
    with patch("errex.prometheus._count_history_errors", return_value=0), \
         patch("errex.prometheus._scan_metrics", return_value={
             "open_total": 0, "by_severity": {}, "total_tickets": 0
         }), \
         patch("errex.prometheus._streak_days", return_value=0):
        result = generate_metrics()
    assert "# HELP" in result
    assert "# TYPE" in result


def test_count_history_errors_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("errex.prometheus.HISTORY_FILE", tmp_path / "missing")
    assert _count_history_errors() == 0


def test_count_history_errors_counts_recent(tmp_path, monkeypatch):
    from datetime import datetime, timedelta
    hf = tmp_path / ".errex_history"
    recent = (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z"
    old = (datetime.utcnow() - timedelta(hours=48)).isoformat() + "Z"
    hf.write_text(
        json.dumps({"timestamp": recent, "error": "e1"}) + "\n"
        + json.dumps({"timestamp": old, "error": "e2"}) + "\n"
    )
    monkeypatch.setattr("errex.prometheus.HISTORY_FILE", hf)
    assert _count_history_errors(24) == 1


def test_streak_days_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", staticmethod(lambda: tmp_path))
    result = _streak_days()
    assert result == 0


def test_streak_days_reads_file(tmp_path, monkeypatch):
    status = tmp_path / ".errex_scan_status"
    status.write_text(json.dumps({"streak": 12}))
    monkeypatch.setattr("pathlib.Path.home", staticmethod(lambda: tmp_path))
    result = _streak_days()
    assert result == 12
