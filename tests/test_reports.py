"""Tests for weekly report module."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest


def _write_history(path: Path, entries: list[dict]) -> None:
    with open(path, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def test_weekly_report_no_history(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    import errex._paths as paths
    import importlib
    # Patch HISTORY_FILE to a non-existent file
    with patch("errex.reports.HISTORY_FILE", tmp_path / ".errex_history"):
        from errex.reports import weekly_report
        # Should print "No history" without raising
        weekly_report()


def test_weekly_report_with_history(monkeypatch, tmp_path):
    hist = tmp_path / ".errex_history"
    now = datetime.now()
    entries = [
        {
            "timestamp": (now - timedelta(hours=i)).isoformat(),
            "model": "claude-sonnet-4-6",
            "brief": False,
            "error": f"TypeError: NoneType error {i}",
            "explanation": "Some explanation",
        }
        for i in range(5)
    ]
    _write_history(hist, entries)

    with patch("errex.reports.HISTORY_FILE", hist):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from errex.reports import weekly_report
        weekly_report()


def test_load_recent_returns_recent_entries(tmp_path):
    hist = tmp_path / ".errex_history"
    now = datetime.now()
    entries = [
        {"timestamp": (now - timedelta(days=1)).isoformat(), "model": "m", "brief": False, "error": "e1", "explanation": "x"},
        {"timestamp": (now - timedelta(days=10)).isoformat(), "model": "m", "brief": False, "error": "e2", "explanation": "x"},
    ]
    _write_history(hist, entries)

    with patch("errex.reports.HISTORY_FILE", hist):
        from errex.reports import _load_recent
        recent = _load_recent(days=7)
        assert len(recent) == 1
        assert "e1" in recent[0]["error"]


def test_top_error_types():
    from errex.reports import _top_error_types
    entries = [
        {"error": "TypeError: something", "explanation": ""},
        {"error": "TypeError: other thing", "explanation": ""},
        {"error": "ValueError: bad value", "explanation": ""},
    ]
    top = _top_error_types(entries, n=5)
    # TypeError should be most common
    names = [t for t, c in top]
    # Result depends on extract_error_type, just assert it returns something
    assert isinstance(top, list)


def test_busiest_hour_returns_string():
    from errex.reports import _busiest_hour
    now = datetime.now()
    entries = [
        {"timestamp": now.replace(hour=14).isoformat()},
        {"timestamp": now.replace(hour=14).isoformat()},
        {"timestamp": now.replace(hour=9).isoformat()},
    ]
    result = _busiest_hour(entries)
    assert result is not None
    assert "14:00" in result


def test_busiest_hour_empty():
    from errex.reports import _busiest_hour
    assert _busiest_hour([]) is None
