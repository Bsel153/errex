import csv
import json
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from io import StringIO

import errex as ex


# ---------------------------------------------------------------------------
# get_error_input
# ---------------------------------------------------------------------------

def test_get_error_input_reads_file(tmp_path):
    f = tmp_path / "error.txt"
    f.write_text("TypeError: something went wrong")
    assert ex.get_error_input([str(f)]) == "TypeError: something went wrong"


def test_get_error_input_strips_whitespace(tmp_path):
    f = tmp_path / "error.txt"
    f.write_text("  some error\n\n")
    assert ex.get_error_input([str(f)]) == "some error"


def test_get_error_input_missing_file_exits(tmp_path):
    with pytest.raises(SystemExit) as exc:
        ex.get_error_input([str(tmp_path / "nope.txt")])
    assert exc.value.code == 1


def test_get_error_input_reads_stdin():
    with patch("sys.stdin", StringIO("error from stdin")):
        with patch("sys.stdin.isatty", return_value=False):
            result = ex.get_error_input([])
    assert result == "error from stdin"


# ---------------------------------------------------------------------------
# save_history
# ---------------------------------------------------------------------------

def test_save_history_writes_json_line(tmp_path):
    history_file = tmp_path / "history"
    with patch.object(ex, "HISTORY_FILE", history_file):
        ex.save_history("some error", "some explanation", "claude-sonnet-4-6", False)

    entry = json.loads(history_file.read_text().strip())
    assert entry["error"] == "some error"
    assert entry["explanation"] == "some explanation"
    assert entry["model"] == "claude-sonnet-4-6"
    assert entry["brief"] is False
    assert "timestamp" in entry


def test_save_history_appends(tmp_path):
    history_file = tmp_path / "history"
    with patch.object(ex, "HISTORY_FILE", history_file):
        ex.save_history("error 1", "explanation 1", "claude-sonnet-4-6", False)
        ex.save_history("error 2", "explanation 2", "claude-sonnet-4-6", True)

    lines = history_file.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["error"] == "error 2"


def test_save_history_truncates_long_errors(tmp_path):
    history_file = tmp_path / "history"
    with patch.object(ex, "HISTORY_FILE", history_file):
        ex.save_history("x" * 500, "explanation", "claude-sonnet-4-6", False)

    entry = json.loads(history_file.read_text().strip())
    assert len(entry["error"]) == 200


def test_save_history_with_name(tmp_path):
    history_file = tmp_path / "history"
    with patch.object(ex, "HISTORY_FILE", history_file):
        ex.save_history("err", "expl", "claude-sonnet-4-6", False, name="myerror")

    entry = json.loads(history_file.read_text().strip())
    assert entry["name"] == "myerror"


# ---------------------------------------------------------------------------
# explain_error: API key checks
# ---------------------------------------------------------------------------

def test_explain_error_exits_without_api_key():
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(SystemExit) as exc:
            ex.explain_error("some error", model="claude-sonnet-4-6")
    assert exc.value.code == 1


def test_explain_error_streams_output(tmp_path, capsys):
    history_file = tmp_path / "history"
    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.text_stream = iter(["This ", "is ", "an ", "error."])
    mock_client = MagicMock()
    mock_client.messages.stream.return_value = mock_stream

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("anthropic.Anthropic", return_value=mock_client):
            with patch.object(ex, "HISTORY_FILE", history_file):
                ex.explain_error("some error", model="claude-sonnet-4-6")

    assert "This is an error." in capsys.readouterr().out


def test_explain_error_brief_uses_short_prompt(tmp_path):
    history_file = tmp_path / "history"
    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.text_stream = iter(["Short answer."])
    mock_client = MagicMock()
    mock_client.messages.stream.return_value = mock_stream

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("anthropic.Anthropic", return_value=mock_client):
            with patch.object(ex, "HISTORY_FILE", history_file):
                ex.explain_error("some error", model="claude-sonnet-4-6", brief=True)

    call_kwargs = mock_client.messages.stream.call_args.kwargs
    assert call_kwargs["max_tokens"] == 256
    assert "one short paragraph" in call_kwargs["messages"][0]["content"]


# ---------------------------------------------------------------------------
# redact_secrets
# ---------------------------------------------------------------------------

