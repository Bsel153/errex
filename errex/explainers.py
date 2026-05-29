from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import anthropic
from . import output, _constants
from ._paths import HISTORY_FILE
from .history import save_history
from .utils import read_file, _detect_yaml_type
from .core import call_claude


def explain_exit_code(code: int, model: str, copy: bool) -> None:
    """Explain a shell exit code — known codes answered locally, unknowns via Claude."""
    from rich.markdown import Markdown
    output.console.rule(f"[bold cyan]errex — Exit Code {code}[/bold cyan]")
    output.console.print()

    if code in _constants.EXIT_CODES:
        name, explanation = _constants.EXIT_CODES[code]
        output.console.print(f"[bold red]Exit {code}:[/bold red]  [bold]{name}[/bold]\n")
        output.console.print(explanation)
        output.console.print()
        output.console.rule(style="dim")
        if copy:
            output.copy_to_clipboard(f"Exit {code}: {name}\n{explanation}")
        return

    if 128 < code <= 165:
        sig_num = code - 128
        sig_name = _constants._SIGNAL_NAMES.get(sig_num, f"signal {sig_num}")
        msg = (
            f"The process was killed by **{sig_name}** (signal {sig_num}).\n\n"
            f"Exit code {code} = 128 + {sig_num} (the signal number)."
        )
        output.console.print(f"[bold red]Exit {code}:[/bold red]  [bold]Killed by {sig_name}[/bold]\n")
        output.console.print(Markdown(msg))
        output.console.print()
        output.console.rule(style="dim")
        if copy:
            output.copy_to_clipboard(f"Exit {code}: Killed by {sig_name}\n{msg}")
        return

    # Unknown — fall through to Claude
    output.console.print(f"[dim]Unknown exit code — asking Claude…[/dim]\n")
    prompt = (
        f"Explain shell exit code {code}. Cover: what it typically means, "
        f"which tools or runtimes commonly return it, and how to diagnose or fix the root cause. "
        f"Be concise and use markdown."
    )
    _, in_tok, out_tok, _elapsed = call_claude(
        str(code), model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    print()
    output.console.rule(style="dim")
    if copy:
        output.copy_to_clipboard(prompt)


def explain_http(code: int, model: str, copy: bool) -> None:
    """Explain an HTTP status code — known codes answered locally, unknowns via Claude."""
    output.console.rule(f"[bold cyan]errex — HTTP {code}[/bold cyan]")
    output.console.print()

    if code in _constants.HTTP_CODES:
        name, explanation = _constants.HTTP_CODES[code]
        category = {1: "Informational", 2: "Success", 3: "Redirection", 4: "Client Error", 5: "Server Error"}.get(code // 100, "Unknown")
        output.console.print(f"[bold red]HTTP {code}:[/bold red]  [bold]{name}[/bold]  [dim]({category})[/dim]\n")
        output.console.print(explanation)
        output.console.print()
        output.console.rule(style="dim")
        if copy:
            output.copy_to_clipboard(f"HTTP {code}: {name}\n{explanation}")
        return

    output.console.print(f"[dim]Non-standard status code — asking Claude…[/dim]\n")
    prompt = (
        f"Explain HTTP status code {code}. Cover: what it means, which servers or frameworks use it, "
        f"common causes, and how to handle or fix it. Be concise and use markdown."
    )
    call_claude(str(code), model=model, messages=[{"role": "user", "content": prompt}])
    print()
    output.console.rule(style="dim")


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
                days = [_constants._CRON_DOW.get(int(d), d) for d in dw.split(",")]
                day_str = ", ".join(days[:-1]) + " and " + days[-1]
            else:
                day_str = _constants._CRON_DOW.get(int(dw), dw)
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
            return f"Once a year: {_constants._CRON_MONTH[int(mo)]} {_ordinal(int(dm))} at {t}."
        except (ValueError, KeyError):
            return None

    return None


def explain_cron(expr: str, model: str, copy: bool) -> None:
    """Explain a cron expression in plain English."""
    output.console.rule(f"[bold cyan]errex — Cron: {expr}[/bold cyan]")
    output.console.print()

    local = _cron_local(expr)
    if local:
        output.console.print(f"[bold]{local}[/bold]\n")
        output.console.print(f"[dim]Fields: minute  hour  day-of-month  month  day-of-week[/dim]")
        output.console.print(f"[dim]        {expr}[/dim]")
        output.console.print()
        output.console.rule(style="dim")
        if copy:
            output.copy_to_clipboard(f"Cron `{expr}`: {local}")
        return

    output.console.print("[dim]Complex expression — asking Claude…[/dim]\n")
    prompt = (
        f"Explain this cron expression in plain English: `{expr}`\n\n"
        f"Cover: when it runs (with concrete examples), what each field means, "
        f"and any edge cases (e.g. month-end days, DST). Use markdown."
    )
    call_claude(expr, model=model, messages=[{"role": "user", "content": prompt}])
    print()
    output.console.rule(style="dim")
    if copy:
        output.copy_to_clipboard(expr)


def explain_sql(query: str, model: str, copy: bool, show_tokens: bool, perf: bool = False) -> None:
    """Explain a SQL query in plain English."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        output.err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    prompt = f"Explain this SQL query:\n\n```sql\n{query}\n```"

    output.console.rule("[bold cyan]errex — SQL Explanation[/bold cyan]")
    print()

    client = anthropic.Anthropic(timeout=_constants.API_TIMEOUT)
    collected = []
    input_tokens = output_tokens = 0
    t0 = time.time()
    try:
        with client.messages.stream(
            model=model,
            max_tokens=1024,
            system=[{"type": "text", "text": _constants.SQL_PROMPT, "cache_control": {"type": "ephemeral"}}],
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

    save_history(query, response, model, False)
    if copy:
        output.copy_to_clipboard(response)


def explain_env_var(var: str, model: str, copy: bool) -> None:
    """Explain an environment variable — known ones answered locally, unknowns via Claude."""
    import os as _os
    output.console.rule(f"[bold cyan]errex — Env: {var}[/bold cyan]")
    output.console.print()

    lookup = _constants.ENV_VARS.get(var.upper()) or _constants.ENV_VARS.get(var)
    if lookup:
        output.console.print(f"[bold cyan]{var}[/bold cyan]\n")
        output.console.print(lookup)
        output.console.print()
        # Also show current value if set
        current = _os.environ.get(var)
        if current is not None:
            display = current if len(current) <= 80 else current[:77] + "…"
            output.console.print(f"[dim]Current value:[/dim] {display}")
        else:
            output.console.print(f"[dim]Not currently set in this environment.[/dim]")
        output.console.print()
        output.console.rule(style="dim")
        if copy:
            output.copy_to_clipboard(f"{var}: {lookup}")
        return

    output.console.print(f"[dim]Unknown variable — asking Claude…[/dim]\n")
    prompt = (
        f"Explain the environment variable `{var}`. Cover: what it does, which tools or "
        f"languages use it, common values, and any security or performance implications. "
        f"Be concise and use markdown."
    )
    call_claude(var, model=model, messages=[{"role": "user", "content": prompt}])
    print()
    output.console.rule(style="dim")


def explain_yaml(path: str, model: str, copy: bool, show_tokens: bool, perf: bool = False) -> None:
    """Explain a YAML config file in plain English."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        output.err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    content = read_file(path)
    yaml_type = _detect_yaml_type(content)
    prompt = f"This is a {yaml_type} file. Please explain it:\n\n```yaml\n{content}\n```"

    output.console.rule(f"[bold cyan]errex — YAML: {Path(path).name}[/bold cyan]")
    output.console.print(f"[dim]Detected: {yaml_type}[/dim]\n")

    client = anthropic.Anthropic(timeout=_constants.API_TIMEOUT)
    collected = []
    input_tokens = output_tokens = 0
    t0 = time.time()
    try:
        with client.messages.stream(
            model=model,
            max_tokens=2048,
            system=[{"type": "text", "text": _constants.YAML_PROMPT, "cache_control": {"type": "ephemeral"}}],
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


def explain_dockerfile(path: str, model: str, copy: bool, show_tokens: bool, perf: bool = False) -> None:
    """Explain a Dockerfile step by step."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        output.err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    content = read_file(path)
    prompt = f"Please explain this Dockerfile:\n\n```dockerfile\n{content}\n```"

    output.console.rule(f"[bold cyan]errex — Dockerfile: {Path(path).name}[/bold cyan]")
    print()

    client = anthropic.Anthropic(timeout=_constants.API_TIMEOUT)
    collected = []
    input_tokens = output_tokens = 0
    t0 = time.time()
    try:
        with client.messages.stream(
            model=model,
            max_tokens=2048,
            system=[{"type": "text", "text": _constants.DOCKERFILE_PROMPT, "cache_control": {"type": "ephemeral"}}],
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


def explain_regex(pattern: str, model: str, copy: bool, show_tokens: bool, perf: bool = False) -> None:
    """Explain a regular expression in plain English."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        output.err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    prompt = f"Explain this regular expression:\n\n```\n{pattern}\n```"

    output.console.rule("[bold cyan]errex — Regex Explanation[/bold cyan]")
    print()

    client = anthropic.Anthropic(timeout=_constants.API_TIMEOUT)
    collected = []
    input_tokens = output_tokens = 0
    t0 = time.time()
    try:
        with client.messages.stream(
            model=model,
            max_tokens=1024,
            system=[{"type": "text", "text": _constants.REGEX_PROMPT, "cache_control": {"type": "ephemeral"}}],
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

    save_history(pattern, response, model, False)
    if copy:
        output.copy_to_clipboard(response)
