from __future__ import annotations

import sys
import os
import re
import platform
import subprocess
import time
import importlib.metadata
import urllib.request
import urllib.error
import urllib.parse
import json

from . import output, _constants


def read_file(path: str) -> str:
    if not os.path.exists(path):
        output.err_console.print(f"[red]errex: file not found: {path}[/red]")
        sys.exit(1)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read().strip()


def get_error_input(files: list) -> str:
    """Read error input from file argument(s), piped stdin, or interactive paste."""
    if files:
        return read_file(files[0])

    if not sys.stdin.isatty():
        return sys.stdin.read().strip()

    output.console.print("[dim]Paste your error below. Press Ctrl+D (Mac/Linux) or Ctrl+Z+Enter (Windows) when done:[/dim]\n")
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
        output.console.print(f"\n[bold green]Shareable link:[/bold green] [cyan]{url}[/cyan]")
    except urllib.error.URLError as e:
        output.err_console.print(f"[yellow]errex: could not create share link — {e}[/yellow]")


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


def _parse_since(since: str):
    """Parse a YYYY-MM-DD date string, return a datetime or None on failure."""
    from datetime import datetime
    try:
        return datetime.strptime(since, "%Y-%m-%d")
    except ValueError:
        output.err_console.print(f"[red]errex: --since expects YYYY-MM-DD, got: {since!r}[/red]")
        sys.exit(1)


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
    shown: set = set()

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
            if _constants._STDLIB_RE.search(line):
                skip_next = True  # also drop the code-context line that follows
                continue

        # Node.js stack frames: '    at Func (path:line:col)'
        if stripped.startswith("at ") and _constants._STDLIB_RE.search(line):
            continue

        result.append(line)

    filtered = "\n".join(result).strip()
    if not filtered or len(result) >= len(lines) - 1:
        return error_text  # nothing filtered — return as-is
    return filtered


def redact_secrets(text: str) -> tuple:
    """Strip common secret patterns from text. Returns (redacted_text, count_replaced)."""
    count = 0
    for pattern, replacement in _constants._REDACT_PATTERNS:
        new_text, n = pattern.subn(replacement, text)
        text = new_text
        count += n
    return text, count


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
            output.console.print(
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
            from pathlib import Path
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


def post_webhook(url: str, error_text: str, explanation: str, model: str) -> None:
    """POST the explanation to a webhook URL (Slack, Discord, or generic JSON)."""
    from datetime import datetime
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
        output.console.print(f"\n[green]Webhook posted[/green] [dim](HTTP {status} → {url})[/dim]")
    except urllib.error.URLError as e:
        output.err_console.print(f"[yellow]errex: webhook failed — {e}[/yellow]")


def _detect_yaml_type(content: str) -> str:
    if re.search(r'^services\s*:', content, re.MULTILINE) and re.search(r'(image|build)\s*:', content):
        return 'Docker Compose'
    if re.search(r'^apiVersion\s*:', content, re.MULTILINE) and re.search(r'^kind\s*:', content, re.MULTILINE):
        return 'Kubernetes'
    if re.search(r'^(on|jobs)\s*:', content, re.MULTILINE):
        return 'GitHub Actions'
    return 'YAML config'


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

    output.console.print(f"\n[bold]Searching GitHub Issues for:[/bold] [dim]{query}[/dim]\n")

    try:
        encoded = urllib.parse.quote(query)
        url = f"https://api.github.com/search/issues?q={encoded}+is:issue&sort=relevance&per_page=5"
        req = urllib.request.Request(url, headers={"User-Agent": "errex", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        output.console.print(f"[yellow]Could not search GitHub: {e}[/yellow]")
        return

    items = data.get("items", [])
    if not items:
        output.console.print("[dim]No matching GitHub issues found.[/dim]")
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

    output.console.print(table)
    output.console.print()
    for i, item in enumerate(items, 1):
        output.console.print(f"  [dim]{i}.[/dim] [cyan]{item['html_url']}[/cyan]")
    output.console.print()
