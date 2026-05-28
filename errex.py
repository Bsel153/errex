"""
errex — Error Explainer
======================
Paste or pipe an error message and get a clear, plain-English explanation.

Usage:
  errex                       # interactive: paste your error, then Ctrl+D (Mac/Linux) or Ctrl+Z (Windows)
  errex traceback.txt         # read error from a file
  cat error.log | errex       # pipe error via stdin
  errex --watch server.log    # watch a log file and explain errors as they appear
  errex --fix error.txt       # get just the fix command, no explanation

Requirements: pip install errex
Set ANTHROPIC_API_KEY in your environment.
"""

from __future__ import annotations

import sys
import os
import argparse
import json
import platform
import subprocess
import time
from datetime import datetime
from pathlib import Path

import re
import urllib.request
import urllib.error
import urllib.parse
import importlib.metadata
from collections import Counter

import anthropic
from rich.console import Console
from rich.markdown import Markdown
from rich.rule import Rule
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns

console = Console()
err_console = Console(stderr=True)

CONFIG_FILE = Path.home() / ".errexrc"
HISTORY_FILE = Path.home() / ".errex_history"

ERROR_PATTERNS = {"error", "exception", "traceback", "fatal", "panic", "fail", "critical"}

SYSTEM_PROMPT = """You are a senior software engineer with 15+ years of experience across Python, JavaScript, TypeScript, Go, Rust, Java, C, C++, shell scripting, SQL, and cloud infrastructure. You specialize in debugging and explaining errors clearly to developers at all levels.

When given an error message, stack trace, or exception, you will:

1. **Identify the error type** — State what kind of error this is (e.g., NameError, NullPointerException, segfault, syntax error, network timeout) and which language/runtime/tool produced it.

2. **Explain in plain English** — Describe what the error actually means in simple terms, as if explaining to a smart colleague who hasn't seen this error before. Avoid jargon where possible; define it when necessary.

3. **Identify the most likely root cause** — Point to the specific line(s), function(s), or concept that is the root of the problem. If there are multiple likely causes, rank them by probability.

4. **Give numbered fix steps** — Provide concrete, actionable steps to resolve the error. Each step should be specific enough to actually execute. Include code snippets where they would help.

5. **Note common gotchas** — Highlight any subtle pitfalls, follow-on errors, or related mistakes developers often make with this error type. This is where you share the "experience" — things that aren't obvious from the error message alone.

Formatting rules:
- Use markdown headers and bullet points for clarity
- Keep the explanation conversational but precise
- If the error is ambiguous or lacks context, note what additional information would help diagnose it fully
- Do not pad your response with unnecessary caveats or disclaimers
- Be direct and confident in your diagnosis"""

LINT_PROMPT = """You are a senior software engineer performing a code review. When given a piece of code, scan it for potential problems and report them clearly.

For each issue found:
- **Severity**: 🔴 Critical / 🟡 Warning / 🔵 Info
- **Line(s)**: reference the relevant line numbers if possible
- **Issue**: what's wrong or risky
- **Fix**: concrete suggestion to resolve it

Categories to check: bugs, security vulnerabilities, performance issues, error handling gaps, deprecated APIs, undefined behaviour, resource leaks, type errors, and style issues that could cause confusion.

If the code looks clean, say so briefly. Be direct — don't invent issues that aren't there.

Output as markdown."""

DIFF_PROMPT = """You are a senior software engineer reviewing a code change. When given a git diff or patch, explain it clearly:

1. **Summary** — One sentence: what does this change accomplish overall?
2. **What changed** — Walk through the key changes. Focus on logic and behaviour, not cosmetic edits. Group by file if multiple files are affected.
3. **Potential issues** — Flag anything that could introduce bugs, regressions, security problems, or unexpected behaviour. Be specific about the risk and why.
4. **What to test** — Concrete things a reviewer or QA engineer should verify after this change.

Skip files that only have trivial changes (whitespace, imports, formatting) unless they're risky. Use markdown. Be direct."""

CODE_PROMPT = """You are a senior software engineer and excellent technical communicator. When given a piece of code, you will:

1. **What it does** — A plain-English summary of the code's purpose (1-2 sentences).
2. **How it works** — Walk through the key logic step by step. Focus on the non-obvious parts; don't narrate trivial lines.
3. **Inputs & outputs** — What goes in, what comes out, what side effects it has.
4. **Gotchas & edge cases** — Anything surprising, fragile, or worth watching out for.
5. **Suggested improvements** — Optional: one or two concrete ways to make it cleaner, faster, or safer.

Use markdown. Be concise but complete."""

LOG_SUMMARY_PROMPT = """You are a senior engineer analyzing a log file. Produce a concise diagnostic digest:

1. **Error summary** — List each distinct error type with an approximate count. Skip routine info/debug lines.
2. **Most critical issue** — Which error is most likely causing user-facing problems right now?
3. **Timeline** — If timestamps are present, note when errors started and whether frequency is increasing or recovering.
4. **Root cause hypothesis** — What is the most likely underlying cause linking the errors?
5. **Recommended action** — The single most important thing to investigate or fix first.

Use markdown. Be concise and direct."""

REGEX_PROMPT = """You are a senior developer and regex expert. When given a regular expression, explain it clearly:

1. **What it matches** — plain-English summary of what strings this pattern accepts
2. **Component breakdown** — explain each token (groups, quantifiers, character classes, anchors, alternation) in a compact table: | Part | Meaning |
3. **Match examples** — 3–5 strings that match, 2–3 that don't
4. **Gotchas** — edge cases, greedy vs lazy, backtracking, flag sensitivity, or platform differences worth knowing

Be concise. Use markdown."""

SHELL_FUNCTION = """
# errex shell integration — added by errex --install-shell
function errex-last() {
  eval "$(fc -ln -1)" 2>&1 | errex "$@"
}
"""


CONFIG_DEFAULTS: dict = {"model": "claude-sonnet-4-6", "brief": False, "lang": None, "copy": False}
CONFIG_TYPES: dict = {"model": str, "brief": bool, "lang": str, "copy": bool}

API_TIMEOUT: int = 30  # seconds — overridden by --timeout

EXIT_CODES: dict[int, tuple[str, str]] = {
    0:   ("Success", "The command completed successfully."),
    1:   ("General error", "The command failed — check the output above for details."),
    2:   ("Misuse of shell built-in", "Invalid usage of a shell built-in, or the shell couldn't parse the command."),
    126: ("Permission denied / not executable", "The command exists but cannot be run — check permissions with `ls -l`."),
    127: ("Command not found", "The command isn't in your PATH. Check for typos or install the missing tool."),
    128: ("Invalid exit argument", "exit() was called with an out-of-range value."),
    129: ("SIGHUP", "Process received SIGHUP — the controlling terminal was closed."),
    130: ("SIGINT — interrupted", "Process was interrupted by the user (Ctrl+C)."),
    131: ("SIGQUIT", "Process was killed by SIGQUIT (Ctrl+\\). A core dump may have been written."),
    132: ("SIGILL — illegal instruction", "Process executed an illegal CPU instruction — likely a corrupted binary or compiler bug."),
    134: ("SIGABRT — aborted", "Process called abort() — usually from a failed assert() or intentional abort."),
    135: ("SIGBUS — bus error", "Process tried a misaligned or non-existent memory access."),
    136: ("SIGFPE — arithmetic error", "Floating-point exception: division by zero, overflow, or invalid operation."),
    137: ("SIGKILL — killed", "Process was forcibly killed — likely `kill -9` or the OOM killer (out of memory)."),
    139: ("SIGSEGV — segmentation fault", "Process accessed memory it doesn't own: null pointer, buffer overflow, or use-after-free."),
    141: ("SIGPIPE — broken pipe", "Tried to write to a pipe whose reader already exited."),
    143: ("SIGTERM — terminated", "Process received a graceful shutdown request (SIGTERM) and was killed."),
    255: ("Exit status out of range", "The process returned -1 or 255 — often from SSH errors, or a script using `exit 255`."),
}

_SIGNAL_NAMES: dict[int, str] = {
    1: "SIGHUP", 2: "SIGINT", 3: "SIGQUIT", 4: "SIGILL", 6: "SIGABRT",
    7: "SIGBUS", 8: "SIGFPE", 9: "SIGKILL", 10: "SIGUSR1", 11: "SIGSEGV",
    12: "SIGUSR2", 13: "SIGPIPE", 14: "SIGALRM", 15: "SIGTERM",
    17: "SIGCHLD", 18: "SIGCONT", 19: "SIGSTOP", 20: "SIGTSTP",
}

HTTP_CODES: dict[int, tuple[str, str]] = {
    100: ("Continue", "Server received headers; client should proceed to send the body."),
    101: ("Switching Protocols", "Server is switching protocols as requested (e.g. upgrading to WebSocket)."),
    200: ("OK", "Request succeeded. The response body contains the result."),
    201: ("Created", "Request succeeded and a new resource was created. Location header points to it."),
    202: ("Accepted", "Request accepted for async processing — not yet complete."),
    204: ("No Content", "Request succeeded but no response body — normal after DELETE or PUT."),
    206: ("Partial Content", "Server is returning part of the resource due to a Range header."),
    301: ("Moved Permanently", "Resource has permanently moved to the URL in Location. Update your links."),
    302: ("Found (Temporary Redirect)", "Resource is temporarily elsewhere. Use the original URL next time."),
    303: ("See Other", "Redirect to a different URI using GET — common after a POST."),
    304: ("Not Modified", "Cached version is still valid — use your cached copy."),
    307: ("Temporary Redirect", "Like 302, but the HTTP method must not change on redirect."),
    308: ("Permanent Redirect", "Like 301, but the HTTP method must not change on redirect."),
    400: ("Bad Request", "Server couldn't parse the request. Check your body, headers, or query params for syntax errors."),
    401: ("Unauthorized", "Authentication required. Missing or invalid API key, token, or credentials."),
    402: ("Payment Required", "Payment or quota needed to access this resource."),
    403: ("Forbidden", "Server understood the request but your credentials lack permission for this resource."),
    404: ("Not Found", "No resource at this URL. Check for typos or whether it was deleted."),
    405: ("Method Not Allowed", "This endpoint doesn't support the HTTP method you used (GET/POST/PUT/etc.)."),
    408: ("Request Timeout", "Server timed out waiting for your request. Client sent data too slowly."),
    409: ("Conflict", "Request conflicts with current server state — duplicate resource or version mismatch."),
    410: ("Gone", "Resource permanently deleted and won't return (stricter than 404)."),
    413: ("Payload Too Large", "Request body exceeds the server's size limit. Reduce payload or chunk the upload."),
    415: ("Unsupported Media Type", "Content-Type is not supported. Check you're sending the right format (e.g. application/json)."),
    422: ("Unprocessable Entity", "Request is well-formed but has semantic errors — common for API validation failures."),
    429: ("Too Many Requests", "Rate limit hit. Check the Retry-After header and back off before retrying."),
    431: ("Request Header Fields Too Large", "One or more request headers are too large for the server to accept."),
    500: ("Internal Server Error", "Unexpected server-side error. Check server logs — this is a bug on the server."),
    501: ("Not Implemented", "Server doesn't support the functionality needed for this request."),
    502: ("Bad Gateway", "Gateway got an invalid response from upstream. Often a deploy issue or upstream outage."),
    503: ("Service Unavailable", "Server temporarily overloaded or down for maintenance. Retry with exponential backoff."),
    504: ("Gateway Timeout", "Gateway didn't get a response from upstream in time. Upstream may be slow or down."),
    507: ("Insufficient Storage", "Server cannot store the data needed to complete the request."),
    508: ("Loop Detected", "Server detected an infinite loop while processing (WebDAV)."),
}

_CRON_DOW = {0: "Sun", 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}
_CRON_MONTH = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
               7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}

