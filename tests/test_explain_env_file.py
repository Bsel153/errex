"""Unit tests for explain_env_file in errex/explainers.py — no API calls."""
from __future__ import annotations

import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Happy path: known and custom vars
# ---------------------------------------------------------------------------

def test_known_variable_shows_description(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("PATH=/usr/bin:/bin\n")
    from errex.explainers import explain_env_file
    explain_env_file(str(env))
    captured = capsys.readouterr()
    assert "PATH" in captured.out
    # Known key should show a description, not just "(custom)"
    assert "custom" not in captured.out.lower() or "PATH" in captured.out


def test_custom_variable_shows_unknown(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("MY_CUSTOM_VAR=hello\n")
    from errex.explainers import explain_env_file
    explain_env_file(str(env))
    captured = capsys.readouterr()
    assert "MY_CUSTOM_VAR" in captured.out
    assert "custom" in captured.out.lower() or "unknown" in captured.out.lower()


def test_secret_value_is_masked(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("API_KEY=supersecretvalue123\n")
    from errex.explainers import explain_env_file
    explain_env_file(str(env))
    captured = capsys.readouterr()
    assert "API_KEY" in captured.out
    # Full value must NOT appear in output
    assert "supersecretvalue123" not in captured.out
    assert "***" in captured.out


def test_password_value_is_masked(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("DB_PASSWORD=s3cr3tp@ss\n")
    from errex.explainers import explain_env_file
    explain_env_file(str(env))
    captured = capsys.readouterr()
    assert "DB_PASSWORD" in captured.out
    assert "s3cr3tp@ss" not in captured.out


def test_non_secret_value_shown(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("PORT=8080\n")
    from errex.explainers import explain_env_file
    explain_env_file(str(env))
    captured = capsys.readouterr()
    assert "PORT" in captured.out
    assert "8080" in captured.out


def test_comments_and_blank_lines_ignored(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text(
        "# This is a comment\n"
        "\n"
        "PORT=3000\n"
        "# Another comment\n"
        "DEBUG=true\n"
    )
    from errex.explainers import explain_env_file
    explain_env_file(str(env))
    captured = capsys.readouterr()
    assert "PORT" in captured.out
    assert "DEBUG" in captured.out
    # Comment text should NOT appear as a key
    assert "This is a comment" not in captured.out


def test_multiple_vars(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text(
        "HOME=/root\n"
        "SHELL=/bin/bash\n"
        "SECRET_KEY=abc123secret\n"
        "MY_APP=myvalue\n"
    )
    from errex.explainers import explain_env_file
    explain_env_file(str(env))
    captured = capsys.readouterr()
    assert "HOME" in captured.out
    assert "SHELL" in captured.out
    assert "SECRET_KEY" in captured.out
    assert "MY_APP" in captured.out
    # Count variable mentions: at least 4
    assert captured.out.count("\n") > 4


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_missing_file_exits_1(capsys):
    from errex.explainers import explain_env_file
    with pytest.raises(SystemExit) as exc:
        explain_env_file("/does/not/exist/.env")
    assert exc.value.code == 1


def test_empty_file(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("")
    from errex.explainers import explain_env_file
    explain_env_file(str(env))
    captured = capsys.readouterr()
    assert "No KEY=VALUE pairs found" in captured.out


def test_only_comments(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("# just a comment\n# another comment\n")
    from errex.explainers import explain_env_file
    explain_env_file(str(env))
    captured = capsys.readouterr()
    assert "No KEY=VALUE pairs found" in captured.out


# ---------------------------------------------------------------------------
# Value masking edge cases
# ---------------------------------------------------------------------------

def test_sk_ant_prefix_masked(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("ANTHROPIC_KEY=sk-ant-api123456789\n")
    from errex.explainers import explain_env_file
    explain_env_file(str(env))
    captured = capsys.readouterr()
    assert "sk-ant-api123456789" not in captured.out


def test_value_with_equals_sign(tmp_path, capsys):
    """Values containing '=' should be handled (only split on first '=')."""
    env = tmp_path / ".env"
    env.write_text("DATABASE_URL=postgres://user:pass@host/db?key=val\n")
    from errex.explainers import explain_env_file
    explain_env_file(str(env))
    captured = capsys.readouterr()
    assert "DATABASE_URL" in captured.out
