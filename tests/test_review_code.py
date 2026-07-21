"""Unit tests for errex/review_code.py — no API calls."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stream(text: str):
    """Return a mock streaming context manager that yields `text` char-by-char."""
    mock_stream = MagicMock()
    mock_final = MagicMock()
    mock_final.usage.input_tokens = 10
    mock_final.usage.output_tokens = 20
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.text_stream = iter([text])
    mock_stream.get_final_message = MagicMock(return_value=mock_final)
    return mock_stream


# ---------------------------------------------------------------------------
# review_code — missing API key
# ---------------------------------------------------------------------------

def test_review_code_no_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    src = tmp_path / "hello.py"
    src.write_text("print('hello')")
    from errex.review_code import review_code
    with pytest.raises(SystemExit) as exc:
        review_code(str(src))
    assert exc.value.code == 1


def test_review_code_missing_file(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from errex.review_code import review_code
    with pytest.raises(SystemExit) as exc:
        review_code("/does/not/exist/file.py")
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# review_code — successful path (mocked API)
# ---------------------------------------------------------------------------

def test_review_code_calls_api(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    src = tmp_path / "app.js"
    src.write_text("const x = 1;\nconsole.log(x);\n")

    mock_client = MagicMock()
    mock_client.messages.stream.return_value = _make_stream("Looks clean.")

    with patch("errex.review_code.anthropic.Anthropic", return_value=mock_client):
        from errex.review_code import review_code
        review_code(str(src), model="claude-test")

    assert mock_client.messages.stream.called
    call_kwargs = mock_client.messages.stream.call_args[1]
    # model was passed
    assert call_kwargs["model"] == "claude-test"
    # file name mentioned in prompt
    msgs = call_kwargs["messages"]
    assert "app.js" in msgs[0]["content"]


def test_review_code_truncates_large_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    src = tmp_path / "big.py"
    src.write_text("x = 1\n" * 3000)  # ~18 000 chars

    mock_client = MagicMock()
    mock_client.messages.stream.return_value = _make_stream("OK")

    with patch("errex.review_code.anthropic.Anthropic", return_value=mock_client):
        from errex.review_code import review_code
        review_code(str(src), model="claude-test")

    call_kwargs = mock_client.messages.stream.call_args[1]
    prompt = call_kwargs["messages"][0]["content"]
    assert "truncated" in prompt


def test_review_code_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    src = tmp_path / "m.py"
    src.write_text("pass")

    mock_client = MagicMock()
    mock_client.messages.stream.return_value = _make_stream("Clean file.")

    with patch("errex.review_code.anthropic.Anthropic", return_value=mock_client):
        with patch("errex.output.copy_to_clipboard") as mock_copy:
            from errex.review_code import review_code
            review_code(str(src), model="claude-test", copy=True)
    mock_copy.assert_called_once_with("Clean file.")


def test_review_code_show_tokens(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    src = tmp_path / "t.py"
    src.write_text("a = 1")

    mock_client = MagicMock()
    mock_client.messages.stream.return_value = _make_stream("OK")

    with patch("errex.review_code.anthropic.Anthropic", return_value=mock_client):
        with patch("errex.output.show_token_usage") as mock_tok:
            from errex.review_code import review_code
            review_code(str(src), model="claude-test", show_tokens=True)
    mock_tok.assert_called_once()
