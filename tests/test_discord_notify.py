"""Tests for Discord webhook notifications."""
from __future__ import annotations

import json
from unittest.mock import patch
import urllib.error

import pytest

from errex.discord_notify import (
    notify_new_ticket,
    notify_ticket_closed,
    notify_scan_summary,
    _get_webhook,
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
    }
    defaults.update(kwargs)
    return Ticket(defaults)


def test_get_webhook_from_env(monkeypatch):
    monkeypatch.setenv("ERREX_DISCORD_WEBHOOK", "https://discord.com/api/webhooks/test")
    assert _get_webhook() == "https://discord.com/api/webhooks/test"


def test_get_webhook_explicit():
    assert _get_webhook("https://example.com/wh") == "https://example.com/wh"


def test_get_webhook_none(monkeypatch):
    monkeypatch.delenv("ERREX_DISCORD_WEBHOOK", raising=False)
    assert _get_webhook() is None


def test_notify_new_ticket_no_webhook(monkeypatch):
    monkeypatch.delenv("ERREX_DISCORD_WEBHOOK", raising=False)
    ticket = _make_ticket()
    result = notify_new_ticket(ticket, webhook_url=None)
    assert "error" in result


def test_notify_new_ticket_success(monkeypatch):
    ticket = _make_ticket()
    posted = {}

    class FakeResp:
        status = 204
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_urlopen(req, timeout):
        posted["data"] = json.loads(req.data)
        return FakeResp()

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = notify_new_ticket(ticket, webhook_url="https://discord.com/test")

    assert result.get("ok") is True
    embeds = posted["data"]["embeds"]
    assert len(embeds) == 1
    assert "Firewall disabled" in embeds[0]["title"]
    assert embeds[0]["color"] == 0xC00000  # critical color


def test_notify_new_ticket_with_github_url(monkeypatch):
    ticket = _make_ticket()
    posted = {}

    class FakeResp:
        status = 204
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_urlopen(req, timeout):
        posted["data"] = json.loads(req.data)
        return FakeResp()

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        notify_new_ticket(ticket, webhook_url="https://discord.com/test",
                          github_issue_url="https://github.com/org/repo/issues/7")

    fields = posted["data"]["embeds"][0]["fields"]
    field_names = [f["name"] for f in fields]
    assert "GitHub Issue" in field_names


def test_notify_new_ticket_http_error():
    ticket = _make_ticket()

    def _raise(req, timeout):
        raise urllib.error.HTTPError(url="", code=400, msg="Bad Request", hdrs=None, fp=None)

    with patch("urllib.request.urlopen", side_effect=_raise):
        result = notify_new_ticket(ticket, webhook_url="https://discord.com/test")

    assert "error" in result
    assert "400" in result["error"]


def test_notify_ticket_closed_success():
    ticket = _make_ticket(status="closed")
    posted = {}

    class FakeResp:
        status = 204
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_urlopen(req, timeout):
        posted["data"] = json.loads(req.data)
        return FakeResp()

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = notify_ticket_closed(ticket, webhook_url="https://discord.com/test")

    assert result.get("ok") is True
    assert "Resolved" in posted["data"]["embeds"][0]["title"]
    assert posted["data"]["embeds"][0]["color"] == 0x3D9970  # green


def test_notify_scan_summary_all_clear():
    posted = {}

    class FakeResp:
        status = 204
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_urlopen(req, timeout):
        posted["data"] = json.loads(req.data)
        return FakeResp()

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        notify_scan_summary(0, 0, 0, webhook_url="https://discord.com/test")

    assert "All Clear" in posted["data"]["embeds"][0]["title"]
    assert posted["data"]["embeds"][0]["color"] == 0x3D9970


def test_notify_scan_summary_critical():
    posted = {}

    class FakeResp:
        status = 204
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_urlopen(req, timeout):
        posted["data"] = json.loads(req.data)
        return FakeResp()

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        notify_scan_summary(3, 2, 1, webhook_url="https://discord.com/test")

    title = posted["data"]["embeds"][0]["title"]
    assert "Critical" in title
    assert posted["data"]["embeds"][0]["color"] == 0xC00000


def test_notify_scan_summary_no_webhook(monkeypatch):
    monkeypatch.delenv("ERREX_DISCORD_WEBHOOK", raising=False)
    result = notify_scan_summary(1, 0, 1, webhook_url=None)
    assert "error" in result


def test_detail_truncated_at_300():
    ticket = _make_ticket(detail="x" * 500)
    posted = {}

    class FakeResp:
        status = 204
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_urlopen(req, timeout):
        posted["data"] = json.loads(req.data)
        return FakeResp()

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        notify_new_ticket(ticket, webhook_url="https://discord.com/test")

    desc = posted["data"]["embeds"][0]["description"]
    assert len(desc) <= 304  # 300 chars + "…"
    assert desc.endswith("…")
