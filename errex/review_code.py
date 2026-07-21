"""Review a local source file using Claude — bugs, security, style."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import anthropic

from . import output, _constants

_REVIEW_PROMPT = (
    "You are a senior software engineer performing a thorough code review. "
    "Analyse the code and provide a structured report:\n\n"
    "1. **Bugs & Correctness** — logic errors, off-by-ones, null/undefined risks, "
    "unhandled exceptions\n"
    "2. **Security** — injection risks, secrets in code, insecure defaults, "
    "privilege issues\n"
    "3. **Style & Maintainability** — naming, dead code, overly complex sections, "
    "missing docs\n"
    "4. **Performance** — unnecessary allocations, N+1 queries, blocking calls\n"
    "5. **Summary verdict** — one sentence overall rating\n\n"
    "For each issue: state severity (🔴 Critical / 🟡 Warning / 🔵 Info), "
    "line range, description, and fix suggestion.\n"
    "If the file looks clean, say so briefly. Use markdown. Be direct and specific."
)


def review_code(
    path: str,
    model: str | None = None,
    copy: bool = False,
    show_tokens: bool = False,
    perf: bool = False,
) -> None:
    """Review a source file with Claude and print a structured report."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        output.err_console.print(
            "[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]"
        )
        sys.exit(1)

    model = model or os.environ.get("ERREX_MODEL") or _constants.CONFIG_DEFAULTS["model"]

    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        output.err_console.print(f"[red]errex: file not found: {path!r}[/red]")
        sys.exit(1)
    except OSError as e:
        output.err_console.print(f"[red]errex: cannot read {path!r}: {e}[/red]")
        sys.exit(1)

    lang = Path(path).suffix.lstrip(".") or "text"
    max_chars = 12000
    truncated = len(content) > max_chars
    snippet = content[:max_chars]

    prompt = (
        f"Review this `{lang}` file (`{Path(path).name}`):\n\n"
        f"```{lang}\n{snippet}\n```"
    )
    if truncated:
        prompt += f"\n\n_(file truncated — {len(content):,} chars total)_"

    output.console.rule(f"[bold cyan]errex — Code Review: {Path(path).name}[/bold cyan]")
    print()

    client = anthropic.Anthropic(timeout=_constants.API_TIMEOUT)
    collected: list[str] = []
    input_tokens = output_tokens = 0
    t0 = time.time()
    try:
        with client.messages.stream(
            model=model,
            max_tokens=2048,
            system=[
                {
                    "type": "text",
                    "text": _REVIEW_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                collected.append(text)
            final = stream.get_final_message()
            input_tokens = final.usage.input_tokens
            output_tokens = final.usage.output_tokens
    except anthropic.APIError as e:
        output.err_console.print(f"\n[red]errex: API error — {e}[/red]")
        sys.exit(2)

    response = "".join(collected)
    print()
    if show_tokens:
        output.show_token_usage(input_tokens, output_tokens)
    if perf:
        output.show_perf(time.time() - t0, output_tokens)
    output.console.rule(style="dim")
    print()

    if copy:
        output.copy_to_clipboard(response)
