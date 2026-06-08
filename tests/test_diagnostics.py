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


class TestMemoryPressure:
    def test_returns_none_for_normal_usage(self):
        with patch("errex.scanners.diagnostics._sys_platform.system", return_value="Linux"), \
             patch("errex.scanners.diagnostics._linux_memory", return_value=(60.0, 0.0)):
            assert diagnostics.check_memory_pressure() is None

    def test_flags_high_memory_usage(self):
        with patch("errex.scanners.diagnostics._sys_platform.system", return_value="Linux"), \
             patch("errex.scanners.diagnostics._linux_memory", return_value=(92.0, 0.0)):
            finding = diagnostics.check_memory_pressure()
        assert isinstance(finding, Finding)
        assert finding.id == "diag-memory-pressure"
        assert finding.category == "diagnostic"
        assert finding.severity == "medium"

    def test_flags_critical_memory_and_swap(self):
        with patch("errex.scanners.diagnostics._sys_platform.system", return_value="Linux"), \
             patch("errex.scanners.diagnostics._linux_memory", return_value=(97.0, 5000.0)):
            finding = diagnostics.check_memory_pressure()
        assert finding.severity == "high"
        assert "swapped" in finding.detail

    def test_returns_none_when_stats_unavailable(self):
        with patch("errex.scanners.diagnostics._sys_platform.system", return_value="Linux"), \
             patch("errex.scanners.diagnostics._linux_memory", return_value=None):
            assert diagnostics.check_memory_pressure() is None

    def test_returns_none_on_exception(self):
        with patch("errex.scanners.diagnostics._sys_platform.system", side_effect=RuntimeError):
            assert diagnostics.check_memory_pressure() is None


class TestNetworkHealth:
    def test_returns_none_for_healthy_connection(self):
        with patch("errex.scanners.diagnostics._ping", return_value=(0.0, 20.0)):
            assert diagnostics.check_network_health() is None

    def test_flags_high_packet_loss(self):
        with patch("errex.scanners.diagnostics._ping", return_value=(60.0, 30.0)):
            finding = diagnostics.check_network_health()
        assert isinstance(finding, Finding)
        assert finding.id == "diag-network-health"
        assert finding.severity == "high"
        assert "loss" in finding.title

    def test_flags_high_latency(self):
        with patch("errex.scanners.diagnostics._ping", return_value=(0.0, 250.0)):
            finding = diagnostics.check_network_health()
        assert isinstance(finding, Finding)
        assert finding.severity == "medium"
        assert "latency" in finding.title

    def test_returns_none_when_ping_unavailable(self):
        with patch("errex.scanners.diagnostics._ping", return_value=(None, None)):
            assert diagnostics.check_network_health() is None


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

    def test_no_unauthorized_alert_on_first_ever_scan(self, monkeypatch, tmp_path):
        self._patch_history(monkeypatch, tmp_path)
        findings = diagnostics.check_offline_devices([
            {"ip": "10.0.0.5", "hostname": "tv"},
            {"ip": "10.0.0.6", "hostname": "speaker"},
        ])
        assert findings == []

    def test_flags_unrecognized_new_device(self, monkeypatch, tmp_path):
        self._patch_history(monkeypatch, tmp_path)
        known = {"ip": "10.0.0.5", "hostname": "tv"}
        diagnostics.check_offline_devices([known])

        intruder = {"ip": "10.0.0.99", "hostname": "unknown-device"}
        findings = diagnostics.check_offline_devices([known, intruder])
        new_findings = [f for f in findings if f.id.startswith("diag-device-new-")]
        assert len(new_findings) == 1
        assert new_findings[0].id == "diag-device-new-10_0_0_99"
        assert new_findings[0].category == "security"
        assert "unknown-device" in new_findings[0].title

        # Once seen, it shouldn't be re-flagged as "new" on the next scan
        again = diagnostics.check_offline_devices([known, intruder])
        assert all(not f.id.startswith("diag-device-new-") for f in again)


