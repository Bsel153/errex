from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from errex.scanners._base import Finding
from errex.scanners import diagnostics


class TestDiskHealth:
    def test_returns_none_when_plenty_of_space(self):
        usage = MagicMock(total=1_000_000_000_000, free=500_000_000_000, used=500_000_000_000)
        with patch("errex.scanners.diagnostics.shutil.disk_usage", return_value=usage):
            assert diagnostics.check_disk_health() is None

    def test_flags_low_disk_space(self):
        usage = MagicMock(total=1_000_000_000_000, free=20_000_000_000, used=980_000_000_000)
        with patch("errex.scanners.diagnostics.shutil.disk_usage", return_value=usage):
            finding = diagnostics.check_disk_health()
        assert isinstance(finding, Finding)
        assert finding.id == "diag-disk-low-space"
        assert finding.category == "diagnostic"
        assert finding.severity in ("critical", "high", "medium")

    def test_severity_scales_with_free_space(self):
        critical_usage = MagicMock(total=1_000_000_000_000, free=10_000_000_000, used=990_000_000_000)
        with patch("errex.scanners.diagnostics.shutil.disk_usage", return_value=critical_usage):
            assert diagnostics.check_disk_health().severity == "critical"

        medium_usage = MagicMock(total=1_000_000_000_000, free=120_000_000_000, used=880_000_000_000)
        with patch("errex.scanners.diagnostics.shutil.disk_usage", return_value=medium_usage):
            assert diagnostics.check_disk_health().severity == "medium"

    def test_returns_none_on_os_error(self):
        with patch("errex.scanners.diagnostics.shutil.disk_usage", side_effect=OSError):
            assert diagnostics.check_disk_health() is None


class TestStartupItems:
    def test_returns_none_for_light_startup_load(self):
        with patch("errex.scanners.diagnostics._sys_platform.system", return_value="Linux"), \
             patch("errex.scanners.diagnostics._linux_startup_items", return_value=["a", "b"]):
            assert diagnostics.check_startup_items() is None

    def test_flags_heavy_startup_load(self):
        items = [f"item{i}" for i in range(20)]
        with patch("errex.scanners.diagnostics._sys_platform.system", return_value="Linux"), \
             patch("errex.scanners.diagnostics._linux_startup_items", return_value=items):
            finding = diagnostics.check_startup_items()
        assert isinstance(finding, Finding)
        assert finding.id == "diag-startup-load"
        assert finding.category == "diagnostic"
        assert "20" in finding.title

    def test_returns_none_on_exception(self):
        with patch("errex.scanners.diagnostics._sys_platform.system", side_effect=RuntimeError):
            assert diagnostics.check_startup_items() is None


class TestOfflineDeviceDetection:
    def _patch_history(self, monkeypatch, tmp_path):
        history_file = tmp_path / "devices.json"
        monkeypatch.setattr(diagnostics, "_DEVICE_HISTORY_FILE", history_file)
        return history_file

    def test_no_findings_on_first_scan(self, monkeypatch, tmp_path):
        self._patch_history(monkeypatch, tmp_path)
        findings = diagnostics.check_offline_devices([{"ip": "10.0.0.5", "hostname": "tv"}])
        assert findings == []

    def test_flags_device_missing_after_repeat_sightings(self, monkeypatch, tmp_path):
        history_file = self._patch_history(monkeypatch, tmp_path)

        device = {"ip": "10.0.0.5", "hostname": "thermostat"}
        diagnostics.check_offline_devices([device])
        diagnostics.check_offline_devices([device])

        findings = diagnostics.check_offline_devices([])
        assert len(findings) == 1
        assert findings[0].id == "diag-device-offline-10_0_0_5"
        assert findings[0].category == "diagnostic"
        assert "thermostat" in findings[0].title

        # Already-flagged offline devices shouldn't be re-flagged on every scan
        again = diagnostics.check_offline_devices([])
        assert again == []
        assert history_file.exists()

    def test_does_not_flag_device_seen_only_once(self, monkeypatch, tmp_path):
        self._patch_history(monkeypatch, tmp_path)
        device = {"ip": "10.0.0.9", "hostname": "lightbulb"}
        diagnostics.check_offline_devices([device])
        findings = diagnostics.check_offline_devices([])
        assert findings == []

    def test_device_returning_clears_offline_status(self, monkeypatch, tmp_path):
        self._patch_history(monkeypatch, tmp_path)
        device = {"ip": "10.0.0.7", "hostname": "speaker"}
        diagnostics.check_offline_devices([device])
        diagnostics.check_offline_devices([device])
        offline = diagnostics.check_offline_devices([])
        assert len(offline) == 1

        # Device comes back online
        diagnostics.check_offline_devices([device])
        history = diagnostics._load_device_history()
        assert history["10.0.0.7"]["status"] == "online"


def test_get_checks_returns_callables():
    checks = diagnostics.get_checks()
    names = [name for name, _ in checks]
    assert "Disk health" in names
    assert "Startup load" in names
    for _, fn in checks:
        assert callable(fn)
