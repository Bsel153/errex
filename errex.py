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

SHELL_FUNCTION = """
# errex shell integration — added by errex --install-shell
function errex-last() {
  eval "$(fc -ln -1)" 2>&1 | errex "$@"
}
"""


def load_config() -> dict:
    defaults = {"model": "claude-sonnet-4-6", "brief": False, "lang": None, "copy": False}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return {**defaults, **json.load(f)}
        except (json.JSONDecodeError, OSError):
            pass
    return defaults


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


def save_history(error_text: str, explanation: str, model: str, brief: bool) -> None:
    entry = {
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "brief": brief,
        "error": error_text[:200],
        "explanation": explanation,
    }
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def show_history(search: str | None) -> None:
    """Print past explanations from the history file."""
    if not HISTORY_FILE.exists():
        console.print("[yellow]No history yet.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

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

    busiest_day = max(days, key=days.get) if days else "—"
    busiest_hour = max(hours, key=hours.get) if hours else 0
    first_used = min(e["timestamp"][:10] for e in entries if "timestamp" in e)

    console.rule("[bold cyan]errex — Usage Stats[/bold cyan]")
    console.print()

    # Summary panel
    summary = (
        f"[bold]{total}[/bold] total explanations\n"
        f"[bold]{brief_count}[/bold] brief  /  [bold]{total - brief_count}[/bold] full\n"
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


def show_token_usage(input_tokens: int, output_tokens: int) -> None:
    total = input_tokens + output_tokens
    console.print(
        f"[dim]tokens: {input_tokens:,} in · {output_tokens:,} out · {total:,} total[/dim]"
    )


def call_claude(
    error_text: str,
    model: str,
    brief: bool = False,
    json_output: bool = False,
    fix: bool = False,
    lang: str | None = None,
    context: str | None = None,
    messages: list | None = None,
) -> tuple[str, int, int]:
    """Send error to Claude, stream to stdout, return (response, input_tokens, output_tokens)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    client = anthropic.Anthropic()
    lang_hint = f" (language: {lang})" if lang else ""
    context_block = f"\n\nFor context, here is the relevant code:\n```\n{context}\n```" if context else ""

    if messages is None:
        if fix:
            prompt = f"Given this error{lang_hint}, output ONLY the exact shell command(s) to fix it as a code block. No explanation.\n\n```\n{error_text}\n```{context_block}"
        elif json_output:
            prompt = (
                f"Explain this error{lang_hint} as JSON with keys: error_type, language, "
                f"explanation, root_cause, fix_steps (array), gotchas (array). "
                f"Return only valid JSON, no markdown fences.\n\n```\n{error_text}\n```{context_block}"
            )
        elif brief:
            prompt = f"In one short paragraph, tell me: what this error{lang_hint} is, the most likely cause, and how to fix it.\n\n```\n{error_text}\n```{context_block}"
        else:
            prompt = f"Please explain this error{lang_hint}:\n\n```\n{error_text}\n```{context_block}"
        messages = [{"role": "user", "content": prompt}]

    collected = []
    input_tokens = output_tokens = 0
    try:
        with client.messages.stream(
            model=model,
            max_tokens=256 if brief else 2048,
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
    json_output: bool = False,
    fix: bool = False,
    lang: str | None = None,
    copy: bool = False,
    share: bool = False,
    show_tokens: bool = False,
    chat: bool = False,
    context: str | None = None,
    do_notify: bool = False,
) -> None:
    """Explain an error, render output, save history."""
    if not json_output:
        console.rule("[bold cyan]errex — Error Analysis[/bold cyan]")
        print()

    response, in_tok, out_tok = call_claude(
        error_text, model=model, brief=brief, json_output=json_output,
        fix=fix, lang=lang, context=context,
    )

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

    save_history(error_text, response, model, brief)

    if copy:
        copy_to_clipboard(response)

    if share:
        share_explanation(error_text, response)

    if do_notify:
        notify("errex", f"Error explained: {error_text[:60]}")

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

    client = anthropic.Anthropic()
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


def watch_file(path: str, model: str, brief: bool, lang: str | None) -> None:
    """Tail a log file and explain errors as they appear."""
    if not os.path.exists(path):
        console.print(f"[red]errex: file not found: {path}[/red]", file=sys.stderr)
        sys.exit(1)

    console.print(f"[bold]Watching[/bold] [cyan]{path}[/cyan] [dim](Ctrl+C to stop)[/dim]")

    with open(path, encoding="utf-8", errors="replace") as f:
        f.seek(0, 2)
        buffer: list[str] = []
        has_error = False
        last_activity: float | None = None

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


def main() -> None:
    config = load_config()

    parser = argparse.ArgumentParser(
        prog="errex",
        description="Paste or pipe an error message and get a plain-English explanation.",
    )
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
    parser.set_defaults(**config)
    args = parser.parse_args()

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

    if args.install_shell:
        install_shell()
        return

    if args.history is not None:
        show_history(args.history or None)
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

    context_text = read_file(args.context) if args.context else None

    explain_error(
        error_text,
        model=args.model,
        brief=args.brief or False,
        json_output=args.json_output,
        fix=args.fix,
        lang=args.lang,
        copy=args.copy or False,
        share=args.share,
        show_tokens=args.tokens,
        chat=args.chat,
        context=context_text,
        do_notify=args.notify,
    )

    check_for_update()


if __name__ == "__main__":
    main()