class TestPredictiveDiskFailure:
    def _patch_log(self, monkeypatch, tmp_path):
        log_file = tmp_path / "scan_log.jsonl"
        monkeypatch.setattr("errex._scan_scheduler._SCAN_LOG", log_file)
        return log_file

    def _write_samples(self, log_file, samples):
        import json as _json
        with open(log_file, "w", encoding="utf-8") as f:
            for ts, pct in samples:
                f.write(_json.dumps({"timestamp": ts, "disk_free_pct": pct}) + "\n")

    def test_returns_none_with_too_few_samples(self, monkeypatch, tmp_path):
        log_file = self._patch_log(monkeypatch, tmp_path)
        self._write_samples(log_file, [("2026-06-01T00:00:00Z", 50.0)])
        assert diagnostics.check_predictive_disk_failure() is None

    def test_returns_none_when_space_is_stable(self, monkeypatch, tmp_path):
        log_file = self._patch_log(monkeypatch, tmp_path)
        self._write_samples(log_file, [
            ("2026-06-01T00:00:00Z", 50.0),
            ("2026-06-04T00:00:00Z", 50.0),
            ("2026-06-08T00:00:00Z", 49.9),
        ])
        assert diagnostics.check_predictive_disk_failure() is None

    def test_flags_rapid_decline_projected_to_fill_soon(self, monkeypatch, tmp_path):
        log_file = self._patch_log(monkeypatch, tmp_path)
        self._write_samples(log_file, [
            ("2026-06-01T00:00:00Z", 40.0),
            ("2026-06-04T00:00:00Z", 25.0),
            ("2026-06-08T00:00:00Z", 12.0),
        ])
        finding = diagnostics.check_predictive_disk_failure()
        assert isinstance(finding, Finding)
        assert finding.id == "diag-predictive-disk-full"
        assert finding.category == "diagnostic"
        assert finding.severity in ("high", "medium")

    def test_returns_none_when_decline_too_slow_to_matter(self, monkeypatch, tmp_path):
        log_file = self._patch_log(monkeypatch, tmp_path)
        self._write_samples(log_file, [
            ("2026-01-01T00:00:00Z", 80.0),
            ("2026-03-01T00:00:00Z", 78.0),
            ("2026-06-01T00:00:00Z", 76.0),
        ])
        # declining, but so slowly the projection is far beyond the warning window
        assert diagnostics.check_predictive_disk_failure() is None

    def test_returns_none_without_log_file(self, monkeypatch, tmp_path):
        self._patch_log(monkeypatch, tmp_path)
        assert diagnostics.check_predictive_disk_failure() is None


class TestDuplicateFiles:
    def test_returns_none_with_no_scan_dirs(self, monkeypatch, tmp_path):
        monkeypatch.setattr(diagnostics.Path, "home", staticmethod(lambda: tmp_path))
        assert diagnostics.check_duplicate_files() is None

    def test_flags_large_duplicate_groups(self, monkeypatch, tmp_path):
        monkeypatch.setattr(diagnostics.Path, "home", staticmethod(lambda: tmp_path))
        downloads = tmp_path / "Downloads"
        downloads.mkdir()
        payload = b"x" * (30 * 1024 * 1024)  # 30 MB
        for name in ("movie.mp4", "movie (copy).mp4", "movie (copy 2).mp4"):
            (downloads / name).write_bytes(payload)

        finding = diagnostics.check_duplicate_files()
        assert isinstance(finding, Finding)
        assert finding.id == "diag-duplicate-files"
        assert finding.category == "diagnostic"
        assert "MB" in finding.title

    def test_ignores_distinct_files_of_same_size(self, monkeypatch, tmp_path):
        monkeypatch.setattr(diagnostics.Path, "home", staticmethod(lambda: tmp_path))
        downloads = tmp_path / "Downloads"
        downloads.mkdir()
        (downloads / "a.bin").write_bytes(b"a" * (60 * 1024))
        (downloads / "b.bin").write_bytes(b"b" * (60 * 1024))
        assert diagnostics.check_duplicate_files() is None


class TestBrowserJunk:
    def test_returns_none_when_no_cache_dirs_exist(self, monkeypatch, tmp_path):
        monkeypatch.setattr(diagnostics.Path, "home", staticmethod(lambda: tmp_path))
        monkeypatch.setattr(diagnostics._sys_platform, "system", lambda: "Linux")
        assert diagnostics.check_browser_junk() is None

    def test_flags_large_caches(self, monkeypatch, tmp_path):
        monkeypatch.setattr(diagnostics.Path, "home", staticmethod(lambda: tmp_path))
        monkeypatch.setattr(diagnostics._sys_platform, "system", lambda: "Linux")
        cache_dir = tmp_path / ".cache" / "google-chrome"
        cache_dir.mkdir(parents=True)
        (cache_dir / "blob").write_bytes(b"x" * (250 * 1024 * 1024))

        finding = diagnostics.check_browser_junk()
        assert isinstance(finding, Finding)
        assert finding.id == "diag-browser-cache"
        assert finding.severity == "low"
        assert "Chrome" in finding.detail

    def test_returns_none_for_small_caches(self, monkeypatch, tmp_path):
        monkeypatch.setattr(diagnostics.Path, "home", staticmethod(lambda: tmp_path))
        monkeypatch.setattr(diagnostics._sys_platform, "system", lambda: "Linux")
        cache_dir = tmp_path / ".cache" / "google-chrome"
        cache_dir.mkdir(parents=True)
        (cache_dir / "blob").write_bytes(b"x" * (5 * 1024 * 1024))
        assert diagnostics.check_browser_junk() is None


def test_get_checks_returns_callables():
    checks = diagnostics.get_checks()
    names = [name for name, _ in checks]
    assert "Disk health" in names
    assert "Startup load" in names
    assert "Memory pressure" in names
    assert "Network health" in names
    assert "Disk trend" in names
    assert "Duplicate files" in names
    assert "Browser cache" in names
    for _, fn in checks:
        assert callable(fn)
