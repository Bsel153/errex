"""Tests for PagerDuty integration module."""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from errex.pagerduty import create_incident, get_routing_key, _SEV_MAP, _FIRE_SEVERITIES


def _fake_ticket(severity="critical", title="Firewall disabled"):
    t = MagicMock()
    t.severity = severity
    t.title = title
    t.id = "T-999"
    t.detail = "ufw is not active"
    t.source = "scan"
    return t


def test_fire_severities_are_critical_and_high():
    assert "critical" in _FIRE_SEVERITIES
    assert "high" in _FIRE_SEVERITIES
    assert "medium" not in _FIRE_SEVERITIES
    assert "low" not in _FIRE_SEVERITIES


def test_severity_map_critical():
    assert _SEV_MAP["critical"] == "critical"


def test_severity_map_high():
    assert _SEV_MAP["high"] == "error"


def test_severity_map_medium():
    assert _SEV_MAP["medium"] == "warning"


def test_severity_map_low():
    assert _SEV_MAP["low"] == "info"


def test_skips_medium_severity():
    result = create_incident(_fake_ticket(severity="medium"), routing_key="rk")
    assert result.get("skipped") is True


def test_skips_low_severity():
    result = create_incident(_fake_ticket(severity="low"), routing_key="rk")
    assert result.get("skipped") is True


def test_skips_info_severity():
    result = create_incident(_fake_ticket(severity="info"), routing_key="rk")
    assert result.get("skipped") is True


def test_create_incident_critical_success():
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps({"status": "success", "dedup_key": "T-999"}).encode()
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    with patch("errex.pagerduty.urllib.request.urlopen", return_value=fake_resp):
        result = create_incident(_fake_ticket(severity="critical"), routing_key="rk")

    assert result.get("ok") is True


def test_create_incident_high_success():
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps({"status": "success", "dedup_key": "T-999"}).encode()
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    with patch("errex.pagerduty.urllib.request.urlopen", return_value=fake_resp):
        result = create_incident(_fake_ticket(severity="high"), routing_key="rk")

    assert result.get("ok") is True


def test_create_incident_sends_correct_payload():
    posted = {}
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps({"status": "success", "dedup_key": "x"}).encode()
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    def fake_open(req, timeout):
        posted["body"] = json.loads(req.data)
        return fake_resp

    with patch("errex.pagerduty.urllib.request.urlopen", side_effect=fake_open):
        create_incident(_fake_ticket(severity="critical"), routing_key="mykey")

    body = posted["body"]
    assert body["routing_key"] == "mykey"
    assert body["event_action"] == "trigger"
    assert body["dedup_key"] == "T-999"
    assert body["payload"]["severity"] == "critical"
    assert body["payload"]["source"] == "errex"


def test_create_incident_http_error():
    from urllib.error import HTTPError
    with patch("errex.pagerduty.urllib.request.urlopen",
               side_effect=HTTPError("url", 400, "Bad Request", {}, None)):
        result = create_incident(_fake_ticket(severity="critical"), routing_key="rk")
    assert "error" in result
    assert "400" in result["error"]


def test_get_routing_key_from_env(monkeypatch):
    monkeypatch.setenv("PAGERDUTY_ROUTING_KEY", "abc123")
    assert get_routing_key() == "abc123"


def test_get_routing_key_explicit():
    assert get_routing_key("explicit-key") == "explicit-key"


def test_get_routing_key_none(monkeypatch):
    monkeypatch.delenv("PAGERDUTY_ROUTING_KEY", raising=False)
    assert get_routing_key() is None
