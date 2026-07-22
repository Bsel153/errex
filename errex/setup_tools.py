from __future__ import annotations

import os
import sys
import platform
import subprocess
import re
import json
import time
import importlib.metadata
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

import anthropic
from . import output, _constants
from ._paths import HISTORY_FILE, CONFIG_FILE
from .config import load_config
from .core import explain_error, call_claude
from .explainers import explain_exit_code
from .utils import notify


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


def run_setup() -> None:
    """Interactive first-run wizard: check API key, detect env, write ~/.errexrc."""
    output.console.rule("[bold cyan]errex — Setup Wizard[/bold cyan]")
    output.console.print()

    # 1. API key
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        output.console.print(f"[green]✓[/green] ANTHROPIC_API_KEY is set ({api_key[:8]}…)")
    else:
        output.console.print("[red]✗[/red] ANTHROPIC_API_KEY is not set.")
        output.console.print("  Get one at [cyan]https://console.anthropic.com/[/cyan]")
        output.console.print("  Then add to your shell config:")
        output.console.print('  [dim]export ANTHROPIC_API_KEY=sk-ant-...[/dim]\n')

    # 2. Detect environment
    output.console.print("\n[bold]Detecting your environment…[/bold]")
    env = detect_environment()
    if env["detected"]:
        output.console.print(f"[green]✓[/green] Found: {', '.join(env['detected'])}")
    else:
        output.console.print("[dim]No common runtimes detected.[/dim]")

    # 3. Build config
    existing = load_config()
    config: dict = {}

    if env["lang_default"] and not existing.get("lang"):
        config["lang"] = env["lang_default"]
        output.console.print(f"  → Setting default language: [cyan]{env['lang_default']}[/cyan]")

    # Suggest opus if only one language (power user), sonnet otherwise
    if not existing.get("model") or existing.get("model") == "claude-sonnet-4-6":
        config["model"] = "claude-sonnet-4-6"

    # 4. Write config
    if config:
        merged = {**existing, **config}
        with open(CONFIG_FILE, "w") as f:
            json.dump(merged, f, indent=2)
        output.console.print(f"\n[green]✓[/green] Wrote config to [cyan]{CONFIG_FILE}[/cyan]")
    else:
        output.console.print("\n[dim]Config unchanged.[/dim]")

    # 5. Shell integration
    output.console.print()
    shell = os.environ.get("SHELL", "")
    rc_file = Path.home() / (".zshrc" if "zsh" in shell else ".bashrc")
    shell_already = rc_file.exists() and "errex-last" in rc_file.read_text()
    if shell_already:
        output.console.print(f"[green]✓[/green] Shell integration already in {rc_file}")
    else:
        try:
            ans = input("Install errex-last() shell function? [Y/n]: ").strip().lower()
        except KeyboardInterrupt:
            ans = "n"
        if ans in ("", "y"):
            install_shell()

    # 6. Welcome scan — Pro customers see value immediately
    output.console.print()
    from .license import is_pro
    if is_pro():
        try:
            ans = input("Run a welcome scan now to see what errex finds on this machine? [Y/n]: ").strip().lower()
        except KeyboardInterrupt:
            ans = "n"
        if ans in ("", "y"):
            run_welcome_scan()
    else:
        output.console.print(
            "[dim]errex Pro includes a full security & diagnostics scan "
            "(--scan) — upgrade to run your first welcome scan.[/dim]"
        )

    output.console.print()
    output.console.rule("[dim]Setup complete[/dim]")
    output.console.print("\nRun [cyan]errex --scan[/cyan] to find error logs, or just pipe any error:\n  [dim]cat error.log | errex[/dim]\n")


