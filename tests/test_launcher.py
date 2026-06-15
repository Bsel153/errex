"""Tests for desktop shortcut creation."""
from __future__ import annotations

import platform
import stat
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from errex.launcher import (
    create_shortcut,
    _create_linux_desktop,
    _create_macos_app,
    _create_windows_shortcut,
)


def test_create_linux_desktop(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    desktop = tmp_path / "Desktop"
    desktop.mkdir()

    with patch("platform.system", return_value="Linux"):
        path = _create_linux_desktop()

    assert path.exists()
    assert path.suffix == ".desktop"
    content = path.read_text()
    assert "[Desktop Entry]" in content
    assert "errex" in content
    assert "Exec=" in content


def test_linux_desktop_is_executable(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / "Desktop").mkdir()

    path = _create_linux_desktop()
    assert path.stat().st_mode & stat.S_IEXEC


def test_linux_launcher_script_created(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / "Desktop").mkdir()

    _create_linux_desktop()
    launcher = tmp_path / ".local" / "bin" / "errex-launcher.sh"
    assert launcher.exists()
    content = launcher.read_text()
    assert "--web" in content
    assert "localhost:8787" in content


def test_linux_desktop_also_installed_to_applications(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / "Desktop").mkdir()

    _create_linux_desktop()
    apps = tmp_path / ".local" / "share" / "applications" / "errex.desktop"
    assert apps.exists()


def test_macos_app_structure(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / "Desktop").mkdir()

    path = _create_macos_app()
    assert path.name == "errex.app"
    assert (path / "Contents" / "MacOS" / "errex-launcher").exists()
    assert (path / "Contents" / "Info.plist").exists()


def test_macos_launcher_is_executable(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / "Desktop").mkdir()

    path = _create_macos_app()
    launcher = path / "Contents" / "MacOS" / "errex-launcher"
    assert launcher.stat().st_mode & stat.S_IEXEC


def test_macos_launcher_contains_web_flag(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / "Desktop").mkdir()

    path = _create_macos_app()
    launcher = path / "Contents" / "MacOS" / "errex-launcher"
    content = launcher.read_text()
    assert "--web" in content
    assert "localhost:8787" in content


def test_windows_bat_created(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / "Desktop").mkdir()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        path = _create_windows_shortcut()

    assert path.suffix in (".bat", ".lnk")


def test_windows_bat_content(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / "Desktop").mkdir()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        path = _create_windows_shortcut()

    if path.suffix == ".bat":
        content = path.read_text()
        assert "--web" in content
        assert "localhost:8787" in content


def test_create_shortcut_dispatches_by_os(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / "Desktop").mkdir()

    for os_name, expected_fn in [
        ("Linux", "_create_linux_desktop"),
        ("Darwin", "_create_macos_app"),
    ]:
        with patch("platform.system", return_value=os_name):
            with patch(f"errex.launcher.{expected_fn}",
                       return_value=tmp_path / "shortcut") as mock_fn:
                create_shortcut()
                mock_fn.assert_called_once()


def test_install_scripts_exist():
    scripts = Path(__file__).parent.parent / "scripts"
    assert (scripts / "install.sh").exists()
    assert (scripts / "install.bat").exists()


def test_install_sh_is_bash(tmp_path):
    sh = Path(__file__).parent.parent / "scripts" / "install.sh"
    content = sh.read_text()
    assert "#!/usr/bin/env bash" in content
    assert "pip install" in content
    assert "errex --web" in content


def test_install_bat_is_windows(tmp_path):
    bat = Path(__file__).parent.parent / "scripts" / "install.bat"
    content = bat.read_text()
    assert "pip install" in content
    assert "errex --web" in content
