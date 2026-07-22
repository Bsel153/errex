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


def explain_env_file(path: str) -> None:
    """Read a .env file and print a table: key | masked value | description."""
    import re as _re
    from pathlib import Path as _Path

    # Patterns that suggest a value is a secret and should be masked
    _SECRET_KEYS = _re.compile(
        r"(secret|token|key|password|passwd|pwd|api_key|apikey|auth|credential|private)",
        _re.IGNORECASE,
    )
    _SECRET_VALUE = _re.compile(
        r"^(sk-|ghp_|ghs_|xoxb-|ya29\.|eyJ|AKIA)",
    )

    try:
        text = _Path(path).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        output.err_console.print(f"[red]errex: file not found: {path!r}[/red]")
        import sys
        sys.exit(1)
    except OSError as e:
        output.err_console.print(f"[red]errex: cannot read {path!r}: {e}[/red]")
        import sys
        sys.exit(1)

    from rich.table import Table

    output.console.rule(f"[bold cyan]errex — Env File: {_Path(path).name}[/bold cyan]")
    output.console.print()

    tbl = Table(show_header=True, show_lines=False, box=None, expand=False)
    tbl.add_column("KEY", style="cyan", no_wrap=True)
    tbl.add_column("VALUE", style="dim", no_wrap=True)
    tbl.add_column("WHAT IT DOES", style="")

    found = 0
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, raw_val = line.partition("=")
        key = key.strip()
        raw_val = raw_val.strip().strip('"').strip("'")
        if not key:
            continue
        found += 1

        # Mask value if it looks like a secret
        looks_secret = bool(_SECRET_KEYS.search(key)) or bool(_SECRET_VALUE.match(raw_val))
        if looks_secret:
            display_val = raw_val[:3] + "***" if len(raw_val) > 3 else "***"
        else:
            display_val = raw_val[:40] + ("…" if len(raw_val) > 40 else "")
        if not display_val:
            display_val = "[dim](not set)[/dim]"

        # Look up description
        desc = _constants.ENV_VARS.get(key.upper()) or _constants.ENV_VARS.get(key)
        if desc:
            # Trim to first sentence
            first_sentence = desc.split(". ")[0]
            desc_display = first_sentence[:100] + ("…" if len(first_sentence) > 100 else "")
        else:
            desc_display = "[dim](custom / unknown)[/dim]"

        tbl.add_row(key, display_val, desc_display)

    if found == 0:
        output.console.print("[dim]No KEY=VALUE pairs found.[/dim]")
    else:
        output.console.print(tbl)
        output.console.print(
            f"\n[dim]{found} variable(s) — values containing 'secret', 'key', 'token', "
            f"'password' or known prefixes are masked.[/dim]"
        )

    output.console.print()
    output.console.rule(style="dim")


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


# ── K8s explainer ─────────────────────────────────────────────────────────────

_K8S_TABLE = [
    ("CrashLoopBackOff",         "Pod is crashing on startup",               "Check pod logs: kubectl logs <pod> --previous"),
    ("OOMKilled",                 "Container exceeded its memory limit",      "Increase memory limit or find memory leak"),
    ("ImagePullBackOff",          "Image not found or registry auth failed",  "Check image name/tag and imagePullSecrets"),
    ("ErrImagePull",              "Image pull failed (registry error)",       "Check image name/tag and imagePullSecrets"),
    ("Pending",                   "No schedulable node found",                "Check node resources: kubectl describe node"),
    ("CreateContainerConfigError","Bad env var, secret, or configmap ref",    "Check all env references and secretKeyRef"),
    ("FailedScheduling",          "Insufficient CPU or memory on nodes",      "Scale cluster or reduce resource requests"),
    ("Terminating",               "Pod stuck terminating (finalizer issue)",  "Force delete: kubectl delete pod <pod> --grace-period=0 --force"),
]


def explain_k8s(text: str, model: str | None = None) -> None:
    """Explain Kubernetes status conditions from kubectl output or log text."""
    from rich.table import Table

    output.console.rule("[bold cyan]errex — Kubernetes Explainer[/bold cyan]")
    output.console.print()

    matched: list[tuple] = []
    for condition, cause, fix in _K8S_TABLE:
        if condition.lower() in text.lower():
            matched.append((condition, cause, fix))

    if matched:
        tbl = Table(show_header=True, header_style="bold", show_lines=True, box=None)
        tbl.add_column("ISSUE",        style="red bold", width=28)
        tbl.add_column("LIKELY CAUSE", style="yellow",   width=36)
        tbl.add_column("RECOMMENDED FIX", style="cyan",  width=42)
        for condition, cause, fix in matched:
            tbl.add_row(condition, cause, fix)
        output.console.print(tbl)
    else:
        # Unknown — fall through to Claude
        if not os.environ.get("ANTHROPIC_API_KEY"):
            output.err_console.print(
                "[red]errex: unrecognized k8s status and ANTHROPIC_API_KEY is not set.[/red]"
            )
            sys.exit(1)
        output.console.print("[dim]Unrecognized k8s status — asking Claude…[/dim]\n")
        prompt = (
            "The following is Kubernetes output or pod status. "
            "Identify any error conditions, explain their likely cause, and give concrete fix steps. "
            "Use markdown.\n\n"
            f"```\n{text[:4000]}\n```"
        )
        call_claude(text[:200], model=model or os.environ.get("ERREX_MODEL") or _constants.CONFIG_DEFAULTS["model"],
                    messages=[{"role": "user", "content": prompt}])
        print()

    output.console.rule(style="dim")
    output.console.print()


# ── Network error explainer ───────────────────────────────────────────────────

