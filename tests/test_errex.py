import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch
from io import StringIO

import errex as ex


# --- get_error_input ---

def test_get_error_input_reads_file(tmp_path):
    f = tmp_path / "error.txt"
    f.write_text("TypeError: something went wrong")
    assert ex.get_error_input(str(f)) == "TypeError: something went wrong"


def test_get_error_input_strips_whitespace(tmp_path):
    f = tmp_path / "error.txt"
    f.write_text("  some error\n\n")
    assert ex.get_error_input(str(f)) == "some error"


def test_get_error_input_missing_file_exits(tmp_path):
    with pytest.raises(SystemExit) as exc:
        ex.get_error_input(str(tmp_path / "nope.txt"))
    assert exc.value.code == 1


def test_get_error_input_reads_stdin():
    with patch("sys.stdin", StringIO("error from stdin")):
        with patch("sys.stdin.isatty", return_value=False):
            result = ex.get_error_input(None)
    assert result == "error from stdin"


# --- save_history ---

def test_save_history_writes_json_line(tmp_path):
    history_file = str(tmp_path / "history")
    with patch.object(ex, "HISTORY_FILE", history_file):
        ex.save_history("some error", "some explanation", "claude-sonnet-4-6", False)

    with open(history_file) as f:
        entry = json.loads(f.read().strip())

    assert entry["error"] == "some error"
    assert entry["explanation"] == "some explanation"
    assert entry["model"] == "claude-sonnet-4-6"
    assert entry["brief"] is False
    assert "timestamp" in entry


def test_save_history_appends(tmp_path):
    history_file = str(tmp_path / "history")
    with patch.object(ex, "HISTORY_FILE", history_file):
        ex.save_history("error 1", "explanation 1", "claude-sonnet-4-6", False)
        ex.save_history("error 2", "explanation 2", "claude-sonnet-4-6", True)

    with open(history_file) as f:
        lines = f.read().strip().splitlines()

    assert len(lines) == 2
    assert json.loads(lines[1])["error"] == "error 2"


def test_save_history_truncates_long_errors(tmp_path):
    history_file = str(tmp_path / "history")
    long_error = "x" * 500
    with patch.object(ex, "HISTORY_FILE", history_file):
        ex.save_history(long_error, "explanation", "claude-sonnet-4-6", False)

    with open(history_file) as f:
        entry = json.loads(f.read().strip())

    assert len(entry["error"]) == 200


# --- explain_error: missing API key ---

def test_explain_error_exits_without_api_key():
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(SystemExit) as exc:
            ex.explain_error("some error", model="claude-sonnet-4-6")
    assert exc.value.code == 1


# --- explain_error: mocked API ---

def test_explain_error_streams_output(tmp_path, capsys):
    history_file = str(tmp_path / "history")

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

    output = capsys.readouterr().out
    assert "This is an error." in output


def test_explain_error_brief_uses_short_prompt(tmp_path):
    history_file = str(tmp_path / "history")

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
