import json
import pytest
from unittest.mock import patch, MagicMock
from errex.slack_notify import (
    _get_webhook, _post, notify_new_ticket, notify_ticket_closed,
    notify_fix_applied, notify_scan_summary,
)


def _fake_ticket(severity="high", title="Test issue", ticket_id="T-001"):
    t = MagicMock()
    t.severity = severity
    t.title = title
    t.id = ticket_id
    t.detail = "Detail text for the finding."
    t.source = "scan"
    return t


def test_get_webhook_explicit():
    assert _get_webhook("https://hooks.slack.com/foo") == "https://hooks.slack.com/foo"


def test_get_webhook_env(monkeypatch):
    monkeypatch.setenv("ERREX_SLACK_WEBHOOK", "https://hooks.slack.com/bar")
    assert _get_webhook() == "https://hooks.slack.com/bar"


def test_get_webhook_none(monkeypatch):
    monkeypatch.delenv("ERREX_SLACK_WEBHOOK", raising=False)
    assert _get_webhook() is None


def test_post_success():
    fake_resp = MagicMock()
    fake_resp.status = 200
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)
    with patch("errex.slack_notify.urllib.request.urlopen", return_value=fake_resp):
        result = _post("https://hooks.slack.com/test", {"text": "hi"})
    assert result["ok"] is True


def test_post_http_error():
    from urllib.error import HTTPError
    with patch("errex.slack_notify.urllib.request.urlopen",
               side_effect=HTTPError("url", 403, "Forbidden", {}, None)):
        result = _post("https://hooks.slack.com/test", {"text": "hi"})
    assert "error" in result
    assert "403" in result["error"]


def test_notify_new_ticket_no_webhook(monkeypatch):
    monkeypatch.delenv("ERREX_SLACK_WEBHOOK", raising=False)
    result = notify_new_ticket(_fake_ticket())
    assert "error" in result


def test_notify_new_ticket_posts():
    with patch("errex.slack_notify._post", return_value={"ok": True}) as mock_post:
        result = notify_new_ticket(_fake_ticket(), webhook_url="https://hooks.slack.com/x")
    assert result["ok"]
    payload = mock_post.call_args[0][1]
    assert "Test issue" in payload["text"]


def test_notify_new_ticket_with_github_url():
    with patch("errex.slack_notify._post", return_value={"ok": True}) as mock_post:
        notify_new_ticket(
            _fake_ticket(),
            webhook_url="https://hooks.slack.com/x",
            github_issue_url="https://github.com/o/r/issues/1",
        )
    payload = mock_post.call_args[0][1]
    assert "github.com" in payload["text"]


def test_notify_ticket_closed_posts():
    with patch("errex.slack_notify._post", return_value={"ok": True}) as mock_post:
        result = notify_ticket_closed(_fake_ticket(), webhook_url="https://hooks.slack.com/x")
    assert result["ok"]
    assert "Resolved" in mock_post.call_args[0][1]["text"]


def test_notify_fix_applied_posts():
    with patch("errex.slack_notify._post", return_value={"ok": True}) as mock_post:
        result = notify_fix_applied("Fixed SSH config", webhook_url="https://hooks.slack.com/x")
    assert result["ok"]
    assert "Fixed SSH config" in mock_post.call_args[0][1]["text"]


def test_notify_scan_summary_all_clear():
    with patch("errex.slack_notify._post", return_value={"ok": True}) as mock_post:
        notify_scan_summary(0, 0, 0, webhook_url="https://hooks.slack.com/x")
    payload = mock_post.call_args[0][1]
    assert "All Clear" in payload["text"]
    assert "blocks" in payload


def test_notify_scan_summary_critical():
    with patch("errex.slack_notify._post", return_value={"ok": True}) as mock_post:
        notify_scan_summary(5, 2, 3, webhook_url="https://hooks.slack.com/x")
    payload = mock_post.call_args[0][1]
    assert "Critical" in payload["text"]


def test_notify_scan_summary_open_no_critical():
    with patch("errex.slack_notify._post", return_value={"ok": True}) as mock_post:
        notify_scan_summary(3, 0, 1, webhook_url="https://hooks.slack.com/x")
    payload = mock_post.call_args[0][1]
    assert "3 Open" in payload["text"]
