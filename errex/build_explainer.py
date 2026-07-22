"""Explain build failures from make, cargo, npm, gradle, maven, and go build."""
from __future__ import annotations

import os
import re
import sys
from typing import Optional

from rich.panel import Panel

from . import output


# ── Build system detection ───────────────────────────────────────────────────

_DETECTORS = [
    # (name, pattern, extractor)
    ("make",   re.compile(r"make: \*\*\*|Error 1"),
               re.compile(r"^.*(?:Error|error).*$", re.MULTILINE)),
    ("cargo",  re.compile(r"error\[E\d"),
               re.compile(r"^error(?:\[E\d+\])?.*$", re.MULTILINE)),
    ("npm",    re.compile(r"npm ERR!|error TS\d"),
               re.compile(r"^(?:npm ERR!|error TS\d).*$", re.MULTILINE)),
    ("yarn",   re.compile(r"yarn ERR!|error TS\d"),
               re.compile(r"^(?:error|yarn ERR!).*$", re.MULTILINE)),
    ("gradle", re.compile(r"FAILURE:|BUILD FAILURE"),
               re.compile(r"^> .*$|^.*FAILURE.*$", re.MULTILINE)),
    ("maven",  re.compile(r"BUILD FAILURE.*\[ERROR\]|\[ERROR\].*BUILD FAILURE", re.DOTALL),
               re.compile(r"^\[ERROR\].*$", re.MULTILINE)),
    ("go",     re.compile(r"undefined:|cannot use "),
               re.compile(r"^.*undefined:.*$|^.*cannot use.*$", re.MULTILINE)),
]

# ── Local explanations ────────────────────────────────────────────────────────

_LOCAL_SUMMARIES = {
    "make": (
        "make stopped because a recipe returned a non-zero exit code. "
        "The file:line references above show where the build failed. "
        "Check the compile error immediately before 'make: ***' for the root cause."
    ),
    "cargo": (
        "Rust compiler error(s) detected (E-codes above). "
        "Each error[EXXXX] has a detailed explanation — run `rustc --explain EXXXX` for help. "
        "Fix compilation errors from top to bottom; many later errors often disappear once the first is fixed."
    ),
    "npm": (
        "npm failed to install or build. ENOENT means a missing file/directory; "
        "EACCES means a permissions problem (try fixing npm prefix permissions). "
        "TypeScript TS errors indicate type mismatches — check tsconfig.json and type declarations."
    ),
    "yarn": (
        "Yarn encountered an error during install or build. "
        "Check for missing packages, lockfile conflicts, or TypeScript compilation errors listed above."
    ),
    "gradle": (
        "Gradle build failed. The '> Task :...' line above FAILURE shows which task failed. "
        "Expand the error details with --info or --stacktrace for the full cause."
    ),
    "maven": (
        "Maven build failed. [ERROR] lines above show compilation or test failures. "
        "Run 'mvn -e' for full exception details, or check the surefire-reports directory for test output."
    ),
    "go": (
        "Go build failed with type or symbol errors. "
        "'undefined: X' means X is not imported or does not exist in scope. "
        "'cannot use' means a type mismatch — check that you pass the correct type or pointer."
    ),
}


def _detect_build_system(text: str) -> tuple[str | None, list[str]]:
    """Return (tool_name, [error_lines]) or (None, []) if unknown."""
    for name, detect_re, extract_re in _DETECTORS:
        if detect_re.search(text):
            lines = extract_re.findall(text)
            return name, lines[:20]
    return None, []


def _file_refs(lines: list[str]) -> list[str]:
    """Extract file:line references from error lines."""
    ref_re = re.compile(r"[\w./\\-]+\.\w+:\d+")
    refs = []
    for line in lines:
        found = ref_re.findall(line)
        refs.extend(found)
    seen = set()
    unique = []
    for r in refs:
        if r not in seen:
            seen.add(r)
            unique.append(r)
    return unique[:10]


def explain_build(text: str, model: str | None = None) -> None:
    """Detect build system, extract errors, print rich panel. Falls back to Claude for unknown."""
    tool, error_lines = _detect_build_system(text)

    output.console.rule("[bold cyan]errex — Build Error Explainer[/bold cyan]")
    output.console.print()

    if tool:
        summary = _LOCAL_SUMMARIES[tool]
        refs = _file_refs(error_lines)

        lines_text = "\n".join(error_lines[:10]) if error_lines else "(no specific error lines extracted)"
        refs_text = "\n".join(refs) if refs else "  (none detected)"

        panel_body = (
            f"[bold]Build system:[/bold]  {tool}\n\n"
            f"[bold]Extracted error lines:[/bold]\n{lines_text}\n\n"
            f"[bold]File references:[/bold]\n{refs_text}\n\n"
            f"[bold]What this means:[/bold]\n{summary}"
        )
        output.console.print(Panel(panel_body, title=f"[red]{tool} build failure[/red]", expand=False))
    else:
        # Unknown — send to Claude
        if not os.environ.get("ANTHROPIC_API_KEY"):
            output.err_console.print("[red]errex: ANTHROPIC_API_KEY is not set and build system is unrecognized.[/red]")
            sys.exit(1)

        output.console.print("[dim]Unrecognized build system — asking Claude…[/dim]\n")
        from .core import call_claude
        from . import _constants
        _model = model or os.environ.get("ERREX_MODEL") or _constants.CONFIG_DEFAULTS["model"]

        prompt = (
            "The following is build output that appears to have failed. "
            "Identify the build system, extract the key error lines, explain what went wrong, "
            "and suggest how to fix it. Use markdown.\n\n"
            f"```\n{text[:6000]}\n```"
        )
        call_claude(text[:200], model=_model, messages=[{"role": "user", "content": prompt}])
        print()

    output.console.rule(style="dim")
    output.console.print()
