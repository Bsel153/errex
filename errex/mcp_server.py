"""MCP server — exposes errex tools over stdio JSON-RPC for Claude Desktop and other MCP clients."""
from __future__ import annotations

import io
import json
import sys

SERVER_INFO = {"name": "errex", "version": "0.25.0"}

TOOLS = [
    {
        "name": "explain_error",
        "description": "Explain an error message in plain English using local pattern matching.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "error_text": {
                    "type": "string",
                    "description": "The error message to explain",
                },
                "lang": {
                    "type": "string",
                    "description": "Language hint (python, rust, go, etc.)",
                },
            },
            "required": ["error_text"],
        },
    },
    {
        "name": "explain_exit_code",
        "description": "Look up the meaning of a shell exit code.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "integer",
                    "description": "The exit code to look up",
                },
            },
            "required": ["code"],
        },
    },
    {
        "name": "explain_http_status",
        "description": "Look up the meaning of an HTTP status code.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "integer",
                    "description": "The HTTP status code to look up",
                },
            },
            "required": ["code"],
        },
    },
    {
        "name": "explain_cron",
        "description": "Explain a cron expression in plain English.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "The cron expression to explain (e.g. '0 * * * *')",
                },
            },
            "required": ["expression"],
        },
    },
    {
        "name": "run_scan",
        "description": "Scan common log locations for recent error files.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "Platform hint (linux, darwin, windows)",
                },
                "network": {
                    "type": "boolean",
                    "description": "Include network-related log paths",
                },
            },
        },
    },
    {
        "name": "list_patterns",
        "description": "List all available local error patterns that errex can recognise offline.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


def _read_message() -> dict | None:
    """Read one LSP-framed message from stdin.

    Format: ``Content-Length: N\\r\\n\\r\\n`` followed by N bytes of JSON.
    Returns the parsed dict, or None on EOF / parse failure.
    """
    headers: dict[str, str] = {}
    while True:
        raw = sys.stdin.buffer.readline()
        if not raw:
            return None
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line:
            # Blank line — end of headers
            break
        if ":" in line:
            key, _, value = line.partition(":")
            headers[key.strip().lower()] = value.strip()

    length_str = headers.get("content-length")
    if length_str is None:
        return None
    try:
        length = int(length_str)
    except ValueError:
        return None

    body = sys.stdin.buffer.read(length)
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _write_message(msg: dict) -> None:
    """Write one LSP-framed JSON-RPC message to stdout."""
    body = json.dumps(msg)
    frame = f"Content-Length: {len(body)}\r\n\r\n{body}"
    sys.stdout.buffer.write(frame.encode("utf-8"))
    sys.stdout.buffer.flush()


def _ok(id_: object, result: object) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _error_response(id_: object, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _tool_result(text: str, is_error: bool = False) -> dict:
    result: dict = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["isError"] = True
    return result


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _call_explain_error(params: dict) -> dict:
    error_text = params.get("error_text", "")
    if not error_text:
        return _tool_result("Error: error_text is required.", is_error=True)

    from .patterns import match_pattern
    hit = match_pattern(error_text)
    if hit:
        title, explanation = hit
        return _tool_result(f"**{title}**\n\n{explanation}")

    return _tool_result(
        "No local pattern matched this error. To get a full AI-powered explanation, "
        "run `errex` in your terminal with the error text (requires ANTHROPIC_API_KEY)."
    )


def _call_explain_exit_code(params: dict) -> dict:
    code = params.get("code")
    if code is None:
        return _tool_result("Error: code is required.", is_error=True)

    from ._constants import EXIT_CODES, _SIGNAL_NAMES
    if code in EXIT_CODES:
        name, explanation = EXIT_CODES[code]
        return _tool_result(f"Exit {code}: {name}\n\n{explanation}")

    if 128 < code <= 165:
        sig_num = code - 128
        sig_name = _SIGNAL_NAMES.get(sig_num, f"signal {sig_num}")
        return _tool_result(
            f"Exit {code}: Killed by {sig_name} (signal {sig_num})\n\n"
            f"Exit code {code} = 128 + {sig_num} (the signal number)."
        )

    return _tool_result(
        f"Exit code {code} is not a well-known standard exit code. "
        "It may be application-specific — check the tool's documentation."
    )


def _call_explain_http_status(params: dict) -> dict:
    code = params.get("code")
    if code is None:
        return _tool_result("Error: code is required.", is_error=True)

    from ._constants import HTTP_CODES
    if code in HTTP_CODES:
        name, explanation = HTTP_CODES[code]
        category = {
            1: "Informational", 2: "Success", 3: "Redirection",
            4: "Client Error", 5: "Server Error",
        }.get(code // 100, "Unknown")
        return _tool_result(f"HTTP {code}: {name} ({category})\n\n{explanation}")

    return _tool_result(
        f"HTTP status {code} is not a standard well-known code. "
        "It may be a vendor extension — check the API documentation."
    )


def _call_explain_cron(params: dict) -> dict:
    expression = params.get("expression", "")
    if not expression:
        return _tool_result("Error: expression is required.", is_error=True)

    from .explainers import _cron_local

    local = _cron_local(expression)
    if local:
        return _tool_result(
            f"Cron expression: `{expression}`\n\n{local}\n\n"
            f"Fields: minute  hour  day-of-month  month  day-of-week\n"
            f"        {expression}"
        )

    # Fall back: describe the fields manually
    fields = expression.strip().split()
    if len(fields) == 5:
        mn, hr, dm, mo, dw = fields
        return _tool_result(
            f"Cron expression: `{expression}`\n\n"
            f"Fields (minute hour day-of-month month day-of-week):\n"
            f"  minute:       {mn}\n"
            f"  hour:         {hr}\n"
            f"  day of month: {dm}\n"
            f"  month:        {mo}\n"
            f"  day of week:  {dw}\n\n"
            "This expression contains ranges or complex patterns. "
            "Use a cron reference or https://crontab.guru/ for a full breakdown."
        )

    return _tool_result(
        f"Could not parse cron expression: {expression!r}. "
        "A standard cron expression has 5 space-separated fields: "
        "minute hour day-of-month month day-of-week."
    )


def _call_run_scan(params: dict) -> dict:
    import platform as _platform
    import os
    from pathlib import Path

    plat = params.get("platform") or _platform.system().lower()
    network = params.get("network", False)

    # Candidate log paths (common locations)
    candidates: list[Path] = []

    if plat in ("linux", "darwin"):
        candidates += [
            Path("/var/log/syslog"),
            Path("/var/log/messages"),
            Path("/var/log/kern.log"),
            Path("/var/log/auth.log"),
            Path(os.path.expanduser("~/.npm/_logs")),
        ]
    if plat == "darwin":
        candidates += [
            Path("/var/log/system.log"),
            Path(os.path.expanduser("~/Library/Logs")),
        ]

    if network:
        candidates += [
            Path("/var/log/nginx/error.log"),
            Path("/var/log/apache2/error.log"),
            Path("/var/log/httpd/error_log"),
        ]

    found = []
    for path in candidates:
        if path.exists():
            try:
                stat = path.stat()
                found.append({
                    "path": str(path),
                    "size_bytes": stat.st_size,
                    "is_dir": path.is_dir(),
                })
            except OSError:
                pass

    result = {
        "platform": plat,
        "network": network,
        "found": found,
        "count": len(found),
    }
    return _tool_result(json.dumps(result, indent=2))


def _call_list_patterns(_params: dict) -> dict:
    from .patterns import list_patterns
    patterns = list_patterns()
    lines = [f"- {p}" for p in patterns]
    text = f"Available local error patterns ({len(patterns)} total):\n\n" + "\n".join(lines)
    return _tool_result(text)


_TOOL_HANDLERS = {
    "explain_error": _call_explain_error,
    "explain_exit_code": _call_explain_exit_code,
    "explain_http_status": _call_explain_http_status,
    "explain_cron": _call_explain_cron,
    "run_scan": _call_run_scan,
    "list_patterns": _call_list_patterns,
}


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

def _handle(req: dict) -> dict | None:
    """Dispatch a JSON-RPC request and return the response dict, or None for notifications."""
    method = req.get("method", "")
    id_ = req.get("id")  # None for notifications

    if method == "initialize":
        return _ok(id_, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })

    if method == "initialized":
        # Notification — no response
        return None

    if method == "tools/list":
        return _ok(id_, {"tools": TOOLS})

    if method == "tools/call":
        params = req.get("params", {})
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {}) or {}

        handler = _TOOL_HANDLERS.get(tool_name)
        if handler is None:
            if id_ is not None:
                return _ok(id_, _tool_result(
                    f"Error: unknown tool '{tool_name}'. "
                    f"Available tools: {', '.join(_TOOL_HANDLERS)}",
                    is_error=True,
                ))
            return None

        try:
            result = handler(tool_args)
        except Exception as exc:  # noqa: BLE001
            result = _tool_result(f"Error: {exc}", is_error=True)

        if id_ is not None:
            return _ok(id_, result)
        return None

    if method == "ping":
        return _ok(id_, {})

    # Unknown method — return error if this has an id (not a notification)
    if id_ is not None:
        return _error_response(id_, -32601, f"Method not found: {method}")
    return None


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def serve() -> None:
    """Read MCP messages from stdin, dispatch, write responses to stdout."""
    while True:
        msg = _read_message()
        if msg is None:
            break
        resp = _handle(msg)
        if resp is not None:
            _write_message(resp)
