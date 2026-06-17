import json
import pytest
from pathlib import Path
from errex.auto_scan import _load_last_findings, _save_findings


def test_load_last_findings_missing_file(tmp_path):
    assert _load_last_findings(tmp_path / "nope.json") == set()


def test_save_and_load_findings(tmp_path):
    state = tmp_path / "state.json"
    _save_findings(state, {"f1", "f2", "f3"})
    loaded = _load_last_findings(state)
    assert loaded == {"f1", "f2", "f3"}


def test_save_findings_has_timestamp(tmp_path):
    state = tmp_path / "state.json"
    _save_findings(state, {"f1"})
    data = json.loads(state.read_text())
    assert "timestamp" in data
    assert data["timestamp"].endswith("Z")


def test_load_findings_bad_json(tmp_path):
    state = tmp_path / "state.json"
    state.write_text("not json")
    assert _load_last_findings(state) == set()


def test_save_findings_sorted(tmp_path):
    state = tmp_path / "state.json"
    _save_findings(state, {"c", "a", "b"})
    data = json.loads(state.read_text())
    assert data["finding_ids"] == ["a", "b", "c"]


def test_load_empty_set(tmp_path):
    state = tmp_path / "state.json"
    _save_findings(state, set())
    assert _load_last_findings(state) == set()
