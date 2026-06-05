"""Tests for local ticket store."""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import errex.tickets as T


def _patch_file(tmp_path, monkeypatch):
    tf = tmp_path / "tickets.jsonl"
    monkeypatch.setattr(T, "_TICKETS_FILE", tf)
    return tf


def test_create_ticket(tmp_path, monkeypatch):
    _patch_file(tmp_path, monkeypatch)
    t = T.create_ticket("Bad SSH config", "high", detail="PermitRootLogin yes", source="scan")
    assert len(t.id) == 8
    assert t.title == "Bad SSH config"
    assert t.severity == "high"
    assert t.status == "open"
    assert t.source == "scan"


def test_create_persists_to_file(tmp_path, monkeypatch):
    tf = _patch_file(tmp_path, monkeypatch)
    T.create_ticket("Test", "medium")
    lines = tf.read_text().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["title"] == "Test"


def test_load_all(tmp_path, monkeypatch):
    _patch_file(tmp_path, monkeypatch)
    T.create_ticket("A", "high")
    T.create_ticket("B", "low")
    tickets = T.load_all()
    assert len(tickets) == 2
    assert {t.title for t in tickets} == {"A", "B"}


def test_load_all_empty(tmp_path, monkeypatch):
    _patch_file(tmp_path, monkeypatch)
    assert T.load_all() == []


def test_close_ticket(tmp_path, monkeypatch):
    _patch_file(tmp_path, monkeypatch)
    t = T.create_ticket("Firewall off", "critical")
    closed = T.close_ticket(t.id)
    assert closed is not None
    assert closed.status == "closed"
    assert T.load_all()[0].status == "closed"


def test_close_ticket_not_found(tmp_path, monkeypatch):
    _patch_file(tmp_path, monkeypatch)
    result = T.close_ticket("nonexist")
    assert result is None


def test_snooze_ticket(tmp_path, monkeypatch):
    _patch_file(tmp_path, monkeypatch)
    t = T.create_ticket("Snoozable", "low")
    snoozed = T.snooze_ticket(t.id, days=3)
    assert snoozed is not None
    assert snoozed.status == "snoozed"
    assert snoozed.is_snoozed()


def test_snooze_expiry(tmp_path, monkeypatch):
    _patch_file(tmp_path, monkeypatch)
    t = T.create_ticket("Old snooze", "low")
    # Snooze with past time
    past = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).isoformat() + "Z"
    T.update_ticket(t.id, status="snoozed", snooze_until=past)
    loaded = T.load_all()[0]
    assert loaded.effective_status() == "open"


def test_reopen_ticket(tmp_path, monkeypatch):
    _patch_file(tmp_path, monkeypatch)
    t = T.create_ticket("Closed", "medium")
    T.close_ticket(t.id)
    reopened = T.reopen_ticket(t.id)
    assert reopened.status == "open"


def test_get_open_tickets(tmp_path, monkeypatch):
    _patch_file(tmp_path, monkeypatch)
    t1 = T.create_ticket("Open", "high")
    t2 = T.create_ticket("Closed", "medium")
    T.close_ticket(t2.id)
    open_tickets = T.get_open_tickets()
    assert len(open_tickets) == 1
    assert open_tickets[0].title == "Open"


def test_find_by_finding_id(tmp_path, monkeypatch):
    _patch_file(tmp_path, monkeypatch)
    T.create_ticket("Match", "high", finding_id="abc-123")
    T.create_ticket("Other", "low", finding_id="xyz-999")
    found = T.find_by_finding_id("abc-123")
    assert found is not None
    assert found.title == "Match"


def test_find_by_finding_id_not_found(tmp_path, monkeypatch):
    _patch_file(tmp_path, monkeypatch)
    assert T.find_by_finding_id("nope") is None


def test_update_ticket_sets_updated_at(tmp_path, monkeypatch):
    _patch_file(tmp_path, monkeypatch)
    t = T.create_ticket("Timed", "info")
    old_ts = t.updated_at
    T.update_ticket(t.id, status="closed")
    loaded = T.load_all()[0]
    assert loaded.updated_at >= old_ts


def test_partial_id_match(tmp_path, monkeypatch):
    _patch_file(tmp_path, monkeypatch)
    t = T.create_ticket("Partial", "medium")
    prefix = t.id[:4]
    closed = T.close_ticket(prefix)
    assert closed is not None
    assert closed.status == "closed"


def test_to_dict_roundtrip(tmp_path, monkeypatch):
    _patch_file(tmp_path, monkeypatch)
    t = T.create_ticket("Round", "high", detail="details", finding_id="f1")
    d = t.to_dict()
    assert d["title"] == "Round"
    assert d["severity"] == "high"
    assert d["finding_id"] == "f1"