def test_redact_anthropic_key():
    text = "key=sk-ant-api03-abc123XYZ-more_chars"
    result, count = ex.redact_secrets(text)
    assert "sk-ant" not in result
    assert "[ANTHROPIC_KEY]" in result
    assert count >= 1


def test_redact_github_token():
    # token pattern fires first when prefixed by "token:", still correctly redacted
    text = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
    result, count = ex.redact_secrets(text)
    assert "ghp_" not in result
    assert "[GITHUB_TOKEN]" in result
    assert count >= 1


def test_redact_aws_key():
    text = "AKIAIOSFODNN7EXAMPLE is your access key"
    result, count = ex.redact_secrets(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in result
    assert "[AWS_KEY]" in result


def test_redact_jwt():
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    result, count = ex.redact_secrets(jwt)
    assert "eyJ" not in result
    assert "[JWT_TOKEN]" in result


def test_redact_bearer_token():
    text = "Authorization: Bearer abc123token.very.long.value"
    result, count = ex.redact_secrets(text)
    assert "abc123token" not in result
    assert "[REDACTED]" in result


def test_redact_password_field():
    text = "password=supersecret123"
    result, count = ex.redact_secrets(text)
    assert "supersecret123" not in result
    assert "[REDACTED]" in result


def test_redact_no_secrets_returns_unchanged():
    text = "TypeError: 'NoneType' object has no attribute 'split'"
    result, count = ex.redact_secrets(text)
    assert result == text
    assert count == 0


# ---------------------------------------------------------------------------
# _detect_yaml_type
# ---------------------------------------------------------------------------

def test_detect_docker_compose():
    content = "services:\n  web:\n    image: nginx:latest\n    ports:\n      - '80:80'\n"
    assert ex._detect_yaml_type(content) == "Docker Compose"


def test_detect_kubernetes():
    content = "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: my-app\n"
    assert ex._detect_yaml_type(content) == "Kubernetes"


def test_detect_github_actions():
    content = "on:\n  push:\n    branches: [main]\njobs:\n  build:\n    runs-on: ubuntu-latest\n"
    assert ex._detect_yaml_type(content) == "GitHub Actions"


def test_detect_generic_yaml():
    content = "name: my-project\nversion: 1.0\nsettings:\n  debug: true\n"
    assert ex._detect_yaml_type(content) == "YAML config"


# ---------------------------------------------------------------------------
# _cron_local
# ---------------------------------------------------------------------------

def test_cron_every_minute():
    assert ex._cron_local("* * * * *") == "Every minute."


def test_cron_every_5_minutes():
    assert ex._cron_local("*/5 * * * *") == "Every 5 minutes."


def test_cron_every_hour():
    assert ex._cron_local("0 * * * *") == "Every hour."


def test_cron_every_hour_at_30():
    assert ex._cron_local("30 * * * *") == "Every hour at :30."


def test_cron_daily():
    result = ex._cron_local("0 9 * * *")
    assert result == "Every day at 9:00 AM."


def test_cron_weekly():
    result = ex._cron_local("0 8 * * 1")
    assert result == "Every Mon at 8:00 AM."


def test_cron_monthly():
    result = ex._cron_local("0 0 1 * *")
    assert result == "The 1st of every month at 12:00 AM."


def test_cron_yearly():
    result = ex._cron_local("0 0 1 1 *")
    assert result == "Once a year: Jan 1st at 12:00 AM."


def test_cron_complex_returns_none():
    assert ex._cron_local("0 9-17 * * 1-5") is None


def test_cron_wrong_field_count_returns_none():
    assert ex._cron_local("* * * *") is None


# ---------------------------------------------------------------------------
# extract_error_type
# ---------------------------------------------------------------------------

def test_extract_type_python():
    assert ex.extract_error_type("Traceback...\nTypeError: unsupported operand") == "TypeError"


def test_extract_type_http():
    assert ex.extract_error_type("HTTP 404 Not Found") == "HTTP 404"


def test_extract_type_go_panic():
    assert ex.extract_error_type("goroutine 1 [running]:\npanic: runtime error") == "panic"


def test_extract_type_unknown():
    assert ex.extract_error_type("something went wrong") == "unknown"


# ---------------------------------------------------------------------------
# _error_fingerprint
# ---------------------------------------------------------------------------

def test_fingerprint_strips_line_numbers():
    a = ex._error_fingerprint("Error at line 42 in foo.py")
    b = ex._error_fingerprint("Error at line 99 in foo.py")
    assert a == b


def test_fingerprint_strips_addresses():
    a = ex._error_fingerprint("object at 0x7f1a2b3c4d5e")
    b = ex._error_fingerprint("object at 0xDEADBEEF")
    assert a == b


# ---------------------------------------------------------------------------
# extract_snippet
# ---------------------------------------------------------------------------

def test_snippet_strips_stdlib_frames():
    tb = (
        'Traceback (most recent call last):\n'
        '  File "/usr/lib/python3.9/importlib/__init__.py", line 127, in import_module\n'
        '    return _bootstrap._gcd_import(name[:])\n'
        '  File "myapp.py", line 5, in main\n'
        '    do_thing()\n'
        'ValueError: bad value\n'
    )
    result = ex.extract_snippet(tb)
    assert "/usr/lib/python3.9/importlib" not in result
    assert "myapp.py" in result
    assert "ValueError" in result


def test_snippet_returns_original_if_nothing_filtered():
    tb = "  File \"myapp.py\", line 5, in main\n    do_thing()\nValueError: bad\n"
    assert ex.extract_snippet(tb) == tb


# ---------------------------------------------------------------------------
# format_json_error
# ---------------------------------------------------------------------------

def test_format_json_priority_keys():
    blob = json.dumps({"error": "not found", "status": 404, "path": "/api/users"})
    result = ex.format_json_error(blob)
    lines = result.splitlines()
    assert lines[0].startswith("error:")


def test_format_json_non_json_passthrough():
    text = "plain error text"
    assert ex.format_json_error(text) == text


def test_format_json_invalid_json_passthrough():
    text = "{not valid json"
    assert ex.format_json_error(text) == text


# ---------------------------------------------------------------------------
# _parse_since
# ---------------------------------------------------------------------------

def test_parse_since_valid():
    from datetime import datetime
    result = ex._parse_since("2026-01-15")
    assert result == datetime(2026, 1, 15)


def test_parse_since_invalid_exits():
    with pytest.raises(SystemExit):
        ex._parse_since("not-a-date")


# ---------------------------------------------------------------------------
# History mutation: rate_last, add_note, pin_entry
# ---------------------------------------------------------------------------

def _write_history(path, entries):
    with open(path, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def test_rate_last(tmp_path, capsys):
    history_file = tmp_path / "history"
    _write_history(history_file, [
        {"timestamp": "2026-01-01T00:00:00", "model": "m", "error": "err", "explanation": "expl", "brief": False}
    ])
    with patch.object(ex, "HISTORY_FILE", history_file):
        ex.rate_last(4)

    entry = json.loads(history_file.read_text().strip().splitlines()[-1])
    assert entry["rating"] == 4


def test_rate_last_invalid_exits(tmp_path):
    history_file = tmp_path / "history"
    _write_history(history_file, [
        {"timestamp": "2026-01-01T00:00:00", "model": "m", "error": "err", "explanation": "expl", "brief": False}
    ])
    with patch.object(ex, "HISTORY_FILE", history_file):
        with pytest.raises(SystemExit):
            ex.rate_last(6)


def test_add_note(tmp_path):
    history_file = tmp_path / "history"
    _write_history(history_file, [
        {"timestamp": "2026-01-01T00:00:00", "model": "m", "error": "err", "explanation": "expl", "brief": False}
    ])
    with patch.object(ex, "HISTORY_FILE", history_file):
        ex.add_note("my note here")

    entry = json.loads(history_file.read_text().strip().splitlines()[-1])
    assert entry["notes"] == "my note here"


def test_pin_entry_pins(tmp_path):
    history_file = tmp_path / "history"
    _write_history(history_file, [
        {"timestamp": "2026-01-01T00:00:00", "model": "m", "error": "err", "explanation": "expl", "brief": False}
    ])
    with patch.object(ex, "HISTORY_FILE", history_file):
        ex.pin_entry(True)

    entry = json.loads(history_file.read_text().strip().splitlines()[-1])
    assert entry["pinned"] is True


def test_pin_entry_unpins(tmp_path):
    history_file = tmp_path / "history"
    _write_history(history_file, [
        {"timestamp": "2026-01-01T00:00:00", "model": "m", "error": "err", "explanation": "expl", "brief": False, "pinned": True}
    ])
    with patch.object(ex, "HISTORY_FILE", history_file):
        ex.pin_entry(False)

    entry = json.loads(history_file.read_text().strip().splitlines()[-1])
    assert entry["pinned"] is False


# ---------------------------------------------------------------------------
# clear_history respects pinned entries
# ---------------------------------------------------------------------------

def test_clear_history_keeps_pinned(tmp_path, monkeypatch):
    history_file = tmp_path / "history"
    _write_history(history_file, [
        {"timestamp": "2026-01-01T00:00:00", "model": "m", "error": "deleteme", "explanation": "e", "brief": False},
        {"timestamp": "2026-01-01T00:00:01", "model": "m", "error": "keepme", "explanation": "e", "brief": False, "pinned": True},
    ])
    monkeypatch.setattr("builtins.input", lambda _: "y")
    with patch.object(ex, "HISTORY_FILE", history_file):
        ex.clear_history(None)

    remaining = [json.loads(l) for l in history_file.read_text().strip().splitlines()]
    assert len(remaining) == 1
    assert remaining[0]["error"] == "keepme"


# ---------------------------------------------------------------------------
# show_history / show_recent with --filter
# ---------------------------------------------------------------------------

def test_show_history_filter_type(tmp_path, capsys):
    history_file = tmp_path / "history"
    _write_history(history_file, [
        {"timestamp": "2026-01-01T00:00:00", "model": "m", "error": "TypeError: bad type", "explanation": "type error expl", "brief": False},
        {"timestamp": "2026-01-01T00:00:01", "model": "m", "error": "KeyError: missing key", "explanation": "key error expl", "brief": False},
    ])
    with patch.object(ex, "HISTORY_FILE", history_file):
        ex.show_history(None, filter_type="TypeError")

    out = capsys.readouterr().out
    assert "TypeError" in out
    assert "KeyError" not in out


def test_show_recent_filter_type(tmp_path, capsys):
    history_file = tmp_path / "history"
    _write_history(history_file, [
        {"timestamp": "2026-01-01T00:00:00", "model": "m", "error": "TypeError: bad", "explanation": "expl", "brief": False},
        {"timestamp": "2026-01-01T00:00:01", "model": "m", "error": "ValueError: bad", "explanation": "expl", "brief": False},
    ])
    with patch.object(ex, "HISTORY_FILE", history_file):
        ex.show_recent(10, filter_type="ValueError")

    out = capsys.readouterr().out
    assert "ValueError" in out
    assert "TypeError" not in out


# ---------------------------------------------------------------------------
# list_named
# ---------------------------------------------------------------------------

def test_list_named_shows_only_named(tmp_path, capsys):
    history_file = tmp_path / "history"
    _write_history(history_file, [
        {"timestamp": "2026-01-01T00:00:00", "model": "m", "error": "unnamed err", "explanation": "e", "brief": False},
        {"timestamp": "2026-01-01T00:00:01", "model": "m", "error": "named err", "explanation": "e", "brief": False, "name": "myerror"},
    ])
    with patch.object(ex, "HISTORY_FILE", history_file):
        ex.list_named()

    out = capsys.readouterr().out
    assert "myerror" in out
    assert "unnamed err" not in out


def test_list_named_no_named_entries(tmp_path, capsys):
    history_file = tmp_path / "history"
    _write_history(history_file, [
        {"timestamp": "2026-01-01T00:00:00", "model": "m", "error": "err", "explanation": "e", "brief": False},
    ])
    with patch.object(ex, "HISTORY_FILE", history_file):
        ex.list_named()

    assert "No named entries" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# export_csv
# ---------------------------------------------------------------------------

def test_export_csv_creates_file(tmp_path):
    history_file = tmp_path / "history"
    _write_history(history_file, [
        {"timestamp": "2026-01-01T00:00:00", "model": "claude-sonnet-4-6", "error": "TypeError: bad", "explanation": "it is bad", "brief": False, "rating": 4},
        {"timestamp": "2026-01-01T00:00:01", "model": "claude-opus-4-7", "error": "KeyError: x", "explanation": "missing key", "brief": False},
    ])
    out_csv = tmp_path / "out.csv"
    with patch.object(ex, "HISTORY_FILE", history_file):
        ex.export_csv(str(out_csv))

    assert out_csv.exists()
    with open(out_csv, newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2
    assert rows[0]["model"] == "claude-sonnet-4-6"
    assert rows[0]["rating"] == "4"
    assert rows[0]["error_type"] == "TypeError"
    assert rows[1]["error_type"] == "KeyError"
    assert "explanation_length" in rows[0]


# ---------------------------------------------------------------------------
# call_claude returns 4-tuple
# ---------------------------------------------------------------------------

def test_call_claude_returns_4_tuple(tmp_path):
    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.text_stream = iter(["answer"])
    mock_final = MagicMock()
    mock_final.usage.input_tokens = 10
    mock_final.usage.output_tokens = 5
    mock_stream.get_final_message.return_value = mock_final
    mock_client = MagicMock()
    mock_client.messages.stream.return_value = mock_stream

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("anthropic.Anthropic", return_value=mock_client):
            result = ex.call_claude("some error", model="claude-sonnet-4-6")

    assert len(result) == 4
    text, in_tok, out_tok, elapsed = result
    assert text == "answer"
    assert in_tok == 10
    assert out_tok == 5
    assert elapsed >= 0.0


# ---------------------------------------------------------------------------
# explain_exit_code — known codes answered locally (no API call)
# ---------------------------------------------------------------------------

def test_explain_exit_code_known_no_api(capsys):
    with patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}, clear=True):
        ex.explain_exit_code(0, model="claude-sonnet-4-6", copy=False)

    out = capsys.readouterr().out
    assert "Success" in out


def test_explain_exit_code_sigkill(capsys):
    with patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}, clear=True):
        ex.explain_exit_code(137, model="claude-sonnet-4-6", copy=False)

    out = capsys.readouterr().out
    assert "SIGKILL" in out or "killed" in out.lower()


