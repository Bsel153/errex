from __future__ import annotations

import os
import sys
import time
import json
import re
from pathlib import Path
from datetime import datetime

import anthropic
from . import output, _constants
from ._paths import HISTORY_FILE
from .history import save_history
from .patterns import match_pattern
from .cache import get_cached, save_cached
from .utils import (read_file, get_error_input, share_explanation,
                    post_webhook, search_github_issues, notify, extract_snippet,
                    format_json_error, redact_secrets, get_env_info)


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
    top_n: int | None = None,
) -> tuple:
    """Send error to Claude, stream to stdout, return (response, input_tokens, output_tokens, elapsed_seconds)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        output.err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    client = anthropic.Anthropic(timeout=_constants.API_TIMEOUT)
    lang_hint = f" (language: {lang})" if lang else ""
    context_block = f"\n\nFor context, here is the relevant code:\n```\n{context}\n```" if context else ""
    translate_suffix = f"\n\nRespond entirely in {translate}." if translate else ""
    top_n_suffix = f"\n\nLimit your root cause analysis to the top {top_n} most likely causes only." if top_n else ""

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
            prompt = f"Please explain this error{lang_hint}:\n\n```\n{error_text}\n```{context_block}{translate_suffix}{top_n_suffix}"
        messages = [{"role": "user", "content": prompt}]

    if dry_run:
        output.console.rule("[bold yellow]errex — Debug (dry run)[/bold yellow]")
        output.console.print(f"\n[bold]Model:[/bold] {model}  [bold]Max tokens:[/bold] {64 if terse else (256 if brief else 2048)}\n")
        output.console.rule("[dim]System prompt[/dim]")
        output.console.print(_constants.SYSTEM_PROMPT)
        output.console.rule("[dim]User prompt[/dim]")
        output.console.print(messages[-1]["content"])
        output.console.rule(style="dim")
        return "", 0, 0, 0.0

    collected = []
    input_tokens = output_tokens = 0
    t0 = time.time()
    try:
        with client.messages.stream(
            model=model,
            max_tokens=64 if terse else (256 if brief else 2048),
            system=[{"type": "text", "text": _constants.SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
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
        output.err_console.print(f"\n[red]errex: API error — {e}[/red]")
        sys.exit(2)

    return "".join(collected), input_tokens, output_tokens, time.time() - t0


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
    top_n: int | None = None,
    perf: bool = False,
    no_cache: bool = False,
    use_cache: bool = True,
    no_history: bool = False,
    slack_explain_url: str | None = None,
) -> None:
    """Explain an error, render output, save history."""
    from .init_cmd import load_project_context, format_context as _fmt_ctx
    _proj_ctx = load_project_context()
    if _proj_ctx:
        _ctx_str = _fmt_ctx(_proj_ctx)
        if _ctx_str:
            error_text = f"[Project context: {_ctx_str}]\n\n{error_text}"

    # Try the local pattern cache before hitting the API
    if not no_cache and not json_output and not fix and not dry_run and not terse:
        hit = match_pattern(error_text)
        if hit:
            from rich.markdown import Markdown
            title, explanation = hit
            output.console.rule(f"[bold cyan]errex — {title}[/bold cyan]")
            print()
            output.console.print(Markdown(explanation))
            print()
            output.console.print("[dim]⚡ matched local pattern — use --no-cache to force Claude[/dim]")
            output.console.rule(style="dim")
            print()
            if not no_history:
                save_history(error_text, explanation, "local", brief, name=save_as)
            if output_file:
                Path(output_file).write_text(explanation, encoding="utf-8")
            if copy:
                output.copy_to_clipboard(explanation)
            return

    if not json_output and not dry_run:
        output.console.rule("[bold cyan]errex — Error Analysis[/bold cyan]")
        print()

    if use_cache and not json_output and not fix and not dry_run:
        cached = get_cached(error_text, model, brief, terse)
        if cached:
            from rich.markdown import Markdown
            output.console.print(Markdown(cached))
            print()
            output.console.print("[dim]📦 cached response — use --no-cache to call Claude[/dim]")
            output.console.rule(style="dim")
            print()
            if not no_history:
                save_history(error_text, cached, model, brief, name=save_as)
            if output_file:
                Path(output_file).write_text(cached, encoding="utf-8")
            if copy:
                output.copy_to_clipboard(cached)
            return

    response, in_tok, out_tok, elapsed = call_claude(
        error_text, model=model, brief=brief, terse=terse, json_output=json_output,
        fix=fix, lang=lang, context=context, translate=translate, dry_run=dry_run,
        top_n=top_n,
    )

    if dry_run:
        return

    if use_cache and response and not json_output and not fix:
        save_cached(error_text, model, brief, terse, response)

    if json_output:
        try:
            parsed = json.loads(response)
            print(json.dumps(parsed, indent=2))
        except json.JSONDecodeError:
            print(response)
    else:
        print()
        if show_tokens:
            output.show_token_usage(in_tok, out_tok)
        if perf:
            output.show_perf(elapsed, out_tok)
        output.console.rule(style="dim")
        print()

    if not no_history:
        save_history(error_text, response, model, brief, name=save_as)

    if output_file:
        out = Path(output_file)
        out.write_text(response, encoding="utf-8")
        output.err_console.print(f"[dim](saved to {out.resolve()})[/dim]")

    if copy:
        output.copy_to_clipboard(response)

    if share:
        share_explanation(error_text, response)

    if do_notify:
        notify("errex", f"Error explained: {error_text[:60]}")

    if issues:
        search_github_issues(error_text)

    if webhook:
        post_webhook(webhook, error_text, response, model)

    if slack_explain_url and response:
        from .slack_notify import notify_explanation
        notify_explanation(response, error_text[:200], slack_explain_url)

    if chat and sys.stdin.isatty():
        chat_loop(error_text, response, model, lang)


def compare_errors(files: list, model: str, lang: str | None, copy: bool) -> None:
    """Explain multiple errors and analyse whether they share a root cause."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        output.err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
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

    output.console.rule(f"[bold cyan]errex — Comparing {len(errors)} errors[/bold cyan]")
    print()

    client = anthropic.Anthropic(timeout=_constants.API_TIMEOUT)
    collected = []
    try:
        with client.messages.stream(
            model=model,
            max_tokens=3000,
            system=[{"type": "text", "text": _constants.SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                collected.append(text)
    except anthropic.APIError as e:
        output.err_console.print(f"\n[red]errex: API error — {e}[/red]")
        sys.exit(2)

    print()
    output.console.rule(style="dim")
    print()

    full_response = "".join(collected)
    combined_error = " | ".join(f"{p}: {t[:100]}" for p, t in errors)
    save_history(combined_error, full_response, model, False)

    if copy:
        output.copy_to_clipboard(full_response)


def chat_loop(error_text: str, initial_response: str, model: str, lang: str | None) -> None:
    """After the initial explanation, let the user ask follow-up questions."""
    lang_hint = f" (language: {lang})" if lang else ""
    history = [
        {"role": "user", "content": f"Please explain this error{lang_hint}:\n\n```\n{error_text}\n```"},
        {"role": "assistant", "content": initial_response},
    ]
    output.console.print("[dim]Ask a follow-up question, or press Ctrl+C to exit.[/dim]\n")
    while True:
        try:
            question = input("You: ").strip()
            if not question:
                continue
            history.append({"role": "user", "content": question})
            print()
            output.console.rule("[dim]errex[/dim]")
            print()
            response, in_tok, out_tok, _elapsed = call_claude(
                error_text, model=model, lang=lang, messages=history
            )
            history.append({"role": "assistant", "content": response})
            print()
            output.show_token_usage(in_tok, out_tok)
            output.console.rule(style="dim")
            print()
        except (KeyboardInterrupt, EOFError):
            output.console.print("\n[dim]Exiting chat.[/dim]")
            break


def ask_about_last(question: str, model: str, show_tokens: bool, copy: bool) -> None:
    """Ask a follow-up question about the last error in history."""
    if not HISTORY_FILE.exists():
        output.console.print("[yellow]No history yet — run errex on an error first.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        output.console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    last = entries[-1]
    error = last.get("error", "")
    explanation = last.get("explanation", "")
    ts = last.get("timestamp", "")[:19]

    output.console.print(f"[dim]Context:[/dim] {error[:80]}{'...' if len(error) > 80 else ''}  [dim]({ts})[/dim]\n")

    messages = [
        {"role": "user", "content": f"Please explain this error:\n\n```\n{error}\n```"},
        {"role": "assistant", "content": explanation},
        {"role": "user", "content": question},
    ]

    output.console.rule("[bold cyan]errex — Follow-up[/bold cyan]")
    print()

    response, in_tok, out_tok, _elapsed = call_claude(error, model=model, messages=messages)

    print()
    if show_tokens:
        output.show_token_usage(in_tok, out_tok)
    output.console.rule(style="dim")
    print()

    save_history(error, response, model, False)
    if copy:
        output.copy_to_clipboard(response)


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
        output.console.print("[yellow]No history yet — run errex on an error first.[/yellow]")
        sys.exit(0)

    with open(HISTORY_FILE, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        output.console.print("[yellow]History is empty.[/yellow]")
        sys.exit(0)

    last = entries[-1]
    error = last.get("error", "")
    ts = last.get("timestamp", "")[:19]

    output.console.print(f"[dim]Retrying:[/dim] {error[:80]}{'...' if len(error) > 80 else ''}  [dim]({ts})[/dim]\n")

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
    import re as _re
    content = read_file(path)
    blocks = [b.strip() for b in _re.split(r"\n{2,}", content) if b.strip()]

    if not blocks:
        output.console.print(f"[yellow]No error blocks found in {path}.[/yellow]")
        return

    output.console.print(f"[bold]{len(blocks)} error block{'s' if len(blocks) != 1 else ''}[/bold] found in [cyan]{Path(path).name}[/cyan]\n")

    for i, block in enumerate(blocks, 1):
        output.console.rule(f"[bold cyan]Block {i} of {len(blocks)}[/bold cyan]")
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



# ---------------------------------------------------------------------------
# apply_fix helpers
# ---------------------------------------------------------------------------

def _apply_unified_diff(diff_text: str, filepath: str, yes: bool) -> bool:
    """Display and apply a unified diff to filepath. Returns True on success."""
    import shutil
    import subprocess as _sp

    output.console.print("\n[bold]Proposed diff:[/bold]")
    for line in diff_text.splitlines()[:40]:
        if line.startswith('+') and not line.startswith('+++'):
            output.console.print(f"[green]{line}[/green]")
        elif line.startswith('-') and not line.startswith('---'):
            output.console.print(f"[red]{line}[/red]")
        else:
            output.console.print(f"[dim]{line}[/dim]")

    if not yes:
        try:
            answer = input("\nApply this patch? [y/N] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            output.console.print("\n[dim]Aborted.[/dim]")
            return False
        if answer not in ("y", "yes"):
            output.console.print("[dim]Skipped.[/dim]")
            return False

    bak = filepath + ".bak"
    shutil.copy2(filepath, bak)

    result = _sp.run(['patch', '-p0', filepath], input=diff_text, text=True, capture_output=True)
    if result.returncode == 0:
        output.console.print(f"[green]✓ Patched {filepath} (backup: {bak})[/green]")
        return True
    else:
        output.console.print(f"[yellow]patch failed, trying manual apply…[/yellow]")
        shutil.copy2(bak, filepath)
        output.console.print(f"[red]✗ Could not apply patch automatically. Backup restored.[/red]")
        return False


def _apply_full_replacement(new_content: str, filepath: str, yes: bool) -> bool:
    """Display and write a full file replacement. Returns True on success."""
    import shutil

    output.console.print(f"\n[bold]Proposed replacement for {filepath}:[/bold]")
    lines = new_content.splitlines()
    preview = lines[:20]
    for line in preview:
        output.console.print(f"  {line}")
    if len(lines) > 20:
        output.console.print(f"  [dim]... ({len(lines) - 20} more lines)[/dim]")

    if not yes:
        try:
            answer = input(f"\nReplace {filepath} with this content? [y/N] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            output.console.print("\n[dim]Aborted.[/dim]")
            return False
        if answer not in ("y", "yes"):
            output.console.print("[dim]Skipped.[/dim]")
            return False

    bak = filepath + ".bak"
    shutil.copy2(filepath, bak)
    Path(filepath).write_text(new_content, encoding="utf-8")
    output.console.print(f"[green]✓ Updated {filepath} (backup: {bak})[/green]")
    return True


def _maybe_open_ticket(
    error_text: str,
    explanation: str,
    username: str | None,
    password: str | None,
    product: str,
    version: str,
    severity: int,
) -> None:
    from .ticketing import open_rht_ticket
    output.console.print("\n[yellow]Fix did not succeed — opening Red Hat support case…[/yellow]")
    open_rht_ticket(
        error_text,
        explanation,
        username=username,
        password=password,
        product=product,
        version=version,
        severity=severity,
    )


def apply_fix(
    error_text: str,
    model: str,
    lang: str | None = None,
    context: str | None = None,
    yes: bool = False,
    open_ticket: bool = False,
    rht_username: str | None = None,
    rht_password: str | None = None,
    rht_product: str = "Red Hat Enterprise Linux",
    rht_version: str = "9.0",
    rht_severity: int = 3,
) -> None:
    """Ask Claude for a fix and apply it.

    When context is a file path that exists, Claude is asked for a unified diff
    or full replacement of that file.  Otherwise, Claude outputs shell commands
    which are extracted and run.
    """
    import re as _re
    import subprocess as _sp

    output.console.rule("[bold cyan]errex — Fix Apply[/bold cyan]")
    print()

    context_path = context
    context_file_exists = context_path is not None and Path(context_path).exists()

    if context_file_exists:
        file_content = Path(context_path).read_text(encoding="utf-8", errors="replace")
        patch_prompt = (
            f"The file `{context_path}` contains code that causes this error. "
            f"Provide the minimal fix as a unified diff "
            f"(--- a/{context_path} +++ b/{context_path} format). "
            f"If a diff isn't possible, provide the complete corrected file content.\n\n"
            f"Error:\n```\n{error_text}\n```\n\n"
            f"Current file content:\n```\n{file_content}\n```"
        )
        response, _, _, _ = call_claude(
            error_text,
            model=model,
            lang=lang,
            messages=[{"role": "user", "content": patch_prompt}],
        )
        print()

        # Check for unified diff
        fix_applied = False
        if ('--- a/' in response or ('--- ' in response and '+++ ' in response)):
            fix_applied = _apply_unified_diff(response, context_path, yes)
        else:
            # Extract code block content and treat as full replacement
            code_match = _re.search(r'```(?:\w+)?\n(.*?)```', response, _re.DOTALL)
            if code_match:
                fix_applied = _apply_full_replacement(code_match.group(1), context_path, yes)
            else:
                output.console.print("[yellow]Could not parse a diff or code block from the response.[/yellow]")
                output.console.print("[dim]Try running without --context to get shell commands instead.[/dim]")

        if not fix_applied and open_ticket:
            _maybe_open_ticket(error_text, response, rht_username, rht_password, rht_product, rht_version, rht_severity)
        return

    # --- Shell-command path (no context file) ---
    response, _, _, _ = call_claude(error_text, model=model, lang=lang, fix=True)
    print()

    # Extract shell commands from code blocks
    blocks = _re.findall(r'```(?:sh|bash|shell)?\n(.*?)```', response, _re.DOTALL)
    if not blocks:
        blocks = _re.findall(r'`([^`\n]+)`', response)

    commands = []
    for block in blocks:
        for line in block.strip().splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                commands.append(line)

    if not commands:
        output.console.print("[yellow]No shell commands found in the response.[/yellow]")
        if open_ticket:
            _maybe_open_ticket(error_text, response, rht_username, rht_password, rht_product, rht_version, rht_severity)
        return

    output.console.print("\n[bold]Commands to run:[/bold]")
    for cmd in commands:
        output.console.print(f"  [cyan]{cmd}[/cyan]")

    if not yes:
        try:
            answer = input("\nRun these commands? [y/N] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            output.console.print("\n[dim]Aborted.[/dim]")
            return
        if answer not in ("y", "yes"):
            output.console.print("[dim]Skipped.[/dim]")
            return

    any_failed = False
    for cmd in commands:
        output.console.print(f"\n[dim]$ {cmd}[/dim]")
        result = _sp.run(cmd, shell=True, text=True)
        if result.returncode != 0:
            output.console.print(f"[red]✗ Command exited {result.returncode}[/red]")
            any_failed = True
        else:
            output.console.print(f"[green]✓ Done[/green]")

    if any_failed and open_ticket:
        _maybe_open_ticket(error_text, response, rht_username, rht_password, rht_product, rht_version, rht_severity)
