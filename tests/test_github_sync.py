"""Tests for GitHub Issues sync."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.request

import pytest

from errex.github_sync import create_issue, close_issue, _parse_repo, _get_token
from errex.tickets import Ticket


def _make_ticket(**kwargs):
    defaults = {
        "id": "abc12345",
        "title": "SSH root login enabled",
        "severity": "high",
        "detail": "PermitRootLogin yes in /etc/ssh/sshd_config",
        "status": "open",
        "source": "scan",
        "finding_id": "ssh-root-login",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "github_issue_number": None,
        "snooze_until": None,
    }
    defaults.update(kwargs)
    return Ticket(defaults)


def test_parse_repo_valid():
    assert _parse_repo("myorg/myrepo") == ("myorg", "myrepo")


def test_parse_repo_invalid():
    assert _parse_repo("noslash") is None
    assert _parse_repo("trailing/") is None


def test_get_token_from_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken")
    assert _get_token() == "ghp_testtoken"


def test_get_token_explicit():
    assert _get_token("explicit-token") == "explicit-token"


def test_get_token_none(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert _get_token() is None


def test_create_issue_no_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    ticket = _make_ticket()
    result = create_issue(ticket, "myorg/myrepo", token=None)
    assert "error" in result
    assert "token" in result["error"].lower()


def test_create_issue_bad_repo(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake")
    ticket = _make_ticket()
    result = create_issue(ticket, "noslash", token="fake")
    assert "error" in result


def test_create_issue_success(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake")
    ticket = _make_ticket()

    _response = {"number": 42, "html_url": "https://github.com/org/repo/issues/42"}

    class FakeResp:
        def read(self): return json.dumps(_response).encode()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    with patch("urllib.request.urlopen", return_value=FakeResp()):
        result = create_issue(ticket, "org/repo", token="fake")

    assert result.get("number") == 42


def test_create_issue_http_error(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake")
    ticket = _make_ticket()

    def _raise(req, timeout):
        raise urllib.error.HTTPError(url="", code=422, msg="Unprocessable", hdrs=None, fp=None)

    with patch("urllib.request.urlopen", side_effect=_raise):
        result = create_issue(ticket, "org/repo", token="fake")

    assert "error" in result
    assert "422" in result["error"]


def test_close_issue_no_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    result = close_issue(42, "org/repo")
    assert "error" in result


def test_close_issue_success(monkeypatch):
    _response = {"number": 42, "state": "closed"}

    class FakeResp:
        def read(self): return json.dumps(_response).encode()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    with patch("urllib.request.urlopen", return_value=FakeResp()):
        result = close_issue(42, "org/repo", token="fake")

    assert result.get("state") == "closed"
