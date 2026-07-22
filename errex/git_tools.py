"""Git-related analysis tools — git blame explain."""
from __future__ import annotations

import os
import re
import subprocess
import sys

from . import output, _constants


def _run(cmd: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    """Run a subprocess and return (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"


def _in_git_repo() -> bool:
    rc, _, _ = _run(["git", "rev-parse", "--git-dir"])
    return rc == 0


def explain_git_blame(file_line: str, model: str | None = None) -> None:
    """Parse FILE:LINE, run git blame, explain via Claude why the code exists."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        output.err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    # Parse FILE:LINE
    m = re.match(r"^(.+):(\d+)$", file_line)
    if not m:
        output.err_console.print(
            f"[red]errex: expected FILE:LINE format, got: {file_line!r}[/red]"
        )
        sys.exit(1)

    filepath, line_str = m.group(1), m.group(2)
    line_num = int(line_str)

    if not _in_git_repo():
        output.err_console.print("[red]errex: not inside a git repository.[/red]")
        sys.exit(1)

    if not os.path.exists(filepath):
        output.err_console.print(f"[red]errex: file not found: {filepath}[/red]")
        sys.exit(1)

    output.console.print(f"[dim]Running git blame on {filepath}:{line_num}…[/dim]")

    rc, blame_out, blame_err = _run(
        ["git", "blame", "-L", f"{line_num},{line_num}", "--porcelain", filepath]
    )
    if rc != 0:
        output.err_console.print(f"[red]errex: git blame failed: {blame_err.strip()}[/red]")
        sys.exit(1)

    # Parse porcelain output
    commit_hash = ""
    author = ""
    author_date = ""
    summary = ""
    code_line = ""

    for bline in blame_out.splitlines():
        if re.match(r"^[0-9a-f]{40}", bline):
            commit_hash = bline.split()[0]
        elif bline.startswith("author "):
            author = bline[7:]
        elif bline.startswith("author-time "):
            try:
                import datetime
                ts = int(bline[12:])
                author_date = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            except Exception:
                author_date = bline[12:]
        elif bline.startswith("summary "):
            summary = bline[8:]
        elif bline.startswith("\t"):
            code_line = bline[1:]

    if not commit_hash:
        output.err_console.print("[red]errex: could not parse git blame output.[/red]")
        sys.exit(1)

    # Get commit stat
    rc2, stat_out, _ = _run(["git", "show", commit_hash, "--stat", "--oneline"])
    commit_context = stat_out[:2000] if rc2 == 0 else "(could not fetch commit details)"

    output.console.rule(f"[bold cyan]errex — Git Blame: {filepath}:{line_num}[/bold cyan]")
    output.console.print(f"\n[bold]Commit:[/bold]  [dim]{commit_hash[:12]}[/dim]")
    output.console.print(f"[bold]Author:[/bold]  {author}  [dim]{author_date}[/dim]")
    output.console.print(f"[bold]Summary:[/bold] {summary}")
    output.console.print(f"[bold]Code:[/bold]    [cyan]{code_line}[/cyan]\n")

    prompt = (
        f"Here is a line of code and its git history. "
        f"In 2-3 sentences, explain WHY this code exists — what problem it solves, "
        f"why it was written this way, or what change prompted it.\n\n"
        f"File: {filepath}, line {line_num}\n"
        f"Code: {code_line}\n\n"
        f"Commit: {commit_hash[:12]}\n"
        f"Author: {author}  ({author_date})\n"
        f"Commit message: {summary}\n\n"
        f"Commit context:\n{commit_context}\n\n"
        f"Be concise — 2 to 3 sentences maximum."
    )

    from .core import call_claude

    _model = model or os.environ.get("ERREX_MODEL") or _constants.CONFIG_DEFAULTS["model"]

    output.console.print("[bold]Why this code exists:[/bold]\n")
    call_claude(code_line, model=_model, messages=[{"role": "user", "content": prompt}])
    print()
    output.console.rule(style="dim")
    output.console.print()