def test_explain_exit_code_signal_decode(capsys):
    with patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}, clear=True):
        ex.explain_exit_code(130, model="claude-sonnet-4-6", copy=False)

    out = capsys.readouterr().out
    assert "SIGINT" in out or "interrupted" in out.lower()


# ---------------------------------------------------------------------------
# explain_http — known codes answered locally (no API call)
# ---------------------------------------------------------------------------

def test_explain_http_known_no_api(capsys):
    with patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}, clear=True):
        ex.explain_http(404, model="claude-sonnet-4-6", copy=False)

    out = capsys.readouterr().out
    assert "Not Found" in out


def test_explain_http_429(capsys):
    with patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}, clear=True):
        ex.explain_http(429, model="claude-sonnet-4-6", copy=False)

    out = capsys.readouterr().out
    assert "429" in out
    assert "Rate" in out or "rate" in out


# ---------------------------------------------------------------------------
# load_profile / delete_profile
# ---------------------------------------------------------------------------

def test_load_profile_missing_exits(tmp_path):
    config = {"profiles": {"go": {"lang": "go"}}}
    config_file = tmp_path / ".errexrc"
    config_file.write_text(json.dumps(config))
    with patch.object(ex, "CONFIG_FILE", config_file):
        with pytest.raises(SystemExit):
            ex.load_profile("nonexistent", config)


def test_load_profile_returns_merged(tmp_path):
    file_config = {"model": "claude-sonnet-4-6", "profiles": {"go": {"lang": "go", "model": "claude-opus-4-7"}}}
    result = ex.load_profile("go", file_config)
    assert result["lang"] == "go"
    assert result["model"] == "claude-opus-4-7"


def test_delete_profile_removes_entry(tmp_path, capsys):
    config = {"model": "claude-sonnet-4-6", "profiles": {"go": {"lang": "go"}, "py": {"lang": "python"}}}
    config_file = tmp_path / ".errexrc"
    config_file.write_text(json.dumps(config))
    with patch.object(ex, "CONFIG_FILE", config_file):
        ex.delete_profile("go")

    saved = json.loads(config_file.read_text())
    assert "go" not in saved.get("profiles", {})
    assert "py" in saved.get("profiles", {})


def test_delete_profile_missing_exits(tmp_path):
    config = {"profiles": {"go": {"lang": "go"}}}
    config_file = tmp_path / ".errexrc"
    config_file.write_text(json.dumps(config))
    with patch.object(ex, "CONFIG_FILE", config_file):
        with pytest.raises(SystemExit):
            ex.delete_profile("nonexistent")