_STDLIB_RE = re.compile(
    r'(site-packages|dist-packages|/lib/python\d|\\lib\\python\d'
    r'|node_modules|/usr/lib/|\\usr\\lib\\'
    r'|\$GOROOT|/go/pkg/|runtime/panic\.go|<frozen importlib|<string>)',
    re.IGNORECASE,
)


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return {**CONFIG_DEFAULTS, **json.load(f)}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(CONFIG_DEFAULTS)


def manage_config(assignment: str | None) -> None:
    """View or set a config value in ~/.errexrc."""
    file_config: dict = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                file_config = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    if assignment is None:
        console.rule("[bold cyan]errex — Config[/bold cyan]")
        console.print(f"[dim]{CONFIG_FILE}[/dim]\n")
        table = Table(show_header=True, header_style="bold magenta", box=None, show_edge=False)
        table.add_column("Key", style="cyan", min_width=8)
        table.add_column("Value", min_width=20)
        table.add_column("Source", style="dim")
        for key, default in CONFIG_DEFAULTS.items():
            if key in file_config:
                table.add_row(key, str(file_config[key]), "~/.errexrc")
            else:
                table.add_row(key, str(default), "default")
        console.print(table)
        console.print(f"\n[dim]Set a value:   errex --config model=claude-opus-4-7[/dim]")
        console.print(f"[dim]Clear a value: errex --config lang=null[/dim]")
        return

    if "=" not in assignment:
        err_console.print(f"[red]errex: expected key=value, got: {assignment!r}[/red]")
        err_console.print(f"[dim]Valid keys: {', '.join(CONFIG_DEFAULTS)}[/dim]")
        sys.exit(1)

    key, _, raw = assignment.partition("=")
    key, raw = key.strip(), raw.strip()

    if key not in CONFIG_TYPES:
        err_console.print(f"[red]errex: unknown config key '{key}'[/red]")
        err_console.print(f"[dim]Valid keys: {', '.join(CONFIG_DEFAULTS)}[/dim]")
        sys.exit(1)

    if raw.lower() == "null":
        file_config.pop(key, None)
        with open(CONFIG_FILE, "w") as f:
            json.dump(file_config, f, indent=2)
        console.print(f"[green]Cleared[/green] [cyan]{key}[/cyan]  [dim](reset to default: {CONFIG_DEFAULTS[key]})[/dim]")
        return

    if CONFIG_TYPES[key] is bool:
        if raw.lower() in ("true", "1", "yes"):
            value: bool | str = True
        elif raw.lower() in ("false", "0", "no"):
            value = False
        else:
            err_console.print(f"[red]errex: '{key}' expects true/false, got: {raw!r}[/red]")
            sys.exit(1)
    else:
        value = raw

    file_config[key] = value
    with open(CONFIG_FILE, "w") as f:
        json.dump(file_config, f, indent=2)
    console.print(f"[green]Set[/green] [cyan]{key}[/cyan] = [bold]{value}[/bold]  [dim]({CONFIG_FILE})[/dim]")


def read_file(path: str) -> str:
    if not os.path.exists(path):
        err_console.print(f"[red]errex: file not found: {path}[/red]")
        sys.exit(1)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read().strip()


def get_error_input(files: list[str]) -> str:
    """Read error input from file argument(s), piped stdin, or interactive paste."""
    if files:
        return read_file(files[0])

    if not sys.stdin.isatty():
        return sys.stdin.read().strip()

    console.print("[dim]Paste your error below. Press Ctrl+D (Mac/Linux) or Ctrl+Z+Enter (Windows) when done:[/dim]\n")
    lines = []
    try:
        while True:
            line = input()
            lines.append(line)
    except EOFError:
        pass
    return "\n".join(lines).strip()


def share_explanation(error_text: str, explanation: str) -> None:
    """Upload explanation to paste.rs and print the shareable URL."""
    content = f"# Error\n\n```\n{error_text}\n```\n\n# Explanation\n\n{explanation}\n"
    try:
        req = urllib.request.Request(
            "https://paste.rs",
            data=content.encode("utf-8"),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            url = resp.read().decode("utf-8").strip()
        console.print(f"\n[bold green]Shareable link:[/bold green] [cyan]{url}[/cyan]")
    except urllib.error.URLError as e:
        err_console.print(f"[yellow]errex: could not create share link — {e}[/yellow]")


def copy_to_clipboard(text: str) -> None:
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["pbcopy"], input=text.encode(), check=True)
        elif system == "Linux":
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
        elif system == "Windows":
            subprocess.run(["clip"], input=text.encode(), check=True)
        err_console.print("[dim](copied to clipboard)[/dim]")
    except (subprocess.CalledProcessError, FileNotFoundError):
        err_console.print("[yellow]errex: could not copy to clipboard[/yellow]")


def save_history(error_text: str, explanation: str, model: str, brief: bool, name: str | None = None) -> None:
    entry = {
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "brief": brief,
        "error": error_text[:200],
        "explanation": explanation,
    }
    if name:
        entry["name"] = name
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _parse_since(since: str) -> datetime | None:
    """Parse a YYYY-MM-DD date string, return a datetime or None on failure."""
    try:
        return datetime.strptime(since, "%Y-%m-%d")
    except ValueError:
        err_console.print(f"[red]errex: --since expects YYYY-MM-DD, got: {since!r}[/red]")
        sys.exit(1)


