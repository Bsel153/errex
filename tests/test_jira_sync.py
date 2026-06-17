import json
import pytest
from unittest.mock import patch, MagicMock
from errex.jira_sync import create_issue, _get_credentials, _PRIORITY_MAP


def _fake_ticket(severity="high", title="SSH weak config"):
    t = MagicMock()
    t.severity = severity
    t.title = title
    t.id = "T-042"
    t.detail = "Password authentication is enabled."
    t.source = "scan"
    return t


def test_get_credentials_from_env(monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://team.atlassian.net")
    monkeypatch.setenv("JIRA_USER", "user@co.com")
    monkeypatch.setenv("JIRA_TOKEN", "secret123")
    creds = _get_credentials()
    assert creds == ("https://team.atlassian.net", "user@co.com", "secret123")


def test_get_credentials_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://team.atlassian.net/")
    monkeypatch.setenv("JIRA_USER", "u")
    monkeypatch.setenv("JIRA_TOKEN", "t")
    creds = _get_credentials()
    assert creds[0] == "https://team.atlassian.net"


def test_get_credentials_missing(monkeypatch):
    monkeypatch.delenv("JIRA_URL", raising=False)
    monkeypatch.delenv("JIRA_USER", raising=False)
    monkeypatch.delenv("JIRA_TOKEN", raising=False)
    assert _get_credentials() is None


def test_create_issue_no_credentials(monkeypatch):
    monkeypatch.delenv("JIRA_URL", raising=False)
    monkeypatch.delenv("JIRA_USER", raising=False)
    monkeypatch.delenv("JIRA_TOKEN", raising=False)
    result = create_issue(_fake_ticket())
    assert "error" in result
    assert "credentials" in result["error"].lower() or "JIRA" in result["error"]


def test_create_issue_no_project(monkeypatch):
    monkeypatch.delenv("JIRA_PROJECT", raising=False)
    result = create_issue(
        _fake_ticket(),
        jira_url="https://x.atlassian.net",
        jira_user="u",
        jira_token="t",
    )
    assert "error" in result
    assert "project" in result["error"].lower()


def test_create_issue_success():
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps({"key": "PROJ-123", "id": "10001"}).encode()
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    with patch("errex.jira_sync.urllib.request.urlopen", return_value=fake_resp):
        result = create_issue(
            _fake_ticket(),
            jira_url="https://team.atlassian.net",
            jira_user="user@co.com",
            jira_token="tok",
            project_key="PROJ",
        )
    assert result["key"] == "PROJ-123"
    assert "atlassian.net/browse/PROJ-123" in result["url"]


def test_create_issue_sends_correct_payload():
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps({"key": "X-1"}).encode()
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    with patch("errex.jira_sync.urllib.request.urlopen", return_value=fake_resp) as mock_open:
        create_issue(
            _fake_ticket(severity="critical", title="Firewall off"),
            jira_url="https://j.co",
            jira_user="u",
            jira_token="t",
            project_key="SEC",
        )

    req = mock_open.call_args[0][0]
    body = json.loads(req.data)
    assert body["fields"]["project"]["key"] == "SEC"
    assert body["fields"]["priority"]["name"] == "Highest"
    assert "CRITICAL" in body["fields"]["summary"]
    assert "errex" in body["fields"]["labels"]


def test_priority_map_covers_all_severities():
    for sev in ("critical", "high", "medium", "low", "info"):
        assert sev in _PRIORITY_MAP


def test_create_issue_http_error():
    from urllib.error import HTTPError
    with patch("errex.jira_sync.urllib.request.urlopen",
               side_effect=HTTPError("url", 401, "Unauthorized", {}, None)):
        result = create_issue(
            _fake_ticket(),
            jira_url="https://j.co",
            jira_user="u",
            jira_token="t",
            project_key="P",
        )
    assert "error" in result
    assert "401" in result["error"]