def run_welcome_scan() -> None:
    """Run a one-time deep scan right after setup so new customers see value immediately."""
    from .scan import run_scan, detect_platform
    from .scanners._base import SEVERITIES

    from .mascot import say as _mascot_say
    output.console.print(f"\n  [dim]{_mascot_say('welcome')}[/dim]")

    plat = detect_platform()
    output.console.print(f"\n[bold]Running your first scan on {plat}…[/bold] [dim](this is a one-time welcome scan)[/dim]\n")

    def _progress(name, done, total):
        output.console.print(f"  Checking [dim]{name}[/dim]…", end="\r")

    result = run_scan(progress_cb=_progress)
    output.console.print(" " * 60, end="\r")

    try:
        from ._scan_scheduler import log_scan_result
        from .cloud_sync import sync_scan_summary, is_enabled as _sync_enabled
        from .config import load_config as _lc
        _cfg = _lc()
        entry = log_scan_result(result)
        if entry and _sync_enabled(_cfg):
            sync_scan_summary(entry, url=_cfg.get("sync_url"), key=_cfg.get("sync_key"))
    except Exception:
        pass

    if not result.findings:
        output.console.print("[green]✔ All clear — no issues found on this machine.[/green]\n")
        return

    icons = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}
    counts = {s: sum(1 for f in result.findings if f.severity == s) for s in SEVERITIES}
    summary = ", ".join(f"{counts[s]} {s}" for s in SEVERITIES if counts[s])
    output.console.print(f"[bold]Found {len(result.findings)} thing(s) worth a look:[/bold] {summary}\n")
    for severity in ("critical", "high"):
        for finding in result.findings:
            if finding.severity != severity:
                continue
            output.console.print(f"  {icons[severity]} [bold]{finding.title}[/bold]")
    output.console.print(
        "\n[dim]Run[/dim] [cyan]errex --scan[/cyan] [dim]for the full report, "
        "or[/dim] [cyan]errex --scan --scan-fix[/cyan] [dim]to fix what can be auto-fixed.[/dim]\n"
    )


def run_doctor(offline: bool = False) -> None:
    """Check that errex is set up and working correctly."""
    output.console.rule("[bold cyan]errex — Doctor[/bold cyan]")
    output.console.print()
    ok = True

    # 1. API key
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        output.console.print(f"[green]✓[/green] ANTHROPIC_API_KEY is set ({api_key[:8]}…)")
    else:
        output.console.print("[red]✗[/red] ANTHROPIC_API_KEY is not set")
        output.console.print("  [dim]Get one at https://console.anthropic.com/[/dim]")
        ok = False

    # 2. Live API ping
    if api_key and not offline:
        try:
            client = anthropic.Anthropic(api_key=api_key, timeout=_constants.API_TIMEOUT)
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=8,
                messages=[{"role": "user", "content": "ping"}],
            )
            output.console.print("[green]✓[/green] Anthropic API reachable")
        except Exception as e:
            output.console.print(f"[red]✗[/red] Anthropic API error: {e}")
            ok = False

    # 3. Config file
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                cfg = json.load(f)
            output.console.print(f"[green]✓[/green] Config file OK ({CONFIG_FILE})")
        except json.JSONDecodeError as e:
            output.console.print(f"[red]✗[/red] Config file has invalid JSON: {e}")
            ok = False
    else:
        output.console.print(f"[dim]–[/dim] No config file (using defaults) — run [cyan]errex --setup[/cyan] to create one")

    # 4. History file
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, encoding="utf-8", errors="replace") as f:
            count = sum(1 for line in f if line.strip())
        output.console.print(f"[green]✓[/green] History file OK ({count} entries at {HISTORY_FILE})")
    else:
        output.console.print("[dim]–[/dim] No history file yet (created on first use)")

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
            output.console.print(f"[green]✓[/green] errex {current} is up to date")
        else:
            output.console.print(f"[yellow]![/yellow] errex {current} → {latest} available ([dim]pip install --upgrade errex[/dim])")
    except Exception:
        output.console.print("[dim]–[/dim] Could not check PyPI for updates")

    output.console.print()
    if ok:
        output.console.rule("[green]All checks passed[/green]")
    else:
        output.console.rule("[red]Some checks failed — see above[/red]")
        sys.exit(1)


def print_email_report_cron(email: str, period: str = "weekly") -> None:
    """Print cron entries for automated health reports."""
    cron_entries = {
        "daily":   "0 8 * * *",
        "weekly":  "0 8 * * 1",
        "monthly": "0 8 1 * *",
    }
    schedule = cron_entries.get(period, "0 8 * * 1")
    cmd = f"errex --email-report {email} --report-period {period}"
    from rich.console import Console
    Console().print(f"\nAdd to crontab ([dim]crontab -e[/dim]):\n\n[cyan]{schedule} {cmd}[/cyan]\n")


