"""Tests for the system restore-point wrapper (Time Machine / System Restore / timeshift)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

import errex.restore_points as RP


def _mock_run(stdout="", returncode=0):
    class R:
        pass
    r = R()
    r.stdout = stdout
    r.stderr = ""
    r.returncode = returncode
    return r


def test_is_supported_macos(monkeypatch):
    monkeypatch.setattr(RP.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(RP.shutil, "which", lambda name: "/usr/bin/tmutil" if name == "tmutil" else None)
    assert RP.is_supported() is True


def test_is_supported_macos_missing_tool(monkeypatch):
    monkeypatch.setattr(RP.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(RP.shutil, "which", lambda name: None)
    assert RP.is_supported() is False


def test_is_supported_linux_requires_timeshift(monkeypatch):
    monkeypatch.setattr(RP.platform, "system", lambda: "Linux")
    monkeypatch.setattr(RP.shutil, "which", lambda name: "/usr/bin/timeshift" if name == "timeshift" else None)
    assert RP.is_supported() is True


def test_is_supported_unknown_platform(monkeypatch):
    monkeypatch.setattr(RP.platform, "system", lambda: "Plan9")
    assert RP.is_supported() is False


def test_create_restore_point_macos_success(monkeypatch):
    monkeypatch.setattr(RP.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(RP.shutil, "which", lambda name: "/usr/bin/tmutil")
    with patch("errex.restore_points.subprocess.run", return_value=_mock_run("Created snapshot")):
        resp = RP.create_restore_point()
    assert resp.get("ok") is True
    assert resp["tool"] == "Time Machine (local snapshot)"


def test_create_restore_point_macos_missing_tool(monkeypatch):
    monkeypatch.setattr(RP.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(RP.shutil, "which", lambda name: None)
    resp = RP.create_restore_point()
    assert "error" in resp


def test_create_restore_point_macos_failure(monkeypatch):
    monkeypatch.setattr(RP.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(RP.shutil, "which", lambda name: "/usr/bin/tmutil")
    with patch("errex.restore_points.subprocess.run", return_value=_mock_run("denied", returncode=1)):
        resp = RP.create_restore_point()
    assert "error" in resp


def test_create_restore_point_linux_missing_timeshift(monkeypatch):
    monkeypatch.setattr(RP.platform, "system", lambda: "Linux")
    monkeypatch.setattr(RP.shutil, "which", lambda name: None)
    resp = RP.create_restore_point()
    assert "error" in resp
    assert "timeshift" in resp["error"]


def test_create_restore_point_linux_success(monkeypatch):
    monkeypatch.setattr(RP.platform, "system", lambda: "Linux")
    monkeypatch.setattr(RP.shutil, "which", lambda name: "/usr/bin/timeshift")
    with patch("errex.restore_points.subprocess.run", return_value=_mock_run("Snapshot created")):
        resp = RP.create_restore_point()
    assert resp.get("ok") is True
    assert resp["tool"] == "timeshift"


def test_create_restore_point_windows_success(monkeypatch):
    monkeypatch.setattr(RP.platform, "system", lambda: "Windows")
    monkeypatch.setattr(RP.shutil, "which", lambda name: "powershell.exe")
    with patch("errex.restore_points.subprocess.run", return_value=_mock_run("Restore point created")):
        resp = RP.create_restore_point()
    assert resp.get("ok") is True
    assert resp["tool"] == "Windows System Restore"


def test_create_restore_point_unsupported_platform(monkeypatch):
    monkeypatch.setattr(RP.platform, "system", lambda: "Plan9")
    resp = RP.create_restore_point()
    assert "error" in resp