def show_history(search: str | None, since: str | None = None) -> None:
    """Print past explanations from the history file."""
    if not HISTORY_FILE.exists():
        console.print("[yellow]No history yet.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if since:
        cutoff = _parse_since(since)
        entries = [
            e for e in entries
            if datetime.fromisoformat(e["timestamp"]) >= cutoff
        ]

    if search:
        entries = [
            e for e in entries
            if search.lower() in e.get("error", "").lower()
            or search.lower() in e.get("explanation", "").lower()
        ]

    if not entries:
        console.print("[yellow]No matching history entries.[/yellow]")
        sys.exit(0)

    for entry in entries:
        label = f"  {entry['timestamp'][:19]}  |  {entry['model']}{'  |  brief' if entry.get('brief') else ''}"
        console.rule(label, style="dim")
        console.print(f"[bold red]Error:[/bold red] {entry['error'][:80]}{'...' if len(entry['error']) > 80 else ''}\n")
        console.print(Markdown(entry["explanation"]))
        console.print()


def extract_error_type(error_text: str) -> str:
    """Best-effort extraction of an error type label from raw error text."""
    # Python-style: TypeError, ImportError, etc.
    m = re.search(r'\b([A-Z][a-zA-Z]*(?:Error|Exception|Warning|Fault|Panic))\b', error_text)
    if m:
        return m.group(1)
    # Go panic
    if re.search(r'\bpanic\b', error_text, re.I):
        return "panic"
    # HTTP status codes
    m = re.search(r'\b(4\d{2}|5\d{2})\b', error_text)
    if m:
        return f"HTTP {m.group(1)}"
    # Segfault / signal
    m = re.search(r'\b(SIGSEGV|SIGABRT|SIGFPE|segfault|segmentation fault)\b', error_text, re.I)
    if m:
        return "segfault"
    # SQL
    if re.search(r'\bsql\b|\bquery\b|\bcolumn\b|\btable\b', error_text, re.I):
        return "SQL error"
    return "unknown"


def ask_about_last(question: str, model: str, show_tokens: bool, copy: bool) -> None:
    """Ask a follow-up question about the last error in history."""
    if not HISTORY_FILE.exists():
        console.print("[yellow]No history yet — run errex on an error first.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    last = entries[-1]
    error = last.get("error", "")
    explanation = last.get("explanation", "")
    ts = last.get("timestamp", "")[:19]

    console.print(f"[dim]Context:[/dim] {error[:80]}{'...' if len(error) > 80 else ''}  [dim]({ts})[/dim]\n")

    messages = [
        {"role": "user", "content": f"Please explain this error:\n\n```\n{error}\n```"},
        {"role": "assistant", "content": explanation},
        {"role": "user", "content": question},
    ]

    console.rule("[bold cyan]errex — Follow-up[/bold cyan]")
    print()

    response, in_tok, out_tok = call_claude(error, model=model, messages=messages)

    print()
    if show_tokens:
        show_token_usage(in_tok, out_tok)
    console.rule(style="dim")
    print()

    save_history(error, response, model, False)
    if copy:
        copy_to_clipboard(response)


def explain_diff(diff_text: str, model: str, lang: str | None, copy: bool, show_tokens: bool) -> None:
    """Explain what a git diff changes and what could break."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    lang_hint = f" (primary language: {lang})" if lang else ""
    prompt = f"Please explain this diff{lang_hint}:\n\n```diff\n{diff_text}\n```"

    console.rule("[bold cyan]errex — Diff Explanation[/bold cyan]")
    print()

    client = anthropic.Anthropic(timeout=API_TIMEOUT)
    collected = []
    input_tokens = output_tokens = 0
    try:
        with client.messages.stream(
            model=model,
            max_tokens=2048,
            system=[{"type": "text", "text": DIFF_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                collected.append(text)
            final = stream.get_final_message()
            input_tokens = final.usage.input_tokens
            output_tokens = final.usage.output_tokens
    except anthropic.APIError as e:
        err_console.print(f"\n[red]errex: API error — {e}[/red]")
        sys.exit(2)

    response = "".join(collected)
    print()
    if show_tokens:
        show_token_usage(input_tokens, output_tokens)
    console.rule(style="dim")
    print()

    save_history(diff_text[:200], response, model, False)
    if copy:
        copy_to_clipboard(response)


def find_similar(error_text: str, top_n: int = 5) -> None:
    """Search history for past errors similar to the current one."""
    if not HISTORY_FILE.exists():
        console.print("[yellow]No history yet.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    current_fp = _error_fingerprint(error_text)
    current_words = set(current_fp.lower().split())

    def jaccard(entry: dict) -> float:
        fp = _error_fingerprint(entry.get("error", ""))
        words = set(fp.lower().split())
        if not current_words or not words:
            return 0.0
        return len(current_words & words) / len(current_words | words)

    scored = sorted(((jaccard(e), e) for e in entries), reverse=True, key=lambda x: x[0])
    top = [(s, e) for s, e in scored if s > 0.0][:top_n]

    if not top:
        console.print("[yellow]No similar errors found in history.[/yellow]")
        return

    console.rule("[bold cyan]errex — Similar Past Errors[/bold cyan]")
    console.print(f"[dim]Matched {len(top)} result(s) from history[/dim]\n")
    for score, entry in top:
        label = f"  {entry['timestamp'][:19]}  ·  {entry['model']}  ·  {score:.0%} match"
        console.rule(label, style="dim")
        console.print(f"[bold red]Error:[/bold red] {entry['error'][:80]}{'...' if len(entry['error']) > 80 else ''}\n")
        console.print(Markdown(entry["explanation"]))
        console.print()


def clear_history(before_days: int | None) -> None:
    """Delete all or old history entries with a confirmation prompt."""
    if not HISTORY_FILE.exists():
        console.print("[yellow]No history to clear.[/yellow]")
        return

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        console.print("[yellow]History is already empty.[/yellow]")
        return

    if before_days is not None:
        cutoff = datetime.now().timestamp() - before_days * 86400
        to_keep, to_delete = [], []
        for e in entries:
            try:
                ts = datetime.fromisoformat(e["timestamp"]).timestamp()
                (to_delete if ts < cutoff else to_keep).append(e)
            except (KeyError, ValueError):
                to_keep.append(e)

        if not to_delete:
            console.print(f"[yellow]No entries older than {before_days} days.[/yellow]")
            return

        s = "y" if len(to_delete) == 1 else "ies"
        console.print(f"This will delete [bold]{len(to_delete)}[/bold] entr{s} older than {before_days} days. [dim]({len(to_keep)} will remain)[/dim]")
        try:
            ans = input("Proceed? [y/N]: ").strip().lower()
        except KeyboardInterrupt:
            console.print("\n[dim]Cancelled.[/dim]")
            return
        if ans != "y":
            console.print("[dim]Cancelled.[/dim]")
            return
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            for e in to_keep:
                f.write(json.dumps(e) + "\n")
        console.print(f"[green]Deleted {len(to_delete)} old entr{s}.[/green]")
    else:
        s = "y" if len(entries) == 1 else "ies"
        console.print(f"This will permanently delete [bold]all {len(entries)}[/bold] history entr{s}.")
        try:
            ans = input("Proceed? [y/N]: ").strip().lower()
        except KeyboardInterrupt:
            console.print("\n[dim]Cancelled.[/dim]")
            return
        if ans != "y":
            console.print("[dim]Cancelled.[/dim]")
            return
        HISTORY_FILE.unlink()
        console.print(f"[green]Cleared {len(entries)} history entr{s}.[/green]")


def export_history(output_path: str, fmt: str) -> None:
    """Export history to an HTML or Markdown file."""
    if not HISTORY_FILE.exists():
        console.print("[yellow]No history to export.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    if fmt == "html":
        lines = ["""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>errex history</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
  body { font-family: -apple-system, sans-serif; max-width: 860px; margin: 2rem auto; padding: 0 1rem; background: #0f1117; color: #e2e8f0; }
  h1 { color: #7dd3fc; } .entry { border: 1px solid #2d3748; border-radius: 8px; padding: 1.25rem; margin: 1.5rem 0; }
  .meta { color: #64748b; font-size: 0.85rem; margin-bottom: 0.75rem; }
  .error-block { background: #1e2130; border-radius: 6px; padding: 0.75rem; font-family: monospace; font-size: 0.85rem; color: #f87171; white-space: pre-wrap; margin-bottom: 1rem; }
  .explanation { line-height: 1.7; } h2,h3 { color: #7dd3fc; } code { background: #1e2130; padding: 0.1em 0.4em; border-radius: 4px; color: #86efac; }
  pre { background: #1e2130; padding: 1rem; border-radius: 6px; overflow-x: auto; }
</style>
</head><body>
<h1>errex — Export</h1>"""]
        for e in entries:
            ts = e.get("timestamp", "")[:19]
            model = e.get("model", "")
            brief = " · brief" if e.get("brief") else ""
            error = e.get("error", "")
            explanation = e.get("explanation", "")
            lines.append(f"""<div class="entry">
  <div class="meta">{ts} · {model}{brief}</div>
  <div class="error-block">{error}</div>
  <div class="explanation" data-md="{explanation.replace('"', '&quot;')}"></div>
</div>""")
        lines.append("""<script>
  document.querySelectorAll('[data-md]').forEach(el => {
    el.innerHTML = marked.parse(el.dataset.md);
  });
</script></body></html>""")
        content = "\n".join(lines)

    else:  # markdown
        md_parts = ["# errex History\n"]
        for e in entries:
            ts = e.get("timestamp", "")[:19]
            model = e.get("model", "")
            brief = " · brief" if e.get("brief") else ""
            error = e.get("error", "")
            explanation = e.get("explanation", "")
            md_parts.append(f"---\n\n**{ts}** · {model}{brief}\n\n**Error:**\n```\n{error}\n```\n\n{explanation}\n")
        content = "\n".join(md_parts)

    out = Path(output_path)
    out.write_text(content, encoding="utf-8")
    console.print(f"[green]Exported {len(entries)} entries to[/green] [cyan]{out.resolve()}[/cyan]")


def show_stats() -> None:
    """Print usage statistics from ~/.errex_history."""
    if not HISTORY_FILE.exists():
        console.print("[yellow]No history yet — run errex on some errors first.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        console.print("[yellow]History file is empty.[/yellow]")
        sys.exit(0)

    total = len(entries)
    brief_count = sum(1 for e in entries if e.get("brief"))
    models = Counter(e.get("model", "unknown") for e in entries)
    error_types = Counter(extract_error_type(e.get("error", "")) for e in entries)
    days = Counter(e["timestamp"][:10] for e in entries if "timestamp" in e)
    hours = Counter(int(e["timestamp"][11:13]) for e in entries if "timestamp" in e)
    ratings = [e["rating"] for e in entries if "rating" in e]

    busiest_day = max(days, key=days.get) if days else "—"
    busiest_hour = max(hours, key=hours.get) if hours else 0
    first_used = min(e["timestamp"][:10] for e in entries if "timestamp" in e)
    avg_rating = f"{sum(ratings)/len(ratings):.1f}/5 ({len(ratings)} rated)" if ratings else "none yet"

    console.rule("[bold cyan]errex — Usage Stats[/bold cyan]")
    console.print()

    # Summary panel
    summary = (
        f"[bold]{total}[/bold] total explanations\n"
        f"[bold]{brief_count}[/bold] brief  /  [bold]{total - brief_count}[/bold] full\n"
        f"Avg rating: [dim]{avg_rating}[/dim]\n"
        f"First used: [dim]{first_used}[/dim]\n"
        f"Busiest day: [dim]{busiest_day} ({days.get(busiest_day, 0)} runs)[/dim]\n"
        f"Busiest hour: [dim]{busiest_hour:02d}:00–{busiest_hour:02d}:59[/dim]"
    )
    console.print(Panel(summary, title="Overview", border_style="cyan"))
    console.print()

    # Models table
    model_table = Table(title="Models used", show_header=True, header_style="bold magenta")
    model_table.add_column("Model", style="cyan")
    model_table.add_column("Count", justify="right")
    model_table.add_column("Share", justify="right")
    for model, count in models.most_common():
        model_table.add_row(model, str(count), f"{count/total*100:.0f}%")

    # Error types table
    type_table = Table(title="Top error types", show_header=True, header_style="bold magenta")
    type_table.add_column("Error type", style="red")
    type_table.add_column("Count", justify="right")
    for etype, count in error_types.most_common(8):
        type_table.add_row(etype, str(count))

    console.print(Columns([model_table, type_table], equal=False, expand=False))
    console.print()


def detect_environment() -> dict:
    """Detect installed languages and tools, return suggested config values."""
    tools = {
        "python": ["python3", "python"],
        "node": ["node"],
        "go": ["go"],
        "rust": ["rustc"],
        "ruby": ["ruby"],
        "java": ["java"],
        "php": ["php"],
    }
    found = []
    for lang, cmds in tools.items():
        for cmd in cmds:
            result = subprocess.run(["which", cmd], capture_output=True, text=True)
            if result.returncode == 0:
                found.append(lang)
                break

    # Pick the most prominent lang as default hint
    lang_default = found[0] if len(found) == 1 else None
    return {"detected": found, "lang_default": lang_default}


def scan_logs() -> None:
    """Scan common locations for recent log files containing errors, offer a picker."""
    search_dirs = [
        Path.home() / ".npm" / "_logs",
        Path.home() / "Library" / "Logs",
        Path.home() / "Library" / "Application Support",
        Path("/var/log"),
        Path("/tmp"),
        Path.cwd(),
    ]

    error_keywords = re.compile(
        r'\b(error|exception|traceback|fatal|panic|fail|critical|stderr)\b',
        re.IGNORECASE,
    )

    console.print("[bold]Scanning for recent error logs…[/bold]\n")
    candidates: list[tuple[float, Path]] = []

    for base in search_dirs:
        if not base.exists():
            continue
        try:
            for p in base.rglob("*.log"):
                try:
                    stat = p.stat()
                    if stat.st_size == 0 or stat.st_size > 10 * 1024 * 1024:
                        continue
                    # Quick scan: check if file contains error-like lines
                    with open(p, encoding="utf-8", errors="ignore") as f:
                        sample = f.read(4096)
                    if error_keywords.search(sample):
                        candidates.append((stat.st_mtime, p))
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            continue

    if not candidates:
        console.print("[yellow]No error logs found in common locations.[/yellow]")
        console.print("[dim]Try: errex --watch /path/to/your.log[/dim]")
        return

    # Sort by most recent, take top 10
    candidates.sort(reverse=True)
    top = candidates[:10]

    from rich.table import Table as RichTable
    table = RichTable(show_header=True, header_style="bold cyan", box=None)
    table.add_column("#", style="dim", width=3)
    table.add_column("File", style="cyan")
    table.add_column("Modified", style="dim", width=20)
    table.add_column("Size", justify="right", style="dim", width=8)

    for i, (mtime, p) in enumerate(top, 1):
        modified = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        size = p.stat().st_size
        size_str = f"{size // 1024}KB" if size >= 1024 else f"{size}B"
        table.add_row(str(i), str(p), modified, size_str)

    console.print(table)
    console.print()

    try:
        choice = input("Pick a file to explain (1–{}, or q to quit): ".format(len(top))).strip()
        if choice.lower() == "q" or not choice:
            return
        idx = int(choice) - 1
        if not 0 <= idx < len(top):
            console.print("[red]Invalid choice.[/red]")
            return
        chosen = top[idx][1]
        console.print(f"\n[dim]Reading {chosen}…[/dim]\n")
        error_text = chosen.read_text(encoding="utf-8", errors="replace").strip()
        if len(error_text) > 8000:
            error_text = error_text[-8000:]  # use the tail where errors usually are
        explain_error(error_text, model=load_config()["model"])
    except (ValueError, KeyboardInterrupt):
        console.print("\n[dim]Cancelled.[/dim]")


def run_setup() -> None:
    """Interactive first-run wizard: check API key, detect env, write ~/.errexrc."""
    console.rule("[bold cyan]errex — Setup Wizard[/bold cyan]")
    console.print()

    # 1. API key
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        console.print(f"[green]✓[/green] ANTHROPIC_API_KEY is set ({api_key[:8]}…)")
    else:
        console.print("[red]✗[/red] ANTHROPIC_API_KEY is not set.")
        console.print("  Get one at [cyan]https://console.anthropic.com/[/cyan]")
        console.print("  Then add to your shell config:")
        console.print('  [dim]export ANTHROPIC_API_KEY=sk-ant-...[/dim]\n')

    # 2. Detect environment
    console.print("\n[bold]Detecting your environment…[/bold]")
    env = detect_environment()
    if env["detected"]:
        console.print(f"[green]✓[/green] Found: {', '.join(env['detected'])}")
    else:
        console.print("[dim]No common runtimes detected.[/dim]")

    # 3. Build config
    existing = load_config()
    config: dict = {}

    if env["lang_default"] and not existing.get("lang"):
        config["lang"] = env["lang_default"]
        console.print(f"  → Setting default language: [cyan]{env['lang_default']}[/cyan]")

    # Suggest opus if only one language (power user), sonnet otherwise
    if not existing.get("model") or existing.get("model") == "claude-sonnet-4-6":
        config["model"] = "claude-sonnet-4-6"

    # 4. Write config
    if config:
        merged = {**existing, **config}
        with open(CONFIG_FILE, "w") as f:
            json.dump(merged, f, indent=2)
        console.print(f"\n[green]✓[/green] Wrote config to [cyan]{CONFIG_FILE}[/cyan]")
    else:
        console.print("\n[dim]Config unchanged.[/dim]")

    # 5. Shell integration
    console.print()
    shell = os.environ.get("SHELL", "")
    rc_file = Path.home() / (".zshrc" if "zsh" in shell else ".bashrc")
    shell_already = rc_file.exists() and "errex-last" in rc_file.read_text()
    if shell_already:
        console.print(f"[green]✓[/green] Shell integration already in {rc_file}")
    else:
        try:
            ans = input("Install errex-last() shell function? [Y/n]: ").strip().lower()
        except KeyboardInterrupt:
            ans = "n"
        if ans in ("", "y"):
            install_shell()

    console.print()
    console.rule("[dim]Setup complete[/dim]")
    console.print("\nRun [cyan]errex --scan[/cyan] to find error logs, or just pipe any error:\n  [dim]cat error.log | errex[/dim]\n")


def install_shell() -> None:
    shell = os.environ.get("SHELL", "")
    rc_file = Path.home() / (".zshrc" if "zsh" in shell else ".bashrc")
    with open(rc_file, "a") as f:
        f.write(SHELL_FUNCTION)
    console.print(f"[green]Added errex-last() to {rc_file}[/green]")
    console.print(f"[dim]Restart your shell or run: source {rc_file}[/dim]")
    console.print("[dim]Then use: errex-last  (after any failed command)[/dim]")


def search_github_issues(error_text: str) -> None:
    """Search GitHub for issues similar to this error and print the top results."""
    # Extract a concise search query from the first meaningful error line
    lines = [l.strip() for l in error_text.splitlines() if l.strip()]
    # Prefer lines that look like error messages
    query_line = next(
        (l for l in lines if re.search(r'\b(Error|Exception|panic|fatal|fail)\b', l, re.I)),
        lines[0] if lines else error_text[:100],
    )
    # Trim to a reasonable search length and strip file paths/line numbers
    query = re.sub(r'File ".*?", line \d+,?\s*', '', query_line)
    query = query[:120].strip()

    console.print(f"\n[bold]Searching GitHub Issues for:[/bold] [dim]{query}[/dim]\n")

    try:
        encoded = urllib.parse.quote(query)
        url = f"https://api.github.com/search/issues?q={encoded}+is:issue&sort=relevance&per_page=5"
        req = urllib.request.Request(url, headers={"User-Agent": "errex", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        console.print(f"[yellow]Could not search GitHub: {e}[/yellow]")
        return

    items = data.get("items", [])
    if not items:
        console.print("[dim]No matching GitHub issues found.[/dim]")
        return

    from rich.table import Table as RTable
    table = RTable(show_header=True, header_style="bold magenta", box=None, show_edge=False)
    table.add_column("", style="dim", width=2)
    table.add_column("Title", style="cyan", max_width=55)
    table.add_column("Repo", style="dim", max_width=30)
    table.add_column("State", width=6)
    table.add_column("👍", justify="right", width=4)

    for i, item in enumerate(items, 1):
        repo = item["repository_url"].replace("https://api.github.com/repos/", "")
        state_color = "green" if item["state"] == "open" else "red"
        table.add_row(
            str(i),
            item["title"][:55],
            repo,
            f"[{state_color}]{item['state']}[/{state_color}]",
            str(item.get("reactions", {}).get("+1", 0)),
        )

    console.print(table)
    console.print()
    for i, item in enumerate(items, 1):
        console.print(f"  [dim]{i}.[/dim] [cyan]{item['html_url']}[/cyan]")
    console.print()


def notify(title: str, message: str) -> None:
    """Send a macOS desktop notification (no-op on other platforms)."""
    if platform.system() != "Darwin":
        return
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{message[:100]}" with title "{title}"'],
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        pass


def check_for_update() -> None:
    """Check PyPI for a newer version and print a notice if one exists."""
    try:
        current = importlib.metadata.version("errex")
    except importlib.metadata.PackageNotFoundError:
        return
    try:
        req = urllib.request.Request(
            "https://pypi.org/pypi/errex/json",
            headers={"User-Agent": f"errex/{current}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            latest = json.loads(resp.read())["info"]["version"]
        if latest != current:
            console.print(
                f"\n[yellow]Update available:[/yellow] {current} → [bold]{latest}[/bold]  "
                f"[dim]pip install --upgrade errex[/dim]\n"
            )
    except Exception:
        pass


def get_env_info() -> str:
    """Collect cross-platform system info to attach as error context."""
    info = []
    info.append(f"OS: {platform.system()} {platform.release()} ({platform.machine()})")
    info.append(f"Python: {sys.version.split()[0]}")

    if platform.system() == "Windows":
        psmod = os.environ.get("PSModulePath", "")
        if psmod:
            shell = "PowerShell"
        else:
            comspec = os.environ.get("COMSPEC", "cmd.exe")
            shell = Path(comspec).name
    else:
        shell = os.environ.get("SHELL", "unknown")
    info.append(f"Shell: {shell}")

    for cmd, flag in [
        ("node", "--version"),
        ("go", "version"),
        ("rustc", "--version"),
        ("java", "-version"),
        ("ruby", "--version"),
        ("php", "--version"),
    ]:
        try:
            result = subprocess.run(
                [cmd, flag], capture_output=True, text=True, timeout=3,
            )
            line = (result.stdout or result.stderr).strip().split("\n")[0]
            if line:
                info.append(f"{cmd}: {line}")
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

    return "\n".join(info)


def explain_regex(pattern: str, model: str, copy: bool, show_tokens: bool) -> None:
    """Explain a regular expression in plain English."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    prompt = f"Explain this regular expression:\n\n```\n{pattern}\n```"

    console.rule("[bold cyan]errex — Regex Explanation[/bold cyan]")
    print()

    client = anthropic.Anthropic(timeout=API_TIMEOUT)
    collected = []
    input_tokens = output_tokens = 0
    try:
        with client.messages.stream(
            model=model,
            max_tokens=1024,
            system=[{"type": "text", "text": REGEX_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                collected.append(text)
            final = stream.get_final_message()
            input_tokens = final.usage.input_tokens
            output_tokens = final.usage.output_tokens
    except anthropic.APIError as e:
        err_console.print(f"\n[red]errex: API error — {e}[/red]")
        sys.exit(2)

    response = "".join(collected)
    print()
    if show_tokens:
        show_token_usage(input_tokens, output_tokens)
    console.rule(style="dim")
    print()

    save_history(pattern, response, model, False)
    if copy:
        copy_to_clipboard(response)


def explain_exit_code(code: int, model: str, copy: bool) -> None:
    """Explain a shell exit code — known codes answered locally, unknowns via Claude."""
    console.rule(f"[bold cyan]errex — Exit Code {code}[/bold cyan]")
    console.print()

    if code in EXIT_CODES:
        name, explanation = EXIT_CODES[code]
        console.print(f"[bold red]Exit {code}:[/bold red]  [bold]{name}[/bold]\n")
        console.print(explanation)
        console.print()
        console.rule(style="dim")
        if copy:
            copy_to_clipboard(f"Exit {code}: {name}\n{explanation}")
        return

    if 128 < code <= 165:
        sig_num = code - 128
        sig_name = _SIGNAL_NAMES.get(sig_num, f"signal {sig_num}")
        msg = (
            f"The process was killed by **{sig_name}** (signal {sig_num}).\n\n"
            f"Exit code {code} = 128 + {sig_num} (the signal number)."
        )
        console.print(f"[bold red]Exit {code}:[/bold red]  [bold]Killed by {sig_name}[/bold]\n")
        console.print(Markdown(msg))
        console.print()
        console.rule(style="dim")
        if copy:
            copy_to_clipboard(f"Exit {code}: Killed by {sig_name}\n{msg}")
        return

    # Unknown — fall through to Claude
    console.print(f"[dim]Unknown exit code — asking Claude…[/dim]\n")
    prompt = (
        f"Explain shell exit code {code}. Cover: what it typically means, "
        f"which tools or runtimes commonly return it, and how to diagnose or fix the root cause. "
        f"Be concise and use markdown."
    )
    _, in_tok, out_tok = call_claude(
        str(code), model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    print()
    console.rule(style="dim")
    if copy:
        copy_to_clipboard(prompt)


def post_webhook(url: str, error_text: str, explanation: str, model: str) -> None:
    """POST the explanation to a webhook URL (Slack, Discord, or generic JSON)."""
    timestamp = datetime.now().isoformat()

    if "hooks.slack.com" in url or ("slack.com" in url and "services" in url):
        text = f"*errex — Error Explanation*\n\n*Error:*\n```{error_text[:300]}```\n\n{explanation[:2000]}"
        payload: dict = {"text": text}
    elif "discord.com/api/webhooks" in url or "discordapp.com" in url:
        content = f"**errex — Error Explanation**\n**Error:** `{error_text[:100]}`\n\n{explanation[:1900]}"
        payload = {"content": content}
    else:
        payload = {
            "error": error_text,
            "explanation": explanation,
            "model": model,
            "timestamp": timestamp,
        }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "errex"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
        console.print(f"\n[green]Webhook posted[/green] [dim](HTTP {status} → {url})[/dim]")
    except urllib.error.URLError as e:
        err_console.print(f"[yellow]errex: webhook failed — {e}[/yellow]")


def find_by_name(name: str) -> None:
    """Find history entries saved with --save-as NAME."""
    if not HISTORY_FILE.exists():
        console.print("[yellow]No history yet.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    matches = [e for e in entries if e.get("name", "").lower() == name.lower()]

    if not matches:
        console.print(f"[yellow]No entries found with name '{name}'.[/yellow]")
        console.print("[dim]Tip: save an explanation with: errex --save-as NAME[/dim]")
        sys.exit(0)

    console.rule(f"[bold cyan]errex — Saved: {name}[/bold cyan]")
    console.print(f"[dim]{len(matches)} entry{'s' if len(matches) != 1 else ''} found[/dim]\n")
    for entry in matches:
        label = f"  {entry['timestamp'][:19]}  ·  {entry['model']}"
        console.rule(label, style="dim")
        console.print(f"[bold red]Error:[/bold red] {entry['error'][:80]}{'...' if len(entry['error']) > 80 else ''}\n")
        console.print(Markdown(entry["explanation"]))
        console.print()


def show_token_usage(input_tokens: int, output_tokens: int) -> None:
    total = input_tokens + output_tokens
    console.print(
        f"[dim]tokens: {input_tokens:,} in · {output_tokens:,} out · {total:,} total[/dim]"
    )


def call_claude(
    error_text: str,
    model: str,
    brief: bool = False,
    terse: bool = False,
    json_output: bool = False,
    fix: bool = False,
    lang: str | None = None,
    context: str | None = None,
    messages: list | None = None,
    translate: str | None = None,
    dry_run: bool = False,
) -> tuple[str, int, int]:
    """Send error to Claude, stream to stdout, return (response, input_tokens, output_tokens)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    client = anthropic.Anthropic(timeout=API_TIMEOUT)
    lang_hint = f" (language: {lang})" if lang else ""
    context_block = f"\n\nFor context, here is the relevant code:\n```\n{context}\n```" if context else ""
    translate_suffix = f"\n\nRespond entirely in {translate}." if translate else ""

    if messages is None:
        if fix:
            prompt = f"Given this error{lang_hint}, output ONLY the exact shell command(s) to fix it as a code block. No explanation.\n\n```\n{error_text}\n```{context_block}{translate_suffix}"
        elif json_output:
            prompt = (
                f"Explain this error{lang_hint} as JSON with keys: error_type, language, "
                f"explanation, root_cause, fix_steps (array), gotchas (array). "
                f"Return only valid JSON, no markdown fences.\n\n```\n{error_text}\n```{context_block}"
            )
        elif terse:
            prompt = f"In exactly one sentence, state what this error{lang_hint} is and the single most likely fix. No preamble.\n\n```\n{error_text}\n```{context_block}{translate_suffix}"
        elif brief:
            prompt = f"In one short paragraph, tell me: what this error{lang_hint} is, the most likely cause, and how to fix it.\n\n```\n{error_text}\n```{context_block}{translate_suffix}"
        else:
            prompt = f"Please explain this error{lang_hint}:\n\n```\n{error_text}\n```{context_block}{translate_suffix}"
        messages = [{"role": "user", "content": prompt}]

    if dry_run:
        console.rule("[bold yellow]errex — Debug (dry run)[/bold yellow]")
        console.print(f"\n[bold]Model:[/bold] {model}  [bold]Max tokens:[/bold] {64 if terse else (256 if brief else 2048)}\n")
        console.rule("[dim]System prompt[/dim]")
        console.print(SYSTEM_PROMPT)
        console.rule("[dim]User prompt[/dim]")
        console.print(messages[-1]["content"])
        console.rule(style="dim")
        return "", 0, 0

    collected = []
    input_tokens = output_tokens = 0
    try:
        with client.messages.stream(
            model=model,
            max_tokens=64 if terse else (256 if brief else 2048),
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                if not json_output:
                    print(text, end="", flush=True)
                collected.append(text)
            final = stream.get_final_message()
            input_tokens = final.usage.input_tokens
            output_tokens = final.usage.output_tokens
    except anthropic.APIError as e:
        err_console.print(f"\n[red]errex: API error — {e}[/red]")
        sys.exit(2)

    return "".join(collected), input_tokens, output_tokens


def chat_loop(error_text: str, initial_response: str, model: str, lang: str | None) -> None:
    """After the initial explanation, let the user ask follow-up questions."""
    lang_hint = f" (language: {lang})" if lang else ""
    history = [
        {"role": "user", "content": f"Please explain this error{lang_hint}:\n\n```\n{error_text}\n```"},
        {"role": "assistant", "content": initial_response},
    ]
    console.print("[dim]Ask a follow-up question, or press Ctrl+C to exit.[/dim]\n")
    while True:
        try:
            question = input("You: ").strip()
            if not question:
                continue
            history.append({"role": "user", "content": question})
            print()
            console.rule("[dim]errex[/dim]")
            print()
            response, in_tok, out_tok = call_claude(
                error_text, model=model, lang=lang, messages=history
            )
            history.append({"role": "assistant", "content": response})
            print()
            show_token_usage(in_tok, out_tok)
            console.rule(style="dim")
            print()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Exiting chat.[/dim]")
            break


def explain_error(
    error_text: str,
    model: str,
    brief: bool = False,
    terse: bool = False,
    json_output: bool = False,
    fix: bool = False,
    lang: str | None = None,
    copy: bool = False,
    share: bool = False,
    show_tokens: bool = False,
    chat: bool = False,
    context: str | None = None,
    do_notify: bool = False,
    issues: bool = False,
    translate: str | None = None,
    save_as: str | None = None,
    output_file: str | None = None,
    webhook: str | None = None,
    dry_run: bool = False,
) -> None:
    """Explain an error, render output, save history."""
    if not json_output and not dry_run:
        console.rule("[bold cyan]errex — Error Analysis[/bold cyan]")
        print()

    response, in_tok, out_tok = call_claude(
        error_text, model=model, brief=brief, terse=terse, json_output=json_output,
        fix=fix, lang=lang, context=context, translate=translate, dry_run=dry_run,
    )

    if dry_run:
        return

    if json_output:
        try:
            parsed = json.loads(response)
            print(json.dumps(parsed, indent=2))
        except json.JSONDecodeError:
            print(response)
    else:
        print()
        if show_tokens:
            show_token_usage(in_tok, out_tok)
        console.rule(style="dim")
        print()

    save_history(error_text, response, model, brief, name=save_as)

    if output_file:
        out = Path(output_file)
        out.write_text(response, encoding="utf-8")
        err_console.print(f"[dim](saved to {out.resolve()})[/dim]")

    if copy:
        copy_to_clipboard(response)

    if share:
        share_explanation(error_text, response)

    if do_notify:
        notify("errex", f"Error explained: {error_text[:60]}")

    if issues:
        search_github_issues(error_text)

    if webhook:
        post_webhook(webhook, error_text, response, model)

    if chat and sys.stdin.isatty():
        chat_loop(error_text, response, model, lang)


def compare_errors(files: list[str], model: str, lang: str | None, copy: bool) -> None:
    """Explain multiple errors and analyse whether they share a root cause."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    errors = []
    for path in files:
        errors.append((path, read_file(path)))

    lang_hint = f" (language: {lang})" if lang else ""
    blocks = "\n\n".join(
        f"### Error {i+1}: {path}\n```\n{text}\n```"
        for i, (path, text) in enumerate(errors)
    )
    prompt = (
        f"I have {len(errors)} errors{lang_hint}. For each one:\n"
        f"1. Identify the error type and explain it briefly.\n\n"
        f"Then, after explaining all of them:\n"
        f"2. Are these errors related or do they share a root cause? Explain.\n"
        f"3. Give a unified fix plan if they're connected, or separate fixes if not.\n\n"
        f"{blocks}"
    )

    console.rule(f"[bold cyan]errex — Comparing {len(errors)} errors[/bold cyan]")
    print()

    client = anthropic.Anthropic(timeout=API_TIMEOUT)
    collected = []
    try:
        with client.messages.stream(
            model=model,
            max_tokens=3000,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                collected.append(text)
    except anthropic.APIError as e:
        err_console.print(f"\n[red]errex: API error — {e}[/red]")
        sys.exit(2)

    print()
    console.rule(style="dim")
    print()

    full_response = "".join(collected)
    combined_error = " | ".join(f"{p}: {t[:100]}" for p, t in errors)
    save_history(combined_error, full_response, model, False)

    if copy:
        copy_to_clipboard(full_response)


def _error_fingerprint(text: str) -> str:
    """Produce a short dedup key from error text — strips line numbers and addresses."""
    # Remove memory addresses, line numbers, timestamps, UUIDs
    cleaned = re.sub(r'0x[0-9a-fA-F]+', '0xADDR', text)
    cleaned = re.sub(r'\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}[.\d]*\b', '', cleaned)
    cleaned = re.sub(r'\bline \d+\b', 'line N', cleaned, flags=re.I)
    cleaned = re.sub(r':[0-9]+\b', ':N', cleaned)
    cleaned = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', 'UUID', cleaned, flags=re.I)
    # Collapse whitespace and take first 200 chars as fingerprint
    return re.sub(r'\s+', ' ', cleaned).strip()[:200]


def watch_file(path: str, model: str, brief: bool, lang: str | None) -> None:
    """Tail a log file and explain errors as they appear, deduplicating repeats."""
    if not os.path.exists(path):
        err_console.print(f"[red]errex: file not found: {path}[/red]")
        sys.exit(1)

    console.print(f"[bold]Watching[/bold] [cyan]{path}[/cyan] [dim](Ctrl+C to stop | duplicates suppressed)[/dim]")

    seen_fingerprints: set[str] = set()
    COOLDOWN = 30.0  # seconds before re-explaining a similar error

    with open(path, encoding="utf-8", errors="replace") as f:
        f.seek(0, 2)
        buffer: list[str] = []
        has_error = False
        last_activity: float | None = None
        fingerprint_times: dict[str, float] = {}

        try:
            while True:
                line = f.readline()
                if line:
                    buffer.append(line)
                    last_activity = time.time()
                    if any(p in line.lower() for p in ERROR_PATTERNS):
                        has_error = True
                elif has_error and last_activity and time.time() - last_activity > 2.0:
                    text = "".join(buffer).strip()
                    fp = _error_fingerprint(text)
                    now = time.time()
                    last_seen = fingerprint_times.get(fp, 0)

                    if now - last_seen < COOLDOWN:
                        console.print(f"\n[dim]Duplicate error suppressed (seen {int(now - last_seen)}s ago)[/dim]")
                    else:
                        fingerprint_times[fp] = now
                        console.print("\n[bold yellow]New error detected[/bold yellow]")
                        notify("errex — error detected", path)
                        explain_error(text, model=model, brief=brief, lang=lang, do_notify=False)

                    buffer = []
                    has_error = False
                    last_activity = None
                else:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            console.print("\n[dim]Stopped watching.[/dim]")


def show_recent(n: int, since: str | None = None) -> None:
    """Show the N most recent history entries."""
    if not HISTORY_FILE.exists():
        console.print("[yellow]No history yet.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    if since:
        cutoff = _parse_since(since)
        entries = [e for e in entries if datetime.fromisoformat(e["timestamp"]) >= cutoff]

    recent = entries[-n:]
    label = f"Last {len(recent)} explanation{'s' if len(recent) != 1 else ''}"
    console.rule(f"[bold cyan]errex — {label}[/bold cyan]")
    console.print()

    for entry in recent:
        meta = f"  {entry['timestamp'][:19]}  ·  {entry['model']}{'  ·  brief' if entry.get('brief') else ''}"
        console.rule(meta, style="dim")
        console.print(f"[bold red]Error:[/bold red] {entry['error'][:80]}{'...' if len(entry['error']) > 80 else ''}\n")
        console.print(Markdown(entry["explanation"]))
        console.print()


def summarize_log(path: str, model: str, copy: bool, show_tokens: bool) -> None:
    """Produce a digest of all distinct errors in a log file."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    content = read_file(path)
    if len(content) > 8000:
        content = content[-8000:]
        console.print("[dim](log is large — using the last 8000 chars where errors typically appear)[/dim]")

    prompt = f"Analyze this log file and produce a diagnostic digest:\n\n```\n{content}\n```"

    console.rule(f"[bold cyan]errex — Log Summary: {Path(path).name}[/bold cyan]")
    print()

    client = anthropic.Anthropic(timeout=API_TIMEOUT)
    collected = []
    input_tokens = output_tokens = 0
    try:
        with client.messages.stream(
            model=model,
            max_tokens=1024,
            system=[{"type": "text", "text": LOG_SUMMARY_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                collected.append(text)
            final = stream.get_final_message()
            input_tokens = final.usage.input_tokens
            output_tokens = final.usage.output_tokens
    except anthropic.APIError as e:
        err_console.print(f"\n[red]errex: API error — {e}[/red]")
        sys.exit(2)

    response = "".join(collected)
    print()
    if show_tokens:
        show_token_usage(input_tokens, output_tokens)
    console.rule(style="dim")
    print()

    save_history(content[:200], response, model, False)
    if copy:
        copy_to_clipboard(response)


def retry_last(
    model: str,
    brief: bool,
    fix: bool,
    lang: str | None,
    copy: bool,
    show_tokens: bool,
    chat: bool,
) -> None:
    """Re-explain the last error from history with the given flags."""
    if not HISTORY_FILE.exists():
        console.print("[yellow]No history yet — run errex on an error first.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    last = entries[-1]
    error = last.get("error", "")
    ts = last.get("timestamp", "")[:19]

    console.print(f"[dim]Retrying:[/dim] {error[:80]}{'...' if len(error) > 80 else ''}  [dim]({ts})[/dim]\n")

    explain_error(
        error,
        model=model,
        brief=brief,
        fix=fix,
        lang=lang,
        copy=copy,
        show_tokens=show_tokens,
        chat=chat,
    )


def rate_last(score: int) -> None:
    """Rate the last history entry 1-5 and store the rating."""
    if not 1 <= score <= 5:
        err_console.print("[red]errex: --rate expects a score between 1 and 5[/red]")
        sys.exit(1)

    if not HISTORY_FILE.exists():
        console.print("[yellow]No history to rate.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        lines = [l for l in f.readlines() if l.strip()]

    if not lines:
        console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    last = json.loads(lines[-1])
    last["rating"] = score
    lines[-1] = json.dumps(last) + "\n"

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)

    stars = "★" * score + "☆" * (5 - score)
    err_snippet = last.get("error", "")[:60]
    console.print(f"[green]Rated[/green] {stars} ({score}/5)  [dim]{err_snippet}[/dim]")


def load_profile(name: str, file_config: dict) -> dict:
    """Return config merged with the named profile from ~/.errexrc profiles dict."""
    profiles = file_config.get("profiles", {})
    if name not in profiles:
        err_console.print(f"[red]errex: profile '{name}' not found.[/red]")
        available = list(profiles.keys())
        if available:
            err_console.print(f"[dim]Available profiles: {', '.join(available)}[/dim]")
        else:
            err_console.print("[dim]No profiles saved yet. Create one by adding a \"profiles\" key to ~/.errexrc[/dim]")
        sys.exit(1)
    return {**CONFIG_DEFAULTS, **file_config, **profiles[name]}


def run_bulk(
    path: str,
    model: str,
    brief: bool,
    terse: bool,
    lang: str | None,
    copy: bool,
    show_tokens: bool,
) -> None:
    """Explain multiple errors from a file, separated by blank lines."""
    content = read_file(path)
    blocks = [b.strip() for b in re.split(r"\n{2,}", content) if b.strip()]

    if not blocks:
        console.print(f"[yellow]No error blocks found in {path}.[/yellow]")
        return

    console.print(f"[bold]{len(blocks)} error block{'s' if len(blocks) != 1 else ''}[/bold] found in [cyan]{Path(path).name}[/cyan]\n")

    for i, block in enumerate(blocks, 1):
        console.rule(f"[bold cyan]Block {i} of {len(blocks)}[/bold cyan]")
        print()
        explain_error(
            block,
            model=model,
            brief=brief,
            terse=terse,
            lang=lang,
            copy=copy,
            show_tokens=show_tokens,
        )


def explain_http(code: int, model: str, copy: bool) -> None:
    """Explain an HTTP status code — known codes answered locally, unknowns via Claude."""
    console.rule(f"[bold cyan]errex — HTTP {code}[/bold cyan]")
    console.print()

    if code in HTTP_CODES:
        name, explanation = HTTP_CODES[code]
        category = {1: "Informational", 2: "Success", 3: "Redirection", 4: "Client Error", 5: "Server Error"}.get(code // 100, "Unknown")
        console.print(f"[bold red]HTTP {code}:[/bold red]  [bold]{name}[/bold]  [dim]({category})[/dim]\n")
        console.print(explanation)
        console.print()
        console.rule(style="dim")
        if copy:
            copy_to_clipboard(f"HTTP {code}: {name}\n{explanation}")
        return

    console.print(f"[dim]Non-standard status code — asking Claude…[/dim]\n")
    prompt = (
        f"Explain HTTP status code {code}. Cover: what it means, which servers or frameworks use it, "
        f"common causes, and how to handle or fix it. Be concise and use markdown."
    )
    call_claude(str(code), model=model, messages=[{"role": "user", "content": prompt}])
    print()
    console.rule(style="dim")


def add_note(note: str) -> None:
    """Append a personal note to the last history entry."""
    if not HISTORY_FILE.exists():
        console.print("[yellow]No history yet.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        lines = [l for l in f.readlines() if l.strip()]

    if not lines:
        console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    last = json.loads(lines[-1])
    existing = last.get("notes", "")
    last["notes"] = (existing + "\n" + note).strip() if existing else note
    lines[-1] = json.dumps(last) + "\n"

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)

    err_snippet = last.get("error", "")[:60]
    console.print(f"[green]Note added[/green]  [dim]{err_snippet}[/dim]")
    console.print(f"[dim]Note:[/dim] {note}")


def format_json_error(text: str) -> str:
    """Parse a JSON error blob and reformat it as readable text for Claude."""
    stripped = text.strip()
    if not (stripped.startswith("{") or stripped.startswith("[")):
        return text
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return text

    if isinstance(data, list):
        return json.dumps(data, indent=2)

    if not isinstance(data, dict):
        return str(data)

    lines = []
    priority = ["error", "message", "msg", "reason", "detail", "details",
                "description", "stack", "stackTrace", "stack_trace", "trace",
                "exception", "code", "status", "type", "name", "cause"]
    shown: set[str] = set()

    for key in priority:
        if key in data:
            val = data[key]
            shown.add(key)
            if isinstance(val, str):
                lines.append(f"{key}: {val}")
            elif isinstance(val, (int, float, bool)):
                lines.append(f"{key}: {val}")
            else:
                lines.append(f"{key}:\n{json.dumps(val, indent=2)}")

    for key, val in data.items():
        if key not in shown:
            if isinstance(val, str) and len(val) <= 200:
                lines.append(f"{key}: {val}")
            elif isinstance(val, (int, float, bool)):
                lines.append(f"{key}: {val}")

    return "\n".join(lines) if lines else json.dumps(data, indent=2)


def interactive_history(n: int = 15) -> None:
    """Show a numbered list of recent history entries; pick one to view."""
    if not HISTORY_FILE.exists():
        console.print("[yellow]No history yet.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    recent = entries[-n:]

    console.rule("[bold cyan]errex — Interactive History[/bold cyan]")
    console.print()

    table = Table(show_header=True, header_style="bold magenta", box=None, show_edge=False)
    table.add_column("#", style="dim", width=3)
    table.add_column("Date", style="dim", width=17)
    table.add_column("Model", style="dim", width=22)
    table.add_column("Error", style="red")

    for i, entry in enumerate(recent, 1):
        ts = entry.get("timestamp", "")[:16]
        model = entry.get("model", "")
        error = entry.get("error", "")[:65]
        name_tag = f"[{entry['name']}] " if entry.get("name") else ""
        table.add_row(str(i), ts, model, f"{name_tag}{error}")

    console.print(table)
    console.print()

    try:
        choice = input(f"Pick an entry (1–{len(recent)}, or q to quit): ").strip()
    except (EOFError, KeyboardInterrupt):
        console.print("\n[dim]Cancelled.[/dim]")
        return

    if choice.lower() in ("q", ""):
        return

    try:
        idx = int(choice) - 1
        if not 0 <= idx < len(recent):
            console.print("[red]Invalid choice.[/red]")
            return
    except ValueError:
        console.print("[red]Invalid input.[/red]")
        return

    entry = recent[idx]
    console.print()
    label = f"  {entry['timestamp'][:19]}  ·  {entry['model']}{'  ·  brief' if entry.get('brief') else ''}"
    console.rule(label, style="dim")
    console.print(f"\n[bold red]Error:[/bold red] {entry['error']}\n")
    if entry.get("notes"):
        console.print(f"[dim]Note:[/dim] {entry['notes']}\n")
    console.print(Markdown(entry["explanation"]))
    console.print()


def _cron_local(expr: str) -> str | None:
    """Return a plain-English description of a 5-field cron expression, or None if too complex."""
    fields = expr.strip().split()
    if len(fields) != 5:
        return None
    mn, hr, dm, mo, dw = fields
    if any("-" in f for f in fields):
        return None  # ranges — delegate to Claude

    def _fmt_time(h: str, m: str) -> str | None:
        try:
            hh, mm = int(h), int(m)
            ampm = "AM" if hh < 12 else "PM"
            h12 = hh % 12 or 12
            return f"{h12}:{mm:02d} {ampm}"
        except ValueError:
            return None

    def _ordinal(n: int) -> str:
        s = {1: "st", 2: "nd", 3: "rd"}
        return f"{n}{s.get(n % 10 if n % 100 not in (11,12,13) else 0, 'th')}"

    # Every minute
    if all(f == "*" for f in fields):
        return "Every minute."

    # Every N minutes
    if mn.startswith("*/") and hr == "*" and dm == "*" and mo == "*" and dw == "*":
        n = int(mn[2:])
        return f"Every {n} minute{'s' if n > 1 else ''}."

    # Every hour at :MM (0 * * * *)
    if not mn.startswith("*/") and hr == "*" and dm == "*" and mo == "*" and dw == "*":
        try:
            m = int(mn)
            return f"Every hour at :{m:02d}." if m else "Every hour."
        except ValueError:
            return None

    # Every N hours at :MM
    if not mn.startswith("*/") and hr.startswith("*/") and dm == "*" and mo == "*" and dw == "*":
        try:
            n, m = int(hr[2:]), int(mn)
            return f"Every {n} hour{'s' if n > 1 else ''} at :{m:02d}."
        except ValueError:
            return None

    # Daily at fixed time
    if dm == "*" and mo == "*" and dw == "*":
        t = _fmt_time(hr, mn)
        return f"Every day at {t}." if t else None

    # Specific weekday(s)
    if dm == "*" and mo == "*" and dw != "*":
        t = _fmt_time(hr, mn)
        if not t:
            return None
        try:
            if "," in dw:
                days = [_CRON_DOW.get(int(d), d) for d in dw.split(",")]
                day_str = ", ".join(days[:-1]) + " and " + days[-1]
            else:
                day_str = _CRON_DOW.get(int(dw), dw)
            return f"Every {day_str} at {t}."
        except (ValueError, KeyError):
            return None

    # Monthly — specific day
    if dm != "*" and mo == "*" and dw == "*":
        t = _fmt_time(hr, mn)
        if not t:
            return None
        try:
            return f"The {_ordinal(int(dm))} of every month at {t}."
        except ValueError:
            return None

    # Yearly — specific day + month
    if dm != "*" and mo != "*" and dw == "*":
        t = _fmt_time(hr, mn)
        if not t:
            return None
        try:
            return f"Once a year: {_CRON_MONTH[int(mo)]} {_ordinal(int(dm))} at {t}."
        except (ValueError, KeyError):
            return None

    return None


def explain_cron(expr: str, model: str, copy: bool) -> None:
    """Explain a cron expression in plain English."""
    console.rule(f"[bold cyan]errex — Cron: {expr}[/bold cyan]")
    console.print()

    local = _cron_local(expr)
    if local:
        console.print(f"[bold]{local}[/bold]\n")
        console.print(f"[dim]Fields: minute  hour  day-of-month  month  day-of-week[/dim]")
        console.print(f"[dim]        {expr}[/dim]")
        console.print()
        console.rule(style="dim")
        if copy:
            copy_to_clipboard(f"Cron `{expr}`: {local}")
        return

    console.print("[dim]Complex expression — asking Claude…[/dim]\n")
    prompt = (
        f"Explain this cron expression in plain English: `{expr}`\n\n"
        f"Cover: when it runs (with concrete examples), what each field means, "
        f"and any edge cases (e.g. month-end days, DST). Use markdown."
    )
    call_claude(expr, model=model, messages=[{"role": "user", "content": prompt}])
    print()
    console.rule(style="dim")
    if copy:
        copy_to_clipboard(expr)


def extract_snippet(error_text: str) -> str:
    """Strip stdlib/library frames from a traceback, leaving only user-code lines."""
    lines = error_text.splitlines()
    result = []
    skip_next = False

    for line in lines:
        stripped = line.strip()

        if skip_next:
            skip_next = False
            continue

        # Python traceback file lines: '  File "path", line N, in func'
        if stripped.startswith('File "') and '", line' in stripped:
            if _STDLIB_RE.search(line):
                skip_next = True  # also drop the code-context line that follows
                continue

        # Node.js stack frames: '    at Func (path:line:col)'
        if stripped.startswith("at ") and _STDLIB_RE.search(line):
            continue

        result.append(line)

    filtered = "\n".join(result).strip()
    if not filtered or len(result) >= len(lines) - 1:
        return error_text  # nothing filtered — return as-is
    return filtered


def list_profiles() -> None:
    """List all named profiles saved in ~/.errexrc."""
    if not CONFIG_FILE.exists():
        console.print(f"[yellow]No config file at {CONFIG_FILE}. Run [cyan]errex --setup[/cyan] to create one.[/yellow]")
        sys.exit(0)
    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        err_console.print(f"[red]errex: could not read config: {e}[/red]")
        sys.exit(1)

    profiles = data.get("profiles", {})
    if not profiles:
        console.print("[yellow]No profiles saved yet.[/yellow]")
        console.print('[dim]Add a "profiles" key to ~/.errexrc:[/dim]')
        console.print('[dim]  {"profiles": {"go": {"lang": "go", "model": "claude-opus-4-7"}}}[/dim]')
        return

    console.rule("[bold cyan]errex — Profiles[/bold cyan]")
    console.print(f"[dim]{CONFIG_FILE}[/dim]\n")
    table = Table(show_header=True, header_style="bold magenta", box=None, show_edge=False)
    table.add_column("Profile", style="cyan", min_width=12)
    table.add_column("Settings")
    for name, settings in profiles.items():
        parts = "  ".join(f"{k}={v}" for k, v in settings.items())
        table.add_row(name, parts)
    console.print(table)
    console.print(f"\n[dim]Use with: errex --profile NAME[/dim]")


def run_doctor() -> None:
    """Check that errex is set up and working correctly."""
    console.rule("[bold cyan]errex — Doctor[/bold cyan]")
    console.print()
    ok = True

    # 1. API key
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        console.print(f"[green]✓[/green] ANTHROPIC_API_KEY is set ({api_key[:8]}…)")
    else:
        console.print("[red]✗[/red] ANTHROPIC_API_KEY is not set")
        console.print("  [dim]Get one at https://console.anthropic.com/[/dim]")
        ok = False

    # 2. Live API ping
    if api_key:
        try:
            client = anthropic.Anthropic(api_key=api_key, timeout=API_TIMEOUT)
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=8,
                messages=[{"role": "user", "content": "ping"}],
            )
            console.print("[green]✓[/green] Anthropic API reachable")
        except Exception as e:
            console.print(f"[red]✗[/red] Anthropic API error: {e}")
            ok = False

    # 3. Config file
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                cfg = json.load(f)
            console.print(f"[green]✓[/green] Config file OK ({CONFIG_FILE})")
        except json.JSONDecodeError as e:
            console.print(f"[red]✗[/red] Config file has invalid JSON: {e}")
            ok = False
    else:
        console.print(f"[dim]–[/dim] No config file (using defaults) — run [cyan]errex --setup[/cyan] to create one")

    # 4. History file
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE) as f:
            count = sum(1 for line in f if line.strip())
        console.print(f"[green]✓[/green] History file OK ({count} entries at {HISTORY_FILE})")
    else:
        console.print("[dim]–[/dim] No history file yet (created on first use)")

    # 5. Version check
    try:
        current = importlib.metadata.version("errex")
        req = urllib.request.Request(
            "https://pypi.org/pypi/errex/json",
            headers={"User-Agent": f"errex/{current}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            latest = json.loads(resp.read())["info"]["version"]
        if latest == current:
            console.print(f"[green]✓[/green] errex {current} is up to date")
        else:
            console.print(f"[yellow]![/yellow] errex {current} → {latest} available ([dim]pip install --upgrade errex[/dim])")
    except Exception:
        console.print("[dim]–[/dim] Could not check PyPI for updates")

    console.print()
    if ok:
        console.rule("[green]All checks passed[/green]")
    else:
        console.rule("[red]Some checks failed — see above[/red]")
        sys.exit(1)


def print_completion(shell: str) -> None:
    """Print a shell completion script for errex."""
    flags = [
        "--model", "--brief", "--lang", "--copy", "--json", "--fix",
        "--watch", "--history", "--install-shell", "--stats", "--share",
        "--web", "--scan", "--setup", "--context", "--chat", "--tokens",
        "--notify", "--update", "--explain-code", "--issues", "--lint",
        "--export", "--export-format", "--ask", "--explain-diff", "--similar",
        "--config", "--clear-history", "--recent", "--summarize-log", "--retry",
        "--test-gen", "--translate", "--save-as", "--grep", "--doctor",
        "--completion", "--version", "--help",
    ]
    models = ["claude-sonnet-4-6", "claude-opus-4-7", "claude-haiku-4-5-20251001"]

    if shell == "bash":
        flags_str = " ".join(flags)
        models_str = " ".join(models)
        script = f"""# errex bash completion — add to ~/.bashrc:
# source <(errex --completion bash)

_errex_complete() {{
    local cur prev
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"

    case "$prev" in
        --model) COMPREPLY=($(compgen -W "{models_str}" -- "$cur")); return ;;
        --export-format) COMPREPLY=($(compgen -W "html md" -- "$cur")); return ;;
        --completion) COMPREPLY=($(compgen -W "bash zsh" -- "$cur")); return ;;
        --watch|--lint|--explain-code|--test-gen|--summarize-log|--grep|\\
        --context|--explain-diff|--export) COMPREPLY=($(compgen -f -- "$cur")); return ;;
    esac

    if [[ "$cur" == -* ]]; then
        COMPREPLY=($(compgen -W "{flags_str}" -- "$cur"))
    else
        COMPREPLY=($(compgen -f -- "$cur"))
    fi
}}

complete -F _errex_complete errex
"""
    elif shell == "zsh":
        flag_args = "\n    ".join(f"'{f}'" for f in flags)
        script = f"""#compdef errex
# errex zsh completion — add to ~/.zshrc:
# source <(errex --completion zsh)

_errex() {{
    local -a flags
    flags=(
    {flag_args}
    )
    _arguments \\
        '*:file:_files' \\
        '--model[Claude model]:model:({" ".join(models)})' \\
        '--export-format[export format]:format:(html md)' \\
        '--completion[shell]:shell:(bash zsh)' \\
        ${{flags[@]}}
}}

_errex
"""
    else:
        err_console.print(f"[red]errex: unknown shell '{shell}'. Use bash or zsh.[/red]")
        sys.exit(1)

    print(script.strip())


def grep_and_explain(
    pattern: str,
    path: str,
    model: str,
    lang: str | None,
    copy: bool,
    show_tokens: bool,
) -> None:
    """Filter a log file by pattern and explain the matching error lines."""
    content = read_file(path)
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        err_console.print(f"[red]errex: invalid pattern '{pattern}': {e}[/red]")
        sys.exit(1)

    matched = [line for line in content.splitlines() if rx.search(line)]
    if not matched:
        console.print(f"[yellow]No lines matching '{pattern}' in {path}.[/yellow]")
        sys.exit(0)

    excerpt = "\n".join(matched[:200])  # cap at 200 lines
    console.print(f"[dim]Found {len(matched)} matching line(s) — explaining…[/dim]\n")
    explain_error(
        excerpt,
        model=model,
        lang=lang,
        copy=copy,
        show_tokens=show_tokens,
    )


TEST_GEN_PROMPT = """You are a senior software engineer. Given a code file (and optionally an error that occurs when running it), generate a minimal, runnable test case.

Rules:
- Use the natural test framework for the language: pytest for Python, Jest for JS/TS, `go test` for Go, etc.
- If an error is provided, the test should reproduce the exact failure
- If no error is provided, write tests for the key functions/behaviours in the file
- Keep the test self-contained — include any necessary imports and fixtures
- Add a one-line comment above each test explaining what it covers
- Output only the test file content, no explanation

Output as a fenced code block with the appropriate language tag."""


def generate_test(code_path: str, error_text: str | None, model: str, lang: str | None, copy: bool, show_tokens: bool) -> None:
    """Generate a test case from a code file, optionally reproducing an error."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    code = read_file(code_path)
    lang_hint = f" (language: {lang})" if lang else ""

    if error_text:
        prompt = (
            f"Here is a code file{lang_hint}:\n\n```\n{code}\n```\n\n"
            f"When run, it produces this error:\n\n```\n{error_text}\n```\n\n"
            f"Generate a test case that reproduces this error."
        )
    else:
        prompt = f"Here is a code file{lang_hint}:\n\n```\n{code}\n```\n\nGenerate a test suite for the key behaviours."

    console.rule(f"[bold cyan]errex — Test Gen: {Path(code_path).name}[/bold cyan]")
    print()

    client = anthropic.Anthropic(timeout=API_TIMEOUT)
    collected = []
    input_tokens = output_tokens = 0
    try:
        with client.messages.stream(
            model=model,
            max_tokens=2048,
            system=[{"type": "text", "text": TEST_GEN_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                collected.append(text)
            final = stream.get_final_message()
            input_tokens = final.usage.input_tokens
            output_tokens = final.usage.output_tokens
    except anthropic.APIError as e:
        err_console.print(f"\n[red]errex: API error — {e}[/red]")
        sys.exit(2)

    response = "".join(collected)
    print()
    if show_tokens:
        show_token_usage(input_tokens, output_tokens)
    console.rule(style="dim")
    print()

    save_history(code[:200], response, model, False)
    if copy:
        copy_to_clipboard(response)


def lint_file(path: str, model: str, lang: str | None, copy: bool, show_tokens: bool) -> None:
    """Scan a code file for potential bugs and issues."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    code = read_file(path)
    lang_hint = f" (language: {lang})" if lang else ""
    prompt = f"Please review this code{lang_hint} for potential issues:\n\n```\n{code}\n```"

    console.rule(f"[bold cyan]errex — Lint: {Path(path).name}[/bold cyan]")
    print()

    client = anthropic.Anthropic(timeout=API_TIMEOUT)
    collected = []
    input_tokens = output_tokens = 0
    try:
        with client.messages.stream(
            model=model,
            max_tokens=2048,
            system=[{"type": "text", "text": LINT_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                collected.append(text)
            final = stream.get_final_message()
            input_tokens = final.usage.input_tokens
            output_tokens = final.usage.output_tokens
    except anthropic.APIError as e:
        err_console.print(f"\n[red]errex: API error — {e}[/red]")
        sys.exit(2)

    response = "".join(collected)
    print()
    if show_tokens:
        show_token_usage(input_tokens, output_tokens)
    console.rule(style="dim")
    print()

    save_history(code, response, model, False)
    if copy:
        copy_to_clipboard(response)


def explain_code(path: str, model: str, lang: str | None, copy: bool, show_tokens: bool, chat: bool) -> None:
    """Explain what a piece of code does."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    code = read_file(path)
    lang_hint = f" (language: {lang})" if lang else ""
    prompt = f"Please explain this code{lang_hint}:\n\n```\n{code}\n```"

    console.rule("[bold cyan]errex — Code Explanation[/bold cyan]")
    print()

    client = anthropic.Anthropic(timeout=API_TIMEOUT)
    collected = []
    input_tokens = output_tokens = 0
    try:
        with client.messages.stream(
            model=model,
            max_tokens=2048,
            system=[{"type": "text", "text": CODE_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                collected.append(text)
            final = stream.get_final_message()
            input_tokens = final.usage.input_tokens
            output_tokens = final.usage.output_tokens
    except anthropic.APIError as e:
        err_console.print(f"\n[red]errex: API error — {e}[/red]")
        sys.exit(2)

    response = "".join(collected)
    print()
    if show_tokens:
        show_token_usage(input_tokens, output_tokens)
    console.rule(style="dim")
    print()

    save_history(code, response, model, False)
    if copy:
        copy_to_clipboard(response)

    if chat and sys.stdin.isatty():
        # reuse chat_loop — treat code as the "error" context
        chat_loop(code, response, model, lang)


def main() -> None:
    # Two-pass: detect --profile before full parse so profile defaults can be set
    _pre = argparse.ArgumentParser(add_help=False)
    _pre.add_argument("--profile", default=None)
    _pre_args, _ = _pre.parse_known_args()

    file_config: dict = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as _f:
                file_config = json.load(_f)
        except (json.JSONDecodeError, OSError):
            pass

    config = load_config()
    if _pre_args.profile:
        config = load_profile(_pre_args.profile, file_config)

    try:
        _ver = importlib.metadata.version("errex")
    except importlib.metadata.PackageNotFoundError:
        _ver = "dev"

    parser = argparse.ArgumentParser(
        prog="errex",
        description="Paste or pipe an error message and get a plain-English explanation.",
    )
    parser.add_argument("--version", action="version", version=f"errex {_ver}")
    parser.add_argument("files", nargs="*", help="one or more files containing errors (pass 2+ to compare them)")
    parser.add_argument("--model", help="Claude model to use (default: claude-sonnet-4-6)")
    parser.add_argument("--brief", action="store_true", default=None, help="one-paragraph summary instead of full analysis")
    parser.add_argument("--lang", help="language or runtime hint when ambiguous (e.g. rust, go, java)")
    parser.add_argument("--copy", action="store_true", default=None, help="copy the explanation to the clipboard after printing")
    parser.add_argument("--json", action="store_true", dest="json_output", help="output structured JSON")
    parser.add_argument("--fix", action="store_true", help="output only the fix command, no explanation")
    parser.add_argument("--watch", metavar="LOGFILE", help="watch a log file and explain errors as they appear")
    parser.add_argument("--history", nargs="?", const="", metavar="SEARCH", help="show past explanations, optionally filtered by a search term")
    parser.add_argument("--install-shell", action="store_true", help="add errex-last() function to your shell config")
    parser.add_argument("--stats", action="store_true", help="show usage statistics from your history")
    parser.add_argument("--share", action="store_true", help="upload explanation to paste.rs and print a shareable link")
    parser.add_argument("--web", action="store_true", help="launch the local web UI at http://localhost:7337")
    parser.add_argument("--scan", action="store_true", help="scan for recent error logs and pick one to explain")
    parser.add_argument("--setup", action="store_true", help="run the setup wizard (API key, environment detection, shell integration)")
    parser.add_argument("--context", metavar="FILE", help="attach a code file for more targeted explanations")
    parser.add_argument("--chat", action="store_true", help="stay in a follow-up Q&A loop after the explanation")
    parser.add_argument("--tokens", action="store_true", help="show token usage after each explanation")
    parser.add_argument("--notify", action="store_true", help="send a desktop notification when the explanation is ready")
    parser.add_argument("--update", action="store_true", help="check for a newer version of errex")
    parser.add_argument("--explain-code", metavar="FILE", dest="explain_code", help="explain what a piece of code does")
    parser.add_argument("--issues", action="store_true", help="search GitHub Issues for similar errors after explaining")
    parser.add_argument("--lint", metavar="FILE", help="scan a code file for potential bugs and issues")
    parser.add_argument("--export", metavar="FILE", help="export history to a file (.html or .md)")
    parser.add_argument("--export-format", choices=["html", "md"], default=None, help="format for --export (auto-detected from extension if omitted)")
    parser.add_argument("--ask", metavar="QUESTION", help="ask a follow-up question about the last error in history")
    parser.add_argument("--explain-diff", metavar="FILE", dest="explain_diff", nargs="?", const="-", help="explain a git diff (pass a .diff/.patch file, or pipe: git diff | errex --explain-diff)")
    parser.add_argument("--similar", action="store_true", help="find past errors in your history that are similar to the current one")
    parser.add_argument("--config", nargs="?", const=None, metavar="KEY=VALUE", help="view or set config (e.g. --config model=claude-opus-4-7); omit value to show all settings")
    parser.add_argument("--clear-history", nargs="?", const=0, type=int, metavar="DAYS", dest="clear_history",
                        help="delete history entries (all by default; pass DAYS to only remove entries older than N days)")
    parser.add_argument("--recent", nargs="?", const=5, type=int, metavar="N",
                        help="show the N most recent history entries (default: 5)")
    parser.add_argument("--summarize-log", metavar="FILE", dest="summarize_log",
                        help="produce a diagnostic digest of all distinct errors in a log file")
    parser.add_argument("--retry", action="store_true",
                        help="re-explain the last error from history (combine with --model, --brief, etc.)")
    parser.add_argument("--test-gen", metavar="FILE", dest="test_gen",
                        help="generate a test case for a code file; pipe an error to reproduce it")
    parser.add_argument("--doctor", action="store_true",
                        help="check that errex is set up correctly (API key, config, connectivity)")
    parser.add_argument("--completion", metavar="SHELL", choices=["bash", "zsh"],
                        help="print a shell completion script (bash or zsh)")
    parser.add_argument("--translate", metavar="LANG",
                        help="translate the explanation into a spoken language (e.g. Spanish, French, Japanese)")
    parser.add_argument("--save-as", metavar="NAME", dest="save_as",
                        help="save this explanation with a memorable name for quick retrieval")
    parser.add_argument("--grep", nargs=2, metavar=("PATTERN", "FILE"),
                        help="filter a log file by regex pattern, then explain matching lines")
    parser.add_argument("--ci", action="store_true",
                        help="CI mode: no-color + terse output, GitHub Actions annotations, exits 1")
    parser.add_argument("--rate", metavar="SCORE", type=int, dest="rate",
                        help="rate the last explanation 1-5 (stored in history, shown in --stats)")
    parser.add_argument("--profile", metavar="NAME",
                        help="load a named config profile from ~/.errexrc (overrides config, CLI wins)")
    parser.add_argument("--bulk", metavar="FILE",
                        help="explain multiple errors from a file separated by blank lines")
    parser.add_argument("--explain-exit", metavar="CODE", type=int, dest="explain_exit",
                        help="explain a shell exit code (e.g. --explain-exit 139 → segfault)")
    parser.add_argument("--explain-http", metavar="CODE", type=int, dest="explain_http",
                        help="explain an HTTP status code (e.g. --explain-http 429)")
    parser.add_argument("--explain-cron", metavar="EXPR", dest="explain_cron",
                        help="explain a cron expression (e.g. --explain-cron '0 * * * *')")
    parser.add_argument("--snippet", action="store_true",
                        help="strip stdlib/library frames from a traceback before explaining")
    parser.add_argument("--debug", action="store_true",
                        help="dry run: print the prompt that would be sent to Claude, then exit")
    parser.add_argument("--list-profiles", action="store_true", dest="list_profiles",
                        help="list all named profiles in ~/.errexrc")
    parser.add_argument("--add-note", metavar="TEXT", dest="add_note",
                        help="append a personal note to the last history entry")
    parser.add_argument("--format-json", action="store_true", dest="format_json",
                        help="parse the error as JSON and reformat it before explaining")
    parser.add_argument("--interactive", action="store_true",
                        help="browse recent history with a numbered picker")
    parser.add_argument("--webhook", metavar="URL",
                        help="POST the explanation as JSON to a URL (Slack, Discord, or generic)")
    parser.add_argument("--find-name", metavar="NAME", dest="find_name",
                        help="retrieve a history entry saved with --save-as NAME")
    parser.add_argument("--timeout", metavar="N", type=int, default=30,
                        help="API request timeout in seconds (default: 30)")
    parser.add_argument("--output", metavar="FILE",
                        help="save the explanation to a file (in addition to printing)")
    parser.add_argument("--terse", action="store_true",
                        help="one-sentence diagnosis — shorter than --brief, great for scripting")
    parser.add_argument("--no-color", action="store_true", dest="no_color",
                        help="plain-text output with no rich formatting (safe to pipe)")
    parser.add_argument("--since", metavar="DATE",
                        help="filter --history/--recent to entries on or after DATE (YYYY-MM-DD)")
    parser.add_argument("--env", action="store_true",
                        help="auto-attach system info (OS, Python, shell, runtimes) as context")
    parser.add_argument("--explain-regex", metavar="PATTERN", dest="explain_regex",
                        help="explain what a regular expression matches in plain English")
    parser.set_defaults(**config)
    args = parser.parse_args()

    global console, err_console, API_TIMEOUT
    API_TIMEOUT = args.timeout

    if args.no_color or args.ci:
        console = Console(no_color=True, highlight=False)
        err_console = Console(stderr=True, no_color=True, highlight=False)

    if args.ci:
        args.terse = True

    if args.rate is not None:
        rate_last(args.rate)
        return

    if args.bulk:
        run_bulk(
            args.bulk,
            model=args.model,
            brief=args.brief or False,
            terse=args.terse,
            lang=args.lang,
            copy=args.copy or False,
            show_tokens=args.tokens,
        )
        return

    if "--config" in sys.argv:
        manage_config(args.config)
        return

    if args.clear_history is not None:
        days = args.clear_history if args.clear_history > 0 else None
        clear_history(days)
        return

    if args.recent is not None:
        show_recent(args.recent, since=args.since)
        return

    if args.summarize_log:
        summarize_log(
            args.summarize_log,
            model=args.model,
            copy=args.copy or False,
            show_tokens=args.tokens,
        )
        return

    if args.retry:
        retry_last(
            model=args.model,
            brief=args.brief or False,
            fix=args.fix,
            lang=args.lang,
            copy=args.copy or False,
            show_tokens=args.tokens,
            chat=args.chat,
        )
        return

    if args.doctor:
        run_doctor()
        return

    if args.completion:
        print_completion(args.completion)
        return

    if args.grep:
        grep_and_explain(
            args.grep[0],
            args.grep[1],
            model=args.model,
            lang=args.lang,
            copy=args.copy or False,
            show_tokens=args.tokens,
        )
        return

    if args.explain_exit is not None:
        explain_exit_code(args.explain_exit, model=args.model, copy=args.copy or False)
        return

    if args.explain_http is not None:
        explain_http(args.explain_http, model=args.model, copy=args.copy or False)
        return

    if args.explain_cron:
        explain_cron(args.explain_cron, model=args.model, copy=args.copy or False)
        return

    if args.list_profiles:
        list_profiles()
        return

    if args.add_note:
        add_note(args.add_note)
        return

    if args.interactive:
        interactive_history()
        return

    if args.find_name:
        find_by_name(args.find_name)
        return

    if args.ask:
        ask_about_last(
            args.ask,
            model=args.model,
            show_tokens=args.tokens,
            copy=args.copy or False,
        )
        return

    if args.stats:
        show_stats()
        return

    if args.web:
        from web import serve
        serve()
        return

    if args.update:
        check_for_update()
        return

    if args.setup:
        run_setup()
        return

    if args.scan:
        scan_logs()
        return

    if args.export:
        fmt = args.export_format or ("html" if args.export.endswith(".html") else "md")
        export_history(args.export, fmt)
        return

    if args.explain_diff is not None:
        if args.explain_diff == "-" or args.explain_diff is True:
            if not sys.stdin.isatty():
                diff_text = sys.stdin.read().strip()
            else:
                console.print("[dim]Paste your diff below. Press Ctrl+D when done:[/dim]\n")
                diff_text = sys.stdin.read().strip()
        else:
            diff_text = read_file(args.explain_diff)
        if not diff_text:
            err_console.print("[red]errex: no diff content provided.[/red]")
            sys.exit(1)
        explain_diff(
            diff_text,
            model=args.model,
            lang=args.lang,
            copy=args.copy or False,
            show_tokens=args.tokens,
        )
        return

    if args.test_gen:
        error_text_for_test = None
        if not sys.stdin.isatty():
            error_text_for_test = sys.stdin.read().strip() or None
        generate_test(
            args.test_gen,
            error_text=error_text_for_test,
            model=args.model,
            lang=args.lang,
            copy=args.copy or False,
            show_tokens=args.tokens,
        )
        return

    if args.lint:
        lint_file(
            args.lint,
            model=args.model,
            lang=args.lang,
            copy=args.copy or False,
            show_tokens=args.tokens,
        )
        return

    if args.explain_code:
        explain_code(
            args.explain_code,
            model=args.model,
            lang=args.lang,
            copy=args.copy or False,
            show_tokens=args.tokens,
            chat=args.chat,
        )
        return

    if args.install_shell:
        install_shell()
        return

    if args.history is not None:
        show_history(args.history or None, since=args.since)
        return

    if args.explain_regex:
        explain_regex(
            args.explain_regex,
            model=args.model,
            copy=args.copy or False,
            show_tokens=args.tokens,
        )
        return

    if args.watch:
        watch_file(args.watch, model=args.model, brief=args.brief or False, lang=args.lang)
        return

    if len(args.files) >= 2:
        compare_errors(args.files, model=args.model, lang=args.lang, copy=args.copy or False)
        return

    error_text = get_error_input(args.files)

    if not error_text:
        parser.print_usage(sys.stderr)
        sys.exit(1)

    if args.similar:
        find_similar(error_text)
        return

    context_text = read_file(args.context) if args.context else None

    if args.env:
        env_block = get_env_info()
        context_text = (context_text + "\n\n" if context_text else "") + f"System environment:\n{env_block}"

    if args.format_json:
        formatted = format_json_error(error_text)
        if formatted != error_text:
            err_console.print("[dim](JSON parsed and reformatted)[/dim]")
        error_text = formatted

    if args.snippet:
        trimmed = extract_snippet(error_text)
        if trimmed != error_text:
            n_orig = error_text.count("\n") + 1
            n_trim = trimmed.count("\n") + 1
            err_console.print(f"[dim](snippet: {n_orig} → {n_trim} lines after stripping library frames)[/dim]")
        error_text = trimmed

    if args.ci and os.environ.get("GITHUB_ACTIONS"):
        first_line = error_text.splitlines()[0][:200] if error_text else "error"
        print(f"::error::{first_line}")

    explain_error(
        error_text,
        model=args.model,
        brief=args.brief or False,
        terse=args.terse,
        json_output=args.json_output,
        fix=args.fix,
        lang=args.lang,
        copy=args.copy or False,
        share=args.share,
        show_tokens=args.tokens,
        chat=args.chat,
        context=context_text,
        do_notify=args.notify,
        issues=args.issues,
        translate=args.translate,
        save_as=args.save_as,
        output_file=args.output,
        webhook=args.webhook,
        dry_run=args.debug,
    )

    if args.ci:
        sys.exit(1)

    check_for_update()


if __name__ == "__main__":
    main()
