"""
Integration tests — invoke `python -m errex` as a real subprocess.
No ANTHROPIC_API_KEY required; all tested subcommands use local lookup tables.
"""
import os
import subprocess
import sys
from pathlib import Path

# Preserve the real user-packages base so HOME overrides don't break imports.
_REAL_HOME = str(Path.home())
_PYTHONUSERBASE = str(Path.home() / ".local")


def run(args, input=None, env=None):
    merged = {**os.environ, **(env or {})}
    return subprocess.run(
        [sys.executable, "-m", "errex"] + args,
        input=input,
        capture_output=True,
        text=True,
        env=merged,
    )


# ---------------------------------------------------------------------------
# Meta flags
# ---------------------------------------------------------------------------

def test_version_exits_zero():
    r = run(["--version"])
    assert r.returncode == 0


def test_version_prints_semver():
    r = run(["--version"])
    # e.g. "errex 0.19.0" or "errex dev"
    assert "errex" in r.stdout or "errex" in r.stderr or "." in r.stdout


def test_help_exits_zero():
    r = run(["--help"])
    assert r.returncode == 0


def test_help_mentions_key_flags():
    r = run(["--help"])
    output = r.stdout + r.stderr
    for flag in ("--version", "--model", "--history", "--explain-exit"):
        assert flag in output, f"expected {flag!r} in --help output"


# ---------------------------------------------------------------------------
# Shell completion
# ---------------------------------------------------------------------------

def test_completion_bash_exits_zero():
    r = run(["--completion", "bash"])
    assert r.returncode == 0


def test_completion_bash_looks_like_shell_script():
    r = run(["--completion", "bash"])
    assert "_errex" in r.stdout


def test_completion_zsh_exits_zero():
    r = run(["--completion", "zsh"])
    assert r.returncode == 0


def test_completion_zsh_looks_like_shell_script():
    r = run(["--completion", "zsh"])
    assert "_errex" in r.stdout


# ---------------------------------------------------------------------------
# Local exit-code lookups (no API)
# ---------------------------------------------------------------------------

def test_explain_exit_0():
    r = run(["--explain-exit", "0"])
    assert r.returncode == 0
    assert "Success" in r.stdout


def test_explain_exit_137():
    r = run(["--explain-exit", "137"])
    assert r.returncode == 0
    assert "SIGKILL" in r.stdout


def test_explain_exit_1():
    r = run(["--explain-exit", "1"])
    assert r.returncode == 0
    # Generic non-zero; just ensure it doesn't crash
    assert "1" in r.stdout


# ---------------------------------------------------------------------------
# Local HTTP-status lookups (no API)
# ---------------------------------------------------------------------------

def test_explain_http_404():
    r = run(["--explain-http", "404"])
    assert r.returncode == 0
    assert "Not Found" in r.stdout


def test_explain_http_429():
    r = run(["--explain-http", "429"])
    assert r.returncode == 0
    assert "Rate" in r.stdout


def test_explain_http_200():
    r = run(["--explain-http", "200"])
    assert r.returncode == 0


# ---------------------------------------------------------------------------
# Local cron explainer (no API)
# ---------------------------------------------------------------------------

def test_explain_cron_every_minute():
    r = run(["--explain-cron", "* * * * *"])
    assert r.returncode == 0
    assert "minute" in r.stdout.lower()


def test_explain_cron_midnight_daily():
    r = run(["--explain-cron", "0 0 * * *"])
    assert r.returncode == 0
    assert r.stdout.strip() != ""


# ---------------------------------------------------------------------------
# Local env-var explainer (no API)
# ---------------------------------------------------------------------------

def test_explain_env_path():
    r = run(["--explain-env", "PATH"])
    assert r.returncode == 0
    assert "PATH" in r.stdout


# ---------------------------------------------------------------------------
# History / stats with empty history
# ---------------------------------------------------------------------------

def test_stats_no_history(tmp_path):
    r = run(["--stats"], env={"HOME": str(tmp_path), "PYTHONUSERBASE": _PYTHONUSERBASE})
    assert r.returncode == 0
    assert "No history" in r.stdout


def test_history_no_history(tmp_path):
    r = run(["--history"], env={"HOME": str(tmp_path), "PYTHONUSERBASE": _PYTHONUSERBASE})
    assert r.returncode == 0
    assert "No history" in r.stdout


# ---------------------------------------------------------------------------
# Config / profiles with no config file
# ---------------------------------------------------------------------------

def test_list_profiles_no_config(tmp_path):
    r = run(["--list-profiles"], env={"HOME": str(tmp_path), "PYTHONUSERBASE": _PYTHONUSERBASE})
    assert r.returncode == 0
    # Should not crash; any sensible message is acceptable


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_nonexistent_file_exits_nonzero():
    r = run(["nonexistent_file_abc123.txt"])
    assert r.returncode != 0


def test_nonexistent_file_prints_error():
    r = run(["nonexistent_file_abc123.txt"])
    output = r.stdout + r.stderr
    assert "not found" in output.lower() or "no such file" in output.lower()


def test_no_api_key_exits_nonzero():
    """Piping error text without an API key should exit non-zero cleanly."""
    r = run([], input="SomeError: something went wrong\n", env={"ANTHROPIC_API_KEY": ""})
    assert r.returncode != 0


def test_no_api_key_prints_helpful_message():
    r = run([], input="SomeError: something went wrong\n", env={"ANTHROPIC_API_KEY": ""})
    output = r.stdout + r.stderr
    assert "ANTHROPIC_API_KEY" in output
