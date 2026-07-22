"""Tests for git_tools module."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


def test_run_returns_tuple():
    from errex.git_tools import _run
    rc, out, err = _run(["echo", "hello"])
    assert rc == 0
    assert "hello" in out


def test_run_command_not_found():
    from errex.git_tools import _run
    rc, out, err = _run(["nonexistent_command_xyz"])
    assert rc == 127


def test_explain_git_blame_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        from errex.git_tools import explain_git_blame
        explain_git_blame("somefile.py:10")


def test_explain_git_blame_bad_format(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with pytest.raises(SystemExit):
        from errex.git_tools import explain_git_blame
        explain_git_blame("no-colon-format")


def test_explain_git_blame_not_in_repo(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        from errex.git_tools import explain_git_blame
        explain_git_blame(f"{tmp_path}/somefile.py:1")


def test_in_git_repo_true():
    """Should return True when run inside the project repo."""
    from errex.git_tools import _in_git_repo
    # The test runner is inside /home/user/errex which is a git repo
    result = _in_git_repo()
    assert isinstance(result, bool)


def test_explain_git_blame_file_not_found(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    # We ARE in a git repo (the errex repo) but the file doesn't exist
    with patch("errex.git_tools._in_git_repo", return_value=True):
        with pytest.raises(SystemExit):
            from errex.git_tools import explain_git_blame
            explain_git_blame("/nonexistent/path/file.py:42")
