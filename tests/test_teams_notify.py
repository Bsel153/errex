"""Tests for Microsoft Teams webhook notifications."""
from __future__ import annotations

import json
from unittest.mock import patch
import urllib.error

import pytest

from errex.teams_notify import (
    notify_new_ticket,
    notify_scan_summary,
    notify_explanation,
    _get_webhook,
)
from errex.tickets import Ticket


def _make_ticket(**kwargs):
    defaults = {
        "id": "T-001",
        "title": "Firewall disabled",
        "severity": "critical",
        "detail": "ufw is inactive",
        "status": "open",
        "source": "scan",
        "finding_id": "linux-firewall-disabled",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "github_issue_number": None,
        "snooze_until": None,
    }
    defaults.update(kwargs)
    return Ticket(defaults)


def test_get_webhook_from_env(monkeypatch):
    monkeypatch.setenv("ERREX_TEAMS_WEBHOOK", "https://outlook.office.com/webhook/test")
    assert _get_webhook() == "https://outlook.office.com/webhook/test"


def test_get_webhook_explicit():
    assert _get_webhook("https://example.com/wh") == "https://example.com/wh"


def test_get_webhook_none(monkeypatch):
    monkeypatch.delenv("ERREX_TEAMS_WEBHOOK", raising=False)
    assert _get_webhook() is None


def test_notify_new_ticket_no_webhook(monkeypatch):
    monkeypatch.delenv("ERREX_TEAMS_WEBHOOK", raising=False)
    result = notify_new_ticket(_make_ticket(), webhook_url=None)
    assert "error" in result


def test_notify_new_ticket_success():
    posted = {}

    class FakeResp:
        status = 200
        def read(self): return b"1"
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_urlopen(req, timeout):
        posted["data"] = json.loads(req.data)
        return FakeResp()

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = notify_new_ticket(_make_ticket(), webhook_url="https://teams.example.com/wh")

    assert result.get("ok") is True
    assert posted["data"]["@type"] == "MessageCard"
    assert "Firewall disabled" in posted["data"]["sections"][0]["activityTitle"]


def test_notify_new_ticket_with_github_url():
    posted = {}

    class FakeResp:
        status = 200
        def read(self): return b"1"
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_urlopen(req, timeout):
        posted["data"] = json.loads(req.data)
        return FakeResp()

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        notify_new_ticket(
            _make_ticket(),
            webhook_url="https://teams.example.com/wh",
            github_issue_url="https://github.com/org/repo/issues/7",
        )

    facts = posted["data"]["sections"][0]["facts"]
    fact_names = [f["name"] for f in facts]
    assert "GitHub Issue" in fact_names


def test_notify_new_ticket_http_error():
    def _raise(req, timeout):
        raise urllib.error.HTTPError(url="", code=400, msg="Bad Request", hdrs=None, fp=None)

    with patch("urllib.request.urlopen", side_effect=_raise):
        result = notify_new_ticket(_make_ticket(), webhook_url="https://teams.example.com/wh")

    assert "error" in result
    assert "400" in result["error"]


def test_notify_scan_summary_no_findings():
    posted = {}

    class FakeResp:
        status = 200
        def read(self): return b"1"
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_urlopen(req, timeout):
        posted["data"] = json.loads(req.data)
        return FakeResp()

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        notify_scan_summary([], webhook_url="https://teams.example.com/wh")

    assert "All Clear" in posted["data"]["sections"][0]["activityTitle"]


def test_notify_explanation_success():
    posted = {}

    class FakeResp:
        status = 200
        def read(self): return b"1"
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_urlopen(req, timeout):
        posted["data"] = json.loads(req.data)
        return FakeResp()

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = notify_explanation("This is the explanation", "some error", webhook_url="https://teams.example.com/wh")

    assert result.get("ok") is True
    assert posted["data"]["@type"] == "MessageCard"


def test_notify_explanation_no_webhook(monkeypatch):
    monkeypatch.delenv("ERREX_TEAMS_WEBHOOK", raising=False)
    result = notify_explanation("exp", "err", webhook_url=None)
    assert "error" in result


def test_message_card_structure():
    from errex.teams_notify import _message_card
    card = _message_card("summary", "title", [{"name": "K", "value": "V"}])
    assert card["@type"] == "MessageCard"
    assert card["@context"] == "http://schema.org/extensions"
    assert card["sections"][0]["activityTitle"] == "title"
    assert card["sections"][0]["facts"][0]["name"] == "K"
