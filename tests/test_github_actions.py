"""Tests for GitHub Actions failure explainer."""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from errex.github_actions import _parse_run_url, explain_github_actions


def test_parse_run_url_valid():
    result = _parse_run_url("https://github.com/octocat/hello-world/actions/runs/12345")
    assert result == ("octocat", "hello-world", "12345")


def test_parse_run_url_with_trailing_slash():
    result = _parse_run_url("https://github.com/octocat/repo/actions/runs/99 ")
    assert result == ("octocat", "repo", "99")


def test_parse_run_url_invalid():
    assert _parse_run_url("https://github.com/octocat/repo") is None
    assert _parse_run_url("https://example.com/foo") is None
    assert _parse_run_url("not a url") is None


def test_explain_github_actions_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        explain_github_actions("https://github.com/o/r/actions/runs/1")


def test_explain_github_actions_bad_url(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    with pytest.raises(SystemExit):
        explain_github_actions("https://github.com/o/r/pulls/1")


def test_explain_github_actions_api_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    import urllib.error
    with patch("errex.github_actions.urllib.request.urlopen",
               side_effect=urllib.error.HTTPError("", 404, "Not Found", {}, None)):
        with pytest.raises(SystemExit):
            explain_github_actions("https://github.com/o/r/actions/runs/1")


def test_explain_github_actions_no_failed_jobs(monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")

    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps({
        "jobs": [{"id": 1, "name": "build", "conclusion": "success"}]
    }).encode()
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    with patch("errex.github_actions.urllib.request.urlopen", return_value=fake_resp):
        explain_github_actions("https://github.com/o/r/actions/runs/1")
    # Should say no failed jobs — just return without error
