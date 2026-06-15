"""Tests for the opt-in cloud sync module."""
from __future__ import annotations

import json
import urllib.error
from unittest.mock import patch

import pytest

from errex.cloud_sync import (
    is_enabled,
    sync_scan_summary,
    sync_ticket_event,
    _get_endpoint,
)
from errex.tickets import Ticket


def _make_ticket(**kwargs):
    defaults = {
        "id": "abc12345",
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
        "notes": [],
    }
    defaults.update(kwargs)
    return Ticket(defaults)


class FakeResp:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *a): pass


def test_get_endpoint_from_env(monkeypatch):
    monkeypatch.setenv("ERREX_SYNC_URL", "https://api.example.com")
    monkeypatch.setenv("ERREX_SYNC_KEY", "secret")
    assert _get_endpoint() == ("https://api.example.com", "secret")


def test_get_endpoint_explicit_overrides_nothing(monkeypatch):
    monkeypatch.delenv("ERREX_SYNC_URL", raising=False)
    monkeypatch.delenv("ERREX_SYNC_KEY", raising=False)
    assert _get_endpoint("https://x.test", "key123") == ("https://x.test", "key123")


def test_get_endpoint_none(monkeypatch):
    monkeypatch.delenv("ERREX_SYNC_URL", raising=False)
    monkeypatch.delenv("ERREX_SYNC_KEY", raising=False)
    assert _get_endpoint() == (None, None)


def test_is_enabled_false_by_default(monkeypatch):
    monkeypatch.delenv("ERREX_SYNC_URL", raising=False)
    assert is_enabled({}) is False


def test_is_enabled_true_with_config():
    assert is_enabled({"sync_url": "https://api.example.com"}) is True


def test_is_enabled_true_with_env(monkeypatch):
    monkeypatch.setenv("ERREX_SYNC_URL", "https://api.example.com")
    assert is_enabled({}) is True


def test_sync_scan_summary_no_endpoint(monkeypatch):
    monkeypatch.delenv("ERREX_SYNC_URL", raising=False)
    monkeypatch.delenv("ERREX_SYNC_KEY", raising=False)
    result = sync_scan_summary({"finding_count": 3})
    assert "error" in result
    assert "not configured" in result["error"]


def test_sync_scan_summary_success():
    posted = {}

    def fake_urlopen(req, timeout):
        posted["url"] = req.full_url
        posted["data"] = json.loads(req.data)
        posted["headers"] = req.headers
        return FakeResp()

    summary = {"timestamp": "2026-01-01T00:00:00Z", "finding_count": 2,
               "severities": {"high": 1}, "categories": {"security": 1}}
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = sync_scan_summary(summary, url="https://api.example.com", key="secret")

    assert result.get("ok") is True
    assert posted["url"] == "https://api.example.com/v1/scans"
    assert posted["data"] == summary
    assert posted["headers"]["Authorization"] == "Bearer secret"


def test_sync_scan_summary_strips_trailing_slash():
    posted = {}

    def fake_urlopen(req, timeout):
        posted["url"] = req.full_url
        return FakeResp()

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        sync_scan_summary({"finding_count": 0}, url="https://api.example.com/")

    assert posted["url"] == "https://api.example.com/v1/scans"


def test_sync_scan_summary_http_error():
    def _raise(req, timeout):
        raise urllib.error.HTTPError(url="", code=401, msg="Unauthorized", hdrs=None, fp=None)

    with patch("urllib.request.urlopen", side_effect=_raise):
        result = sync_scan_summary({"finding_count": 1}, url="https://api.example.com")

    assert "error" in result
    assert "401" in result["error"]


def test_sync_ticket_event_no_endpoint(monkeypatch):
    monkeypatch.delenv("ERREX_SYNC_URL", raising=False)
    monkeypatch.delenv("ERREX_SYNC_KEY", raising=False)
    result = sync_ticket_event(_make_ticket())
    assert "error" in result


def test_sync_ticket_event_opened():
    posted = {}

    def fake_urlopen(req, timeout):
        posted["url"] = req.full_url
        posted["data"] = json.loads(req.data)
        return FakeResp()

    ticket = _make_ticket()
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = sync_ticket_event(ticket, "opened", url="https://api.example.com", key="k")

    assert result.get("ok") is True
    assert posted["url"] == "https://api.example.com/v1/tickets"
    assert posted["data"]["event"] == "opened"
    assert posted["data"]["ticket"]["id"] == "abc12345"


def test_sync_ticket_event_closed():
    posted = {}

    def fake_urlopen(req, timeout):
        posted["data"] = json.loads(req.data)
        return FakeResp()

    ticket = _make_ticket(status="closed")
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        sync_ticket_event(ticket, "closed", url="https://api.example.com")

    assert posted["data"]["event"] == "closed"
    assert posted["data"]["ticket"]["status"] == "closed"


def test_sync_ticket_event_no_key_omits_auth_header():
    posted = {}

    def fake_urlopen(req, timeout):
        posted["headers"] = req.headers
        return FakeResp()

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        sync_ticket_event(_make_ticket(), "opened", url="https://api.example.com")

    assert "Authorization" not in posted["headers"]
