"""Tests for the OS text-to-speech accessibility helper."""
from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from errex.utils import speak


def test_speak_empty_text_does_nothing():
    with patch("errex.utils.subprocess.run") as mock_run:
        assert speak("   ") is False
    mock_run.assert_not_called()


def test_speak_macos_uses_say(monkeypatch):
    monkeypatch.setattr("errex.utils.platform.system", lambda: "Darwin")
    with patch("errex.utils.subprocess.run") as mock_run:
        assert speak("hello world") is True
    args, kwargs = mock_run.call_args
    assert args[0] == ["say", "hello world"]


def test_speak_linux_prefers_spd_say(monkeypatch):
    monkeypatch.setattr("errex.utils.platform.system", lambda: "Linux")
    with patch("errex.utils.subprocess.run") as mock_run:
        assert speak("hello") is True
    args, kwargs = mock_run.call_args
    assert args[0] == ["spd-say", "hello"]


def test_speak_linux_falls_back_to_espeak(monkeypatch):
    monkeypatch.setattr("errex.utils.platform.system", lambda: "Linux")

    def fake_run(cmd, **kwargs):
        if cmd[0] == "spd-say":
            raise FileNotFoundError()
        return None

    with patch("errex.utils.subprocess.run", side_effect=fake_run) as mock_run:
        assert speak("hello") is True
    last_cmd = mock_run.call_args_list[-1][0][0]
    assert last_cmd == ["espeak", "hello"]


def test_speak_linux_no_tts_available(monkeypatch):
    monkeypatch.setattr("errex.utils.platform.system", lambda: "Linux")
    with patch("errex.utils.subprocess.run", side_effect=FileNotFoundError()):
        assert speak("hello") is False


def test_speak_windows_uses_powershell_with_stdin(monkeypatch):
    monkeypatch.setattr("errex.utils.platform.system", lambda: "Windows")
    with patch("errex.utils.subprocess.run") as mock_run:
        assert speak("hello") is True
    args, kwargs = mock_run.call_args
    assert args[0][0] == "powershell"
    assert kwargs.get("input") == "hello"


def test_speak_swallows_subprocess_errors(monkeypatch):
    monkeypatch.setattr("errex.utils.platform.system", lambda: "Darwin")
    with patch("errex.utils.subprocess.run", side_effect=subprocess.SubprocessError("boom")):
        assert speak("hello") is False


def test_speak_unknown_platform_returns_false(monkeypatch):
    monkeypatch.setattr("errex.utils.platform.system", lambda: "Plan9")
    with patch("errex.utils.subprocess.run") as mock_run:
        assert speak("hello") is False
    mock_run.assert_not_called()
