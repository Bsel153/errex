"""Tests for Linear issue sync module."""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from errex.linear_sync import create_issue, _PRIORITY_MAP


def _fake_ticket(severity="high", title="SSH weak config"):
    t = MagicMock()
    t.severity = severity
    t.title = title
    t.id = "T-042"
    t.detail = "Password authentication is enabled."
    t.source = "scan"
    return t


def test_priority_map_covers_all_severities():
    for sev in ("critical", "high", "medium", "low", "info"):
        assert sev in _PRIORITY_MAP


def test_priority_critical_is_urgent():
    assert _PRIORITY_MAP["critical"] == 1


def test_priority_info_is_no_priority():
    assert _PRIORITY_MAP["info"] == 0


def test_create_issue_no_token(monkeypatch):
    monkeypatch.delenv("LINEAR_TOKEN", raising=False)
    result = create_issue(_fake_ticket(), team_id="TEAM-1", token=None)
    assert "error" in result
    assert "token" in result["error"].lower()


def test_create_issue_no_team(monkeypatch):
    monkeypatch.delenv("LINEAR_TEAM_ID", raising=False)
    result = create_issue(_fake_ticket(), team_id=None, token="tok")
    assert "error" in result
    assert "team" in result["error"].lower()


def test_create_issue_success():
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps({
        "data": {
            "issueCreate": {
                "success": True,
                "issue": {
                    "id": "issue-123",
                    "identifier": "ENG-42",
                    "url": "https://linear.app/team/issue/ENG-42",
                }
            }
        }
    }).encode()
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    with patch("errex.linear_sync.urllib.request.urlopen", return_value=fake_resp):
        result = create_issue(_fake_ticket(), team_id="TEAM-1", token="tok")

    assert result["identifier"] == "ENG-42"
    assert "linear.app" in result["url"]


def test_create_issue_graphql_error():
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps({
        "errors": [{"message": "Team not found"}]
    }).encode()
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    with patch("errex.linear_sync.urllib.request.urlopen", return_value=fake_resp):
        result = create_issue(_fake_ticket(), team_id="TEAM-1", token="tok")

    assert "error" in result
    assert "Team not found" in result["error"]


def test_create_issue_http_error():
    from urllib.error import HTTPError
    with patch("errex.linear_sync.urllib.request.urlopen",
               side_effect=HTTPError("url", 401, "Unauthorized", {}, None)):
        result = create_issue(_fake_ticket(), team_id="T1", token="tok")
    assert "error" in result
    assert "401" in result["error"]


def test_create_issue_sends_mutation():
    """Verify that a GraphQL mutation is sent to the Linear API."""
    posted = {}
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps({
        "data": {"issueCreate": {"success": True, "issue": {"id": "i1", "identifier": "X-1", "url": "u"}}}
    }).encode()
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    def fake_open(req, timeout):
        posted["body"] = json.loads(req.data)
        posted["auth"] = req.get_header("Authorization")
        return fake_resp

    with patch("errex.linear_sync.urllib.request.urlopen", side_effect=fake_open):
        create_issue(_fake_ticket(severity="critical", title="Big problem"), team_id="T1", token="mytoken")

    assert "mutation" in posted["body"]["query"].lower()
    assert posted["body"]["variables"]["teamId"] == "T1"
    assert posted["body"]["variables"]["priority"] == 1  # critical -> 1
    assert "Bearer mytoken" in posted["auth"]