_NETWORK_PATTERNS = [
    ("Connection refused",                  "Nothing is listening on that port",              "Check the service is running and bound to the right address/port"),
    ("Name or service not known",           "DNS resolution failure — hostname does not exist","Check the hostname spelling or your DNS configuration"),
    ("NXDOMAIN",                            "DNS resolution failure — domain not found",      "Verify the domain name and your DNS server settings"),
    ("Network is unreachable",              "No route to the target host",                    "Check your network interface and routing table (ip route)"),
    ("Request timeout",                     "Packet loss or firewall blocking the connection","Verify firewall rules and check for packet loss with traceroute"),
    ("SSL_ERROR",                           "TLS/SSL handshake failure",                      "Check certificate validity, cipher suite compatibility, and hostname"),
    ("Temporary failure in name resolution","DNS server is down or unreachable",             "Check /etc/resolv.conf and your DNS server availability"),
    ("curl: (6)",                           "DNS resolution failure (curl code 6)",           "Verify the hostname and DNS configuration"),
    ("curl: (7)",                           "Connection refused (curl code 7)",               "Check the service is running on the target host and port"),
    ("curl: (28)",                          "Connection timed out (curl code 28)",            "Check firewall rules, network connectivity, and target host status"),
]


def explain_network(text: str, model: str | None = None) -> None:
    """Explain network errors from log text or error messages."""
    from rich.panel import Panel

    output.console.rule("[bold cyan]errex — Network Error Explainer[/bold cyan]")
    output.console.print()

    matched: list[tuple] = []
    for pattern, issue, fix in _NETWORK_PATTERNS:
        if pattern.lower() in text.lower():
            if (pattern, issue, fix) not in matched:
                matched.append((pattern, issue, fix))

    if matched:
        for pattern, issue, fix in matched:
            body = f"[bold]Issue:[/bold]  {issue}\n[bold]Fix:[/bold]    {fix}"
            output.console.print(Panel(body, title=f"[red]{pattern}[/red]", expand=False))
            output.console.print()
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            output.err_console.print(
                "[red]errex: unrecognized network error and ANTHROPIC_API_KEY is not set.[/red]"
            )
            sys.exit(1)
        output.console.print("[dim]Unrecognized network error — asking Claude…[/dim]\n")
        prompt = (
            "The following appears to be a network error or connectivity issue. "
            "Identify what went wrong, explain the likely cause, and give actionable fix steps. "
            "Use markdown.\n\n"
            f"```\n{text[:4000]}\n```"
        )
        call_claude(text[:200], model=model or os.environ.get("ERREX_MODEL") or _constants.CONFIG_DEFAULTS["model"],
                    messages=[{"role": "user", "content": prompt}])
        print()

    output.console.rule(style="dim")
    output.console.print()


# ── Performance profile explainer ─────────────────────────────────────────────

def explain_perf(path: str, model: str | None = None) -> None:
    """Detect cProfile or pprof format, extract hotspots, explain with Claude."""
    import re as _re
    from rich.table import Table

    if not os.environ.get("ANTHROPIC_API_KEY"):
        output.err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except FileNotFoundError:
        output.err_console.print(f"[red]errex: file not found: {path}[/red]")
        sys.exit(1)
    except OSError as e:
        output.err_console.print(f"[red]errex: cannot read {path}: {e}[/red]")
        sys.exit(1)

    output.console.rule(f"[bold cyan]errex — Performance Explainer: {Path(path).name}[/bold cyan]")
    output.console.print()

    fmt = "unknown"
    hotspot_lines: list[str] = []

    # Detect Python cProfile output (has ncalls, cumtime)
    if "ncalls" in content and "cumtime" in content:
        fmt = "Python cProfile"
        data_lines = [l for l in content.splitlines() if l.strip() and not l.strip().startswith("ncalls")]
        # Sort lines heuristically — they usually come pre-sorted by cumtime
        hotspot_lines = [l for l in data_lines if _re.search(r"\s+\d+\.\d+\s+", l)][:10]
    # Detect Go pprof (has flat% and cum%)
    elif "flat%" in content and "cum%" in content:
        fmt = "Go pprof"
        data_lines = [l for l in content.splitlines() if l.strip() and not l.strip().startswith("flat")]
        hotspot_lines = [l for l in data_lines if _re.search(r"\d+\.\d+%", l)][:10]
    else:
        hotspot_lines = content.splitlines()[:20]

    output.console.print(f"[bold]Format detected:[/bold]  {fmt}\n")

    if hotspot_lines:
        tbl = Table(show_header=True, header_style="bold", show_lines=False, box=None)
        tbl.add_column("#",          style="dim",  width=4,   justify="right")
        tbl.add_column("HOTSPOT",    style="cyan")
        for i, line in enumerate(hotspot_lines[:10], 1):
            tbl.add_row(str(i), line.strip()[:120])
        output.console.print(tbl)
        output.console.print()

    # Send to Claude
    hotspot_text = "\n".join(hotspot_lines[:10]) if hotspot_lines else content[:2000]
    prompt = (
        f"Here are the top CPU hotspots from a {fmt} profile. "
        f"Explain what is slow and suggest concrete optimizations. "
        f"Be specific and actionable. Use markdown.\n\n"
        f"```\n{hotspot_text}\n```"
    )

    _model = model or os.environ.get("ERREX_MODEL") or _constants.CONFIG_DEFAULTS["model"]

    output.console.print("[bold]Analysis (Claude):[/bold]\n")
    call_claude(hotspot_text[:200], model=_model, messages=[{"role": "user", "content": prompt}])
    print()
    output.console.rule(style="dim")
    output.console.print()
