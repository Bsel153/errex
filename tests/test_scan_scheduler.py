"""Tests for the scan log / health-streak helpers in _scan_scheduler."""
from __future__ import annotations

import datetime
import json

import pytest

import errex._scan_scheduler as S


def _iso_days_ago(days: float) -> str:
    return (datetime.datetime.utcnow() - datetime.timedelta(days=days)).isoformat() + "Z"


def _patch_log(monkeypatch, tmp_path):
    log_file = tmp_path / "scan_log.jsonl"
    monkeypatch.setattr(S, "_SCAN_LOG", log_file)
    return log_file


def _write(log_file, entries):
    with open(log_file, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


class TestHealthStreak:
    def test_returns_none_without_log(self, monkeypatch, tmp_path):
        _patch_log(monkeypatch, tmp_path)
        assert S.current_health_streak_days() is None

    def test_returns_none_when_most_recent_scan_is_bad(self, monkeypatch, tmp_path):
        log_file = _patch_log(monkeypatch, tmp_path)
        _write(log_file, [
            {"timestamp": _iso_days_ago(5), "severities": {}},
            {"timestamp": _iso_days_ago(0), "severities": {"high": 1}},
        ])
        assert S.current_health_streak_days() is None

    def test_counts_days_since_last_bad_scan(self, monkeypatch, tmp_path):
        log_file = _patch_log(monkeypatch, tmp_path)
        _write(log_file, [
            {"timestamp": _iso_days_ago(10), "severities": {"critical": 1}},
            {"timestamp": _iso_days_ago(7), "severities": {}},
            {"timestamp": _iso_days_ago(3), "severities": {"low": 1, "info": 2}},
        ])
        streak = S.current_health_streak_days()
        assert streak is not None
        assert 6.5 < streak < 7.5

    def test_low_and_info_do_not_break_streak(self, monkeypatch, tmp_path):
        log_file = _patch_log(monkeypatch, tmp_path)
        _write(log_file, [
            {"timestamp": _iso_days_ago(20), "severities": {}},
            {"timestamp": _iso_days_ago(1), "severities": {"low": 3}},
        ])
        streak = S.current_health_streak_days()
        assert streak is not None
        assert streak > 19


class TestLogScanResultReturn:
    def test_returns_logged_entry(self, monkeypatch, tmp_path):
        log_file = _patch_log(monkeypatch, tmp_path)

        class FakeFinding:
            def __init__(self, severity, category):
                self.severity = severity
                self.category = category

        class FakeResult:
            platform = "macos"
            findings = [FakeFinding("high", "security"), FakeFinding("low", "diagnostic")]

        entry = S.log_scan_result(FakeResult())
        assert entry["platform"] == "macos"
        assert entry["finding_count"] == 2
        assert entry["severities"] == {"high": 1, "low": 1}
        assert log_file.exists()
