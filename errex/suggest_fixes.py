"""AI-powered fix suggestions for scan findings using Claude."""
from __future__ import annotations

import os
import sys

from . import output, _constants


def suggest_fixes(
    model: str | None = None,
    severity: str | None = None,
    copy: bool = False,
    show_tokens: bool = False,
    perf: bool = False,
) -> None:
    from .scan import run_scan, detect_platform
    from .scanners._base import SEVERITIES

    if not os.environ.get("ANTHROPIC_API_KEY"):
        output.err_console.print("[red]errex: ANTHROPIC_API_KEY required for --suggest-fixes[/red]")
        sys.exit(1)

    model = model or os.environ.get("ERREX_MODEL") or _constants.DEFAULT_MODEL
    sev_idx = SEVERITIES.index(severity) if severity and severity in SEVERITIES else len(SEVERITIES) - 1

    output.console.print("[dim]Running scan to identify current findings…[/dim]")
    plat = detect_platform()
    result = run_scan(plat, progress_cb=None)

    findings = [
        f for f in result.findings
        if SEVERITIES.index(f.severity) <= sev_idx
    ]

    if not findings:
        output.console.print("[green]✓ No findings to fix — your system looks clean![/green]")
        return

    output.console.print(f"[bold]Found {len(findings)} issue(s). Asking Claude for fixes…[/bold]\n")

    findings_text = ""
    for i, f in enumerate(findings[:15], 1):
        findings_text += (
            f"{i}. [{f.severity.upper()}] {f.title}\n"
            f"   Detail: {f.detail[:200]}\n"
            f"   Platform: {f.platform}\n"
        )
        if f.fix_cmd:
            findings_text += f"   Existing fix hint: {f.fix_cmd}\n"
        findings_text += "\n"

    prompt = (
        f"You are a systems administrator. Given these security scan findings from a {plat} system, "
        f"provide a concrete fix for each one.\n\n"
        f"For each finding, provide:\n"
        f"1. The exact shell command(s) to fix it\n"
        f"2. What the command does (one sentence)\n"
        f"3. Any risks or prerequisites\n\n"
        f"Findings:\n{findings_text}\n"
        f"Format each fix as:\n"
        f"### Finding N: <title>\n"
        f"```bash\n<command>\n```\n"
        f"<explanation>\n"
    )

    from .core import call_claude

    response, in_tok, out_tok, elapsed = call_claude(
        prompt, model=model, messages=[{"role": "user", "content": prompt}],
    )
    output.console.print()

    if show_tokens or perf:
        output.console.print(f"[dim]tokens: {in_tok} in / {out_tok} out[/dim]")
    if perf and elapsed > 0:
        output.console.print(f"[dim]{elapsed:.1f}s  ({out_tok / elapsed:.0f} tok/s)[/dim]")

    if copy:
        try:
            import subprocess
            subprocess.run(["pbcopy"], input=response.encode(), check=True)
            output.console.print("[green]✓ Copied to clipboard[/green]")
        except Exception:
            pass
