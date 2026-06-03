"""Tests for errex MCP server — exercises _handle() directly without touching stdio."""
from __future__ import annotations

import pytest
from errex.mcp_server import _handle, TOOLS


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _req(method: str, id_: int = 1, params: dict | None = None) -> dict:
    req: dict = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        req["params"] = params
    return req


# ---------------------------------------------------------------------------
# 1. initialize → correct response shape
# ---------------------------------------------------------------------------

def test_initialize_response_shape():
    resp = _handle(_req("initialize"))
    assert resp is not None
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    result = resp["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert "tools" in result["capabilities"]
    assert result["serverInfo"]["name"] == "errex"


# ---------------------------------------------------------------------------
# 2. tools/list → returns list with all 6 tools
# ---------------------------------------------------------------------------

def test_tools_list_returns_all_tools():
    resp = _handle(_req("tools/list"))
    assert resp is not None
    tools = resp["result"]["tools"]
    tool_names = {t["name"] for t in tools}
    expected = {
        "explain_error",
        "explain_exit_code",
        "explain_http_status",
        "explain_cron",
        "run_scan",
        "list_patterns",
    }
    assert expected == tool_names
    assert len(tools) == 6


# ---------------------------------------------------------------------------
# 3. tools/call explain_exit_code code=0 → "Success" in text
# ---------------------------------------------------------------------------

def test_explain_exit_code_zero():
    resp = _handle(_req("tools/call", params={
        "name": "explain_exit_code",
        "arguments": {"code": 0},
    }))
    assert resp is not None
    content = resp["result"]["content"]
    assert len(content) == 1
    assert content[0]["type"] == "text"
    assert "Success" in content[0]["text"]
    assert resp["result"].get("isError") is None  # no error flag


# ---------------------------------------------------------------------------
# 4. tools/call explain_http_status code=404 → "Not Found" in text
# ---------------------------------------------------------------------------

def test_explain_http_status_404():
    resp = _handle(_req("tools/call", params={
        "name": "explain_http_status",
        "arguments": {"code": 404},
    }))
    assert resp is not None
    text = resp["result"]["content"][0]["text"]
    assert "Not Found" in text
    assert "404" in text


# ---------------------------------------------------------------------------
# 5. tools/call explain_error with NameError → matches local pattern
# ---------------------------------------------------------------------------

def test_explain_error_name_error():
    resp = _handle(_req("tools/call", params={
        "name": "explain_error",
        "arguments": {"error_text": "NameError: name 'foo' is not defined"},
    }))
    assert resp is not None
    text = resp["result"]["content"][0]["text"]
    # Should match local pattern — title or explanation contains the key info
    assert "foo" in text or "defined" in text or "NameError" in text
    assert resp["result"].get("isError") is None


# ---------------------------------------------------------------------------
# 6. tools/call list_patterns → returns non-empty list
# ---------------------------------------------------------------------------

def test_list_patterns_non_empty():
    resp = _handle(_req("tools/call", params={
        "name": "list_patterns",
        "arguments": {},
    }))
    assert resp is not None
    text = resp["result"]["content"][0]["text"]
    assert "patterns" in text.lower()
    assert text.count("- ") >= 5


# ---------------------------------------------------------------------------
# 7. tools/call with unknown tool name → isError=true
# ---------------------------------------------------------------------------

def test_unknown_tool_is_error():
    resp = _handle(_req("tools/call", params={
        "name": "nonexistent_tool",
        "arguments": {},
    }))
    assert resp is not None
    result = resp["result"]
    assert result.get("isError") is True
    text = result["content"][0]["text"]
    assert "unknown tool" in text.lower() or "nonexistent_tool" in text


# ---------------------------------------------------------------------------
# Bonus: initialized notification → no response (returns None)
# ---------------------------------------------------------------------------

def test_initialized_notification_returns_none():
    # Notifications have no "id"
    notif = {"jsonrpc": "2.0", "method": "initialized"}
    resp = _handle(notif)
    assert resp is None


# ---------------------------------------------------------------------------
# Bonus: explain_http_status for a signal exit code
# ---------------------------------------------------------------------------

def test_explain_exit_code_sigkill():
    resp = _handle(_req("tools/call", params={
        "name": "explain_exit_code",
        "arguments": {"code": 137},
    }))
    text = resp["result"]["content"][0]["text"]
    assert "SIGKILL" in text or "killed" in text.lower()


# ---------------------------------------------------------------------------
# Bonus: explain_cron for a simple expression
# ---------------------------------------------------------------------------

def test_explain_cron_every_minute():
    resp = _handle(_req("tools/call", params={
        "name": "explain_cron",
        "arguments": {"expression": "* * * * *"},
    }))
    text = resp["result"]["content"][0]["text"]
    assert "Every minute" in text or "every minute" in text.lower()