def install_shell() -> None:
    shell = os.environ.get("SHELL", "")
    rc_file = Path.home() / (".zshrc" if "zsh" in shell else ".bashrc")
    with open(rc_file, "a") as f:
        f.write(_constants.SHELL_FUNCTION)
    output.console.print(f"[green]Added errex-last() to {rc_file}[/green]")
    output.console.print(f"[dim]Restart your shell or run: source {rc_file}[/dim]")
    output.console.print("[dim]Then use: errex-last  (after any failed command)[/dim]")


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

    output.console.print("[bold]Scanning for recent error logs…[/bold]\n")
    candidates: list = []

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
        output.console.print("[yellow]No error logs found in common locations.[/yellow]")
        output.console.print("[dim]Try: errex --watch /path/to/your.log[/dim]")
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

    output.console.print(table)
    output.console.print()

    try:
        choice = input("Pick a file to explain (1–{}, or q to quit): ".format(len(top))).strip()
        if choice.lower() == "q" or not choice:
            return
        idx = int(choice) - 1
        if not 0 <= idx < len(top):
            output.console.print("[red]Invalid choice.[/red]")
            return
        chosen = top[idx][1]
        output.console.print(f"\n[dim]Reading {chosen}…[/dim]\n")
        error_text = chosen.read_text(encoding="utf-8", errors="replace").strip()
        if len(error_text) > 8000:
            error_text = error_text[-8000:]  # use the tail where errors usually are
        explain_error(error_text, model=load_config()["model"])
    except (ValueError, KeyboardInterrupt):
        output.console.print("\n[dim]Cancelled.[/dim]")


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
        "--explain-sql", "--list-named", "--run", "--delete-profile", "--pin", "--unpin",
        "--redact", "--explain-yaml", "--filter", "--export-csv", "--perf",
        "--explain-dockerfile", "--search", "--inline", "--dedup", "--last",
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
        output.err_console.print(f"[red]errex: unknown shell '{shell}'. Use bash or zsh.[/red]")
        sys.exit(1)

    print(script.strip())


def run_command(cmd: str, model: str, brief: bool, lang: str | None, copy: bool, show_tokens: bool) -> None:
    """Run a shell command and explain its output if it fails."""
    output.console.print(f"[bold]Running:[/bold] [cyan]{cmd}[/cyan]\n")

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    cmd_output = (result.stdout + "\n" + result.stderr).strip()

    if result.returncode == 0:
        output.console.print("[green]Command succeeded (exit 0) — nothing to explain.[/green]")
        if cmd_output:
            output.console.print(f"\n[dim]{cmd_output[:200]}{'...' if len(cmd_output) > 200 else ''}[/dim]")
        return

    output.console.print(f"[yellow]Failed (exit {result.returncode})[/yellow]\n")
    if not cmd_output:
        output.console.print("[dim]No output captured — explaining the exit code.[/dim]\n")
        explain_exit_code(result.returncode, model=model, copy=copy)
        return

    explain_error(cmd_output, model=model, brief=brief, lang=lang, copy=copy, show_tokens=show_tokens)


