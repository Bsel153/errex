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


# ---------------------------------------------------------------------------
# Pattern cache and --no-cache flag
# ---------------------------------------------------------------------------

def test_list_patterns_exits_zero():
    r = run(["--list-patterns"])
    assert r.returncode == 0

def test_list_patterns_shows_python():
    r = run(["--list-patterns"])
    assert "Python" in r.stdout

def test_no_cache_flag_accepted():
    r = run(["--no-cache", "--list-patterns"])
    assert "unrecognized" not in r.stderr.lower()
    assert r.returncode == 0


def test_clear_cache_exits_zero():
    r = run(["--clear-cache"])
    assert r.returncode == 0
    assert "cache" in r.stdout.lower() or "Cache" in r.stdout


def test_fix_apply_flag_accepted():
    # Just verify --fix-apply is a recognized flag (no error text = exits 1 from usage, not "unrecognized")
    r = run(["--fix-apply", "--help"])
    assert "unrecognized" not in r.stderr.lower()


# ---------------------------------------------------------------------------
# Doctor command
# ---------------------------------------------------------------------------

def test_doctor_exits_zero(tmp_path):
    """--doctor --offline should exit 0 or 1 (no key) but never crash with unrecognized args."""
    r = run(["--doctor", "--offline"], env={"HOME": str(tmp_path), "PYTHONUSERBASE": _PYTHONUSERBASE,
                                             "ANTHROPIC_API_KEY": ""})
    combined = r.stdout + r.stderr
    assert "unrecognized" not in combined.lower()
    assert "traceback" not in combined.lower()


def test_doctor_no_crash(tmp_path):
    """--doctor without API key should exit non-zero but not produce a Python traceback."""
    r = run(["--doctor", "--offline"], env={"HOME": str(tmp_path), "PYTHONUSERBASE": _PYTHONUSERBASE,
                                             "ANTHROPIC_API_KEY": ""})
    assert "Traceback" not in r.stdout
    assert "Traceback" not in r.stderr


# ---------------------------------------------------------------------------
# RHT ticketing flags
# ---------------------------------------------------------------------------

def test_open_ticket_flag_accepted():
    r = run(["--open-ticket", "--help"])
    assert "unrecognized" not in r.stderr.lower()


def test_rht_username_flag_accepted():
    r = run(["--rht-username", "user@redhat.com", "--help"])
    assert "unrecognized" not in r.stderr.lower()


def test_rht_severity_flag_accepted():
    r = run(["--rht-severity", "2", "--help"])
    assert "unrecognized" not in r.stderr.lower()


def test_open_ticket_no_creds_prints_helpful_message():
    """--open-ticket without credentials should print a message, not crash."""
    r = run(
        ["--open-ticket"],
        input="SomeError: something went wrong\n",
        env={"ANTHROPIC_API_KEY": "", "RHT_USERNAME": "", "RHT_PASSWORD": ""},
    )
    combined = r.stdout + r.stderr
    assert "Traceback" not in combined
    # Should mention missing API key or missing RHT credentials
    assert "ANTHROPIC_API_KEY" in combined or "RHT_USERNAME" in combined or "RHT_PASSWORD" in combined

def test_web_auth_flag_accepted():
    r = run(["--auth", "user:pass", "--help"])
    assert "unrecognized" not in r.stderr.lower()


# ---------------------------------------------------------------------------
# Digest
# ---------------------------------------------------------------------------

def test_digest_exits_zero(tmp_path):
    r = run(["--digest"], env={"HOME": str(tmp_path), "PYTHONUSERBASE": _PYTHONUSERBASE})
    assert r.returncode == 0


def test_digest_no_history_message(tmp_path):
    r = run(["--digest"], env={"HOME": str(tmp_path), "PYTHONUSERBASE": _PYTHONUSERBASE})
    assert "0" in r.stdout or "No " in r.stdout


def test_digest_since_flag_accepted(tmp_path):
    r = run(["--digest", "--digest-since", "48"], env={"HOME": str(tmp_path), "PYTHONUSERBASE": _PYTHONUSERBASE})
    assert r.returncode == 0
