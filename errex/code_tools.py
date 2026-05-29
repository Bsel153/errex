from __future__ import annotations

import os
import sys
import time
import re
from pathlib import Path

import anthropic
from . import output, _constants
from .history import save_history
from .utils import read_file
from .core import explain_error, chat_loop


def explain_diff(diff_text: str, model: str, lang: str | None, copy: bool, show_tokens: bool, perf: bool = False) -> None:
    """Explain what a git diff changes and what could break."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        output.err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    lang_hint = f" (primary language: {lang})" if lang else ""
    prompt = f"Please explain this diff{lang_hint}:\n\n```diff\n{diff_text}\n```"

    output.console.rule("[bold cyan]errex — Diff Explanation[/bold cyan]")
    print()

    client = anthropic.Anthropic(timeout=_constants.API_TIMEOUT)
    collected = []
    input_tokens = output_tokens = 0
    t0 = time.time()
    try:
        with client.messages.stream(
            model=model,
            max_tokens=2048,
            system=[{"type": "text", "text": _constants.DIFF_PROMPT, "cache_control": {"type": "ephemeral"}}],
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

    save_history(diff_text[:200], response, model, False)
    if copy:
        output.copy_to_clipboard(response)


def lint_file(path: str, model: str, lang: str | None, copy: bool, show_tokens: bool, perf: bool = False) -> None:
    """Scan a code file for potential bugs and issues."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        output.err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    code = read_file(path)
    lang_hint = f" (language: {lang})" if lang else ""
    prompt = f"Please review this code{lang_hint} for potential issues:\n\n```\n{code}\n```"

    output.console.rule(f"[bold cyan]errex — Lint: {Path(path).name}[/bold cyan]")
    print()

    client = anthropic.Anthropic(timeout=_constants.API_TIMEOUT)
    collected = []
    input_tokens = output_tokens = 0
    t0 = time.time()
    try:
        with client.messages.stream(
            model=model,
            max_tokens=2048,
            system=[{"type": "text", "text": _constants.LINT_PROMPT, "cache_control": {"type": "ephemeral"}}],
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

    save_history(code, response, model, False)
    if copy:
        output.copy_to_clipboard(response)


def explain_code(path: str, model: str, lang: str | None, copy: bool, show_tokens: bool, chat: bool, perf: bool = False) -> None:
    """Explain what a piece of code does."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        output.err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    code = read_file(path)
    lang_hint = f" (language: {lang})" if lang else ""
    prompt = f"Please explain this code{lang_hint}:\n\n```\n{code}\n```"

    output.console.rule("[bold cyan]errex — Code Explanation[/bold cyan]")
    print()

    client = anthropic.Anthropic(timeout=_constants.API_TIMEOUT)
    collected = []
    input_tokens = output_tokens = 0
    t0 = time.time()
    try:
        with client.messages.stream(
            model=model,
            max_tokens=2048,
            system=[{"type": "text", "text": _constants.CODE_PROMPT, "cache_control": {"type": "ephemeral"}}],
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

    save_history(code, response, model, False)
    if copy:
        output.copy_to_clipboard(response)

    if chat and sys.stdin.isatty():
        # reuse chat_loop — treat code as the "error" context
        chat_loop(code, response, model, lang)


def generate_test(code_path: str, error_text: str | None, model: str, lang: str | None, copy: bool, show_tokens: bool, perf: bool = False) -> None:
    """Generate a test case from a code file, optionally reproducing an error."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        output.err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
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

    output.console.rule(f"[bold cyan]errex — Test Gen: {Path(code_path).name}[/bold cyan]")
    print()

    client = anthropic.Anthropic(timeout=_constants.API_TIMEOUT)
    collected = []
    input_tokens = output_tokens = 0
    t0 = time.time()
    try:
        with client.messages.stream(
            model=model,
            max_tokens=2048,
            system=[{"type": "text", "text": _constants.TEST_GEN_PROMPT, "cache_control": {"type": "ephemeral"}}],
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

    save_history(code[:200], response, model, False)
    if copy:
        output.copy_to_clipboard(response)


def explain_inline(path: str, line_num: int, model: str, copy: bool, show_tokens: bool, perf: bool = False) -> None:
    """Explain a specific line of a code file in context."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        output.err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    code = read_file(path)
    lines = code.splitlines()

    if line_num < 1 or line_num > len(lines):
        output.err_console.print(f"[red]errex: line {line_num} is out of range (file has {len(lines)} lines)[/red]")
        sys.exit(1)

    ctx_start = max(0, line_num - 16)
    ctx_end = min(len(lines), line_num + 15)
    ctx_lines = []
    for i in range(ctx_start, ctx_end):
        marker = "▶ " if i == line_num - 1 else "  "
        ctx_lines.append(f"{marker}{i + 1:4d}  {lines[i]}")

    context_block = "\n".join(ctx_lines)
    prompt = (
        f"Here is an excerpt from `{Path(path).name}` with line {line_num} marked with ▶:\n\n"
        f"```\n{context_block}\n```\n\n"
        f"Please explain line {line_num}."
    )

    output.console.rule(f"[bold cyan]errex — Inline: {Path(path).name}:{line_num}[/bold cyan]")
    print()

    client = anthropic.Anthropic(timeout=_constants.API_TIMEOUT)
    collected = []
    input_tokens = output_tokens = 0
    t0 = time.time()
    try:
        with client.messages.stream(
            model=model,
            max_tokens=1024,
            system=[{"type": "text", "text": _constants.INLINE_PROMPT, "cache_control": {"type": "ephemeral"}}],
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

    save_history(f"{path}:{line_num} — {lines[line_num - 1].strip()[:100]}", response, model, False)
    if copy:
        output.copy_to_clipboard(response)


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
        output.err_console.print(f"[red]errex: invalid pattern '{pattern}': {e}[/red]")
        sys.exit(1)

    matched = [line for line in content.splitlines() if rx.search(line)]
    if not matched:
        output.console.print(f"[yellow]No lines matching '{pattern}' in {path}.[/yellow]")
        sys.exit(0)

    excerpt = "\n".join(matched[:200])  # cap at 200 lines
    output.console.print(f"[dim]Found {len(matched)} matching line(s) — explaining…[/dim]\n")
    explain_error(
        excerpt,
        model=model,
        lang=lang,
        copy=copy,
        show_tokens=show_tokens,
    )


def summarize_log(path: str, model: str, copy: bool, show_tokens: bool, perf: bool = False) -> None:
    """Produce a digest of all distinct errors in a log file."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        output.err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    content = read_file(path)
    if len(content) > 8000:
        content = content[-8000:]
        output.console.print("[dim](log is large — using the last 8000 chars where errors typically appear)[/dim]")

    prompt = f"Analyze this log file and produce a diagnostic digest:\n\n```\n{content}\n```"

    output.console.rule(f"[bold cyan]errex — Log Summary: {Path(path).name}[/bold cyan]")
    print()

    client = anthropic.Anthropic(timeout=_constants.API_TIMEOUT)
    collected = []
    input_tokens = output_tokens = 0
    t0 = time.time()
    try:
        with client.messages.stream(
            model=model,
            max_tokens=1024,
            system=[{"type": "text", "text": _constants.LOG_SUMMARY_PROMPT, "cache_control": {"type": "ephemeral"}}],
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

    save_history(content[:200], response, model, False)
    if copy:
        output.copy_to_clipboard(response)
