"""Tests for the auto-backup-before-fix module."""
from __future__ import annotations

import json

import pytest

import errex.backup as B


def _patch_root(tmp_path, monkeypatch):
    root = tmp_path / "backups"
    monkeypatch.setattr(B, "_BACKUP_ROOT", root)
    monkeypatch.setattr(B, "_MANIFEST", root / "manifest.jsonl")
    return root


def test_backup_files_copies_existing_file(tmp_path, monkeypatch):
    _patch_root(tmp_path, monkeypatch)
    src = tmp_path / "config.txt"
    src.write_text("original content")

    records = B.backup_files([str(src)], reason="fix:test-id")

    assert len(records) == 1
    rec = records[0]
    assert rec["original"] == str(src)
    assert rec["reason"] == "fix:test-id"
    backup_path = __import__("pathlib").Path(rec["backup"])
    assert backup_path.exists()
    assert backup_path.read_text() == "original content"


def test_backup_files_skips_missing_files(tmp_path, monkeypatch):
    _patch_root(tmp_path, monkeypatch)
    records = B.backup_files([str(tmp_path / "nope.txt")])
    assert records == []


def test_backup_files_skips_directories(tmp_path, monkeypatch):
    _patch_root(tmp_path, monkeypatch)
    d = tmp_path / "somedir"
    d.mkdir()
    records = B.backup_files([str(d)])
    assert records == []


def test_backup_files_handles_name_collisions(tmp_path, monkeypatch):
    _patch_root(tmp_path, monkeypatch)
    a = tmp_path / "a" / "config.txt"
    b = tmp_path / "b" / "config.txt"
    a.parent.mkdir()
    b.parent.mkdir()
    a.write_text("from a")
    b.write_text("from b")

    monkeypatch.setattr(B, "_now_stamp", lambda: "20260101T000000")
    records = B.backup_files([str(a), str(b)])

    assert len(records) == 2
    assert records[0]["backup"] != records[1]["backup"]
    from pathlib import Path
    assert Path(records[0]["backup"]).read_text() == "from a"
    assert Path(records[1]["backup"]).read_text() == "from b"


def test_backup_files_writes_manifest(tmp_path, monkeypatch):
    root = _patch_root(tmp_path, monkeypatch)
    src = tmp_path / "f.txt"
    src.write_text("x")
    B.backup_files([str(src)])

    manifest = root / "manifest.jsonl"
    lines = manifest.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["original"] == str(src)


def test_list_backups_empty(tmp_path, monkeypatch):
    _patch_root(tmp_path, monkeypatch)
    assert B.list_backups() == []


def test_list_backups_newest_first(tmp_path, monkeypatch):
    _patch_root(tmp_path, monkeypatch)
    f1 = tmp_path / "one.txt"
    f2 = tmp_path / "two.txt"
    f1.write_text("1")
    f2.write_text("2")
    B.backup_files([str(f1)])
    B.backup_files([str(f2)])

    backups = B.list_backups()
    assert len(backups) == 2
    assert backups[0]["original"] == str(f2)
    assert backups[1]["original"] == str(f1)


def test_list_backups_respects_limit(tmp_path, monkeypatch):
    _patch_root(tmp_path, monkeypatch)
    for i in range(5):
        f = tmp_path / f"f{i}.txt"
        f.write_text(str(i))
        B.backup_files([str(f)])
    assert len(B.list_backups(limit=2)) == 2


def test_restore_backup_success(tmp_path, monkeypatch):
    _patch_root(tmp_path, monkeypatch)
    src = tmp_path / "config.txt"
    src.write_text("original")
    [rec] = B.backup_files([str(src)])

    src.write_text("modified by a fix")
    resp = B.restore_backup(rec["backup"])

    assert resp.get("ok") is True
    assert resp["restored_to"] == str(src)
    assert src.read_text() == "original"


def test_restore_backup_unknown_path(tmp_path, monkeypatch):
    _patch_root(tmp_path, monkeypatch)
    resp = B.restore_backup("/no/such/backup.txt")
    assert "error" in resp


def test_restore_backup_missing_backup_file(tmp_path, monkeypatch):
    _patch_root(tmp_path, monkeypatch)
    src = tmp_path / "config.txt"
    src.write_text("original")
    [rec] = B.backup_files([str(src)])

    import os
    os.remove(rec["backup"])
    resp = B.restore_backup(rec["backup"])
    assert "error" in resp
