"""Tests for error clustering module."""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch

from errex.cluster import _fingerprint, cluster_errors


def test_fingerprint_strips_timestamp():
    line = "2024-01-15 10:30:00 ERROR something failed"
    fp = _fingerprint(line)
    assert "<TS>" in fp
    assert "2024-01-15" not in fp


def test_fingerprint_strips_hex():
    line = "crash at address 0xdeadbeef"
    fp = _fingerprint(line)
    assert "<HEX>" in fp
    assert "0xdeadbeef" not in fp


def test_fingerprint_strips_uuid():
    line = "request-id: 550e8400-e29b-41d4-a716-446655440000 failed"
    fp = _fingerprint(line)
    assert "<UUID>" in fp


def test_fingerprint_strips_ip():
    line = "Connection from 192.168.1.100 refused"
    fp = _fingerprint(line)
    assert "<IP>" in fp
    assert "192.168.1.100" not in fp


def test_fingerprint_strips_line_numbers():
    line = "error at file.py:42 in function"
    fp = _fingerprint(line)
    assert "<LINE>" in fp


def test_fingerprint_same_for_similar_lines():
    line1 = "2024-01-15 ERROR Connection from 192.168.1.1 refused"
    line2 = "2024-01-16 ERROR Connection from 10.0.0.5 refused"
    fp1 = _fingerprint(line1)
    fp2 = _fingerprint(line2)
    assert fp1 == fp2


def test_cluster_errors_file(tmp_path):
    log_file = tmp_path / "test.log"
    log_file.write_text(
        "2024-01-15 10:00:00 ERROR Connection refused\n"
        "2024-01-15 10:00:01 ERROR Connection refused\n"
        "2024-01-15 10:00:02 ERROR Out of memory\n"
        "2024-01-15 10:00:03 ERROR Connection refused\n"
    )
    # Should not raise
    cluster_errors(str(log_file))


def test_cluster_errors_missing_file():
    with pytest.raises(SystemExit):
        cluster_errors("/nonexistent/path/to/file.log")


def test_cluster_errors_empty_file(tmp_path):
    empty = tmp_path / "empty.log"
    empty.write_text("")
    # Should print "No lines" without raising
    cluster_errors(str(empty))


def test_cluster_errors_stdin(monkeypatch):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO(
        "2024-01-15 ERROR foo\n"
        "2024-01-16 ERROR foo\n"
    ))
    # Should not raise
    cluster_errors("-")