def rerun_last_command(model: str, brief: bool, lang: str | None, copy: bool, show_tokens: bool) -> None:
    """Read the last shell command, re-run it, and explain if it fails."""
    shell = os.environ.get("SHELL", "")
    cmd: str | None = None

    if "zsh" in shell:
        histfile = Path(os.environ.get("HISTFILE", str(Path.home() / ".zsh_history")))
        if histfile.exists():
            content = histfile.read_text(encoding="utf-8", errors="replace")
            for line in reversed(content.splitlines()):
                line = line.strip()
                if not line:
                    continue
                if line.startswith(": ") and ";" in line:
                    line = line.split(";", 1)[1].strip()
                if line and not line.startswith("errex"):
                    cmd = line
                    break
    elif "bash" in shell:
        histfile = Path(os.environ.get("HISTFILE", str(Path.home() / ".bash_history")))
        if histfile.exists():
            for line in reversed(histfile.read_text(errors="replace").splitlines()):
                line = line.strip()
                if line and not line.startswith("errex") and not line.startswith("#"):
                    cmd = line
                    break

    if not cmd:
        output.err_console.print("[red]errex: could not read last command from shell history.[/red]")
        output.err_console.print("[dim]Tip: errex --install-shell sets up errex-last() which works more reliably.[/dim]")
        sys.exit(1)

    output.console.print(f"[bold]Re-running:[/bold] [cyan]{cmd}[/cyan]")
    try:
        ans = input("Proceed? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        output.console.print("\n[dim]Cancelled.[/dim]")
        return
    if ans not in ("", "y"):
        output.console.print("[dim]Cancelled.[/dim]")
        return

    output.console.print()
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    cmd_output = (result.stdout + "\n" + result.stderr).strip()

    if result.returncode == 0:
        output.console.print("[green]Command succeeded (exit 0) — nothing to explain.[/green]")
        return

    output.console.print(f"[yellow]Failed (exit {result.returncode})[/yellow]\n")
    if not cmd_output:
        output.console.print("[dim]No output captured.[/dim]")
        return

    explain_error(cmd_output, model=model, brief=brief, lang=lang, copy=copy, show_tokens=show_tokens)


def open_last_in_browser() -> None:
    """Export the last history entry as HTML and open it in the default browser."""
    import tempfile
    import webbrowser

    if not HISTORY_FILE.exists():
        output.console.print("[yellow]No history yet.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        output.console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    e = entries[-1]
    ts = e.get("timestamp", "")[:19]
    model = e.get("model", "")
    error = e.get("error", "")
    explanation = e.get("explanation", "")
    name = e.get("name", "")
    notes = e.get("notes", "")
    rating = e.get("rating")

    stars = ("★" * rating + "☆" * (5 - rating)) if rating else ""
    name_html = f" · <strong>{name}</strong>" if name else ""
    rating_html = f" · {stars}" if stars else ""
    notes_html = f'<div class="note">📝 {notes}</div>' if notes else ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>errex — {ts}</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
  body{{font-family:-apple-system,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;background:#0f1117;color:#e2e8f0}}
  h1{{color:#7dd3fc;font-size:1.1rem;margin-bottom:.25rem}}
  .meta{{color:#64748b;font-size:.85rem;margin-bottom:1.25rem}}
  .err{{background:#1e2130;border-radius:6px;padding:.75rem;font-family:monospace;font-size:.85rem;color:#f87171;white-space:pre-wrap;margin-bottom:1.5rem}}
  .note{{background:#1e3a5f;border-left:3px solid #60a5fa;padding:.5rem 1rem;border-radius:4px;margin:1rem 0;font-size:.9rem}}
  .explanation{{line-height:1.7}}
  h2,h3{{color:#7dd3fc}} code{{background:#1e2130;padding:.1em .4em;border-radius:4px;color:#86efac}}
  pre{{background:#1e2130;padding:1rem;border-radius:6px;overflow-x:auto}}
</style>
</head>
<body>
<h1>errex — Error Explanation</h1>
<div class="meta">{ts} · {model}{name_html}{rating_html}</div>
<div class="err">{error}</div>
{notes_html}
<div class="explanation" id="c"></div>
<script>document.getElementById('c').innerHTML=marked.parse({json.dumps(explanation)});</script>
</body></html>"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp = f.name

    webbrowser.open(f"file://{tmp}")
    output.console.print(f"[green]Opened in browser[/green] [dim]({tmp})[/dim]")


_AUTO_EXPLAIN_SNIPPET = """\
_errex_trap() { local rc=$?; [ $rc -ne 0 ] && errex --explain-exit $rc 2>/dev/null; }
trap '_errex_trap' ERR
"""

_AUTO_EXPLAIN_INSTRUCTIONS = """\
Add the following snippet to your shell config file to automatically explain
non-zero exit codes whenever a command fails:

  For bash: add to ~/.bashrc
  For zsh:  add to ~/.zshrc

Snippet:
"""


def install_auto_explain() -> None:
    """Print the auto-explain shell snippet and setup instructions."""
    from rich.panel import Panel
    from rich.syntax import Syntax

    output.console.rule("[bold cyan]errex — Auto-Explain Shell Integration[/bold cyan]")
    output.console.print()
    output.console.print(_AUTO_EXPLAIN_INSTRUCTIONS)
    output.console.print(
        Panel(
            Syntax(_AUTO_EXPLAIN_SNIPPET, "bash", theme="monokai", line_numbers=False),
            title="Shell snippet",
            expand=False,
        )
    )
    output.console.print(
        "\n[dim]After adding, restart your shell or run: source ~/.bashrc (or ~/.zshrc)[/dim]"
    )
    output.console.print(
        "[dim]Once active, any command that fails will automatically have its exit code explained.[/dim]\n"
    )
