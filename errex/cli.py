from __future__ import annotations

import sys
import os
import argparse
import importlib.metadata

from rich.console import Console

from . import output, _constants
from ._paths import HISTORY_FILE, CONFIG_FILE
from .config import load_config, manage_config, load_profile, list_profiles, delete_profile
from .history import (save_history, show_history, show_recent, find_similar, clear_history,
                      export_history, show_stats, interactive_history, rate_last, add_note,
                      find_by_name, list_named, export_csv, search_history, dedup_history,
                      show_last, pin_entry)
from .core import (call_claude, explain_error, compare_errors, chat_loop, ask_about_last,
                   retry_last, run_bulk, apply_fix)
from .cache import clear_cache, cache_stats
from .code_tools import (lint_file, explain_code, generate_test, explain_diff, explain_inline,
                         grep_and_explain, summarize_log)
from .explainers import (explain_exit_code, explain_http, explain_cron, explain_sql,
                         explain_env_var, explain_yaml, explain_dockerfile, explain_regex)
from .setup_tools import (run_setup, run_doctor, install_shell, scan_logs, detect_environment,
                          print_completion, run_command, rerun_last_command, open_last_in_browser)
from .utils import (read_file, get_error_input, extract_snippet, redact_secrets, format_json_error,
                    check_for_update, get_env_info)
from .watch import watch_file
from .patterns import list_patterns as _list_patterns


def main() -> None:
    # Two-pass: detect --profile before full parse so profile defaults can be set
    _pre = argparse.ArgumentParser(add_help=False)
    _pre.add_argument("--profile", default=None)
    _pre_args, _ = _pre.parse_known_args()

    file_config: dict = {}
    if CONFIG_FILE.exists():
        import json
        try:
            with open(CONFIG_FILE) as _f:
                file_config = json.load(_f)
        except (json.JSONDecodeError, OSError):
            pass

    config = load_config()
    if _pre_args.profile:
        config = load_profile(_pre_args.profile, file_config)

    try:
        _ver = importlib.metadata.version("errex")
    except importlib.metadata.PackageNotFoundError:
        _ver = "dev"

    parser = argparse.ArgumentParser(
        prog="errex",
        description="Paste or pipe an error message and get a plain-English explanation.",
    )
    parser.add_argument("--version", action="version", version=f"errex {_ver}")
    parser.add_argument("files", nargs="*", help="one or more files containing errors (pass 2+ to compare them)")
    parser.add_argument("--model", help="Claude model to use (default: claude-sonnet-4-6)")
    parser.add_argument("--brief", action="store_true", default=None, help="one-paragraph summary instead of full analysis")
    parser.add_argument("--lang", help="language or runtime hint when ambiguous (e.g. rust, go, java)")
    parser.add_argument("--copy", action="store_true", default=None, help="copy the explanation to the clipboard after printing")
    parser.add_argument("--json", action="store_true", dest="json_output", help="output structured JSON")
    parser.add_argument("--fix", action="store_true", help="output only the fix command, no explanation")
    parser.add_argument("--watch", metavar="LOGFILE", help="watch a log file and explain errors as they appear")
    parser.add_argument("--host", default="127.0.0.1", metavar="ADDR",
                        help="host to bind the web UI to (default: 127.0.0.1; use 0.0.0.0 for network access)")
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
    parser.add_argument("--explain-code", metavar="FILE", dest="explain_code", help="explain what a piece of code does")
    parser.add_argument("--issues", action="store_true", help="search GitHub Issues for similar errors after explaining")
    parser.add_argument("--lint", metavar="FILE", help="scan a code file for potential bugs and issues")
    parser.add_argument("--export", metavar="FILE", help="export history to a file (.html or .md)")
    parser.add_argument("--export-format", choices=["html", "md"], default=None, help="format for --export (auto-detected from extension if omitted)")
    parser.add_argument("--ask", metavar="QUESTION", help="ask a follow-up question about the last error in history")
    parser.add_argument("--explain-diff", metavar="FILE", dest="explain_diff", nargs="?", const="-", help="explain a git diff (pass a .diff/.patch file, or pipe: git diff | errex --explain-diff)")
    parser.add_argument("--similar", action="store_true", help="find past errors in your history that are similar to the current one")
    parser.add_argument("--config", nargs="?", const=None, metavar="KEY=VALUE", help="view or set config (e.g. --config model=claude-opus-4-7); omit value to show all settings")
    parser.add_argument("--clear-history", nargs="?", const=0, type=int, metavar="DAYS", dest="clear_history",
                        help="delete history entries (all by default; pass DAYS to only remove entries older than N days)")
    parser.add_argument("--recent", nargs="?", const=5, type=int, metavar="N",
                        help="show the N most recent history entries (default: 5)")
    parser.add_argument("--summarize-log", metavar="FILE", dest="summarize_log",
                        help="produce a diagnostic digest of all distinct errors in a log file")
    parser.add_argument("--retry", action="store_true",
                        help="re-explain the last error from history (combine with --model, --brief, etc.)")
    parser.add_argument("--test-gen", metavar="FILE", dest="test_gen",
                        help="generate a test case for a code file; pipe an error to reproduce it")
    parser.add_argument("--doctor", action="store_true",
                        help="check that errex is set up correctly (API key, config, connectivity)")
    parser.add_argument("--offline", action="store_true",
                        help="skip network checks in --doctor")
    parser.add_argument("--completion", metavar="SHELL", choices=["bash", "zsh"],
                        help="print a shell completion script (bash or zsh)")
    parser.add_argument("--translate", metavar="LANG",
                        help="translate the explanation into a spoken language (e.g. Spanish, French, Japanese)")
    parser.add_argument("--save-as", metavar="NAME", dest="save_as",
                        help="save this explanation with a memorable name for quick retrieval")
    parser.add_argument("--grep", nargs=2, metavar=("PATTERN", "FILE"),
                        help="filter a log file by regex pattern, then explain matching lines")
    parser.add_argument("--ci", action="store_true",
                        help="CI mode: no-color + terse output, GitHub Actions annotations, exits 1")
    parser.add_argument("--rate", metavar="SCORE", type=int, dest="rate",
                        help="rate the last explanation 1-5 (stored in history, shown in --stats)")
    parser.add_argument("--profile", metavar="NAME",
                        help="load a named config profile from ~/.errexrc (overrides config, CLI wins)")
    parser.add_argument("--bulk", metavar="FILE",
                        help="explain multiple errors from a file separated by blank lines")
    parser.add_argument("--explain-exit", metavar="CODE", type=int, dest="explain_exit",
                        help="explain a shell exit code (e.g. --explain-exit 139 → segfault)")
    parser.add_argument("--explain-http", metavar="CODE", type=int, dest="explain_http",
                        help="explain an HTTP status code (e.g. --explain-http 429)")
    parser.add_argument("--explain-cron", metavar="EXPR", dest="explain_cron",
                        help="explain a cron expression (e.g. --explain-cron '0 * * * *')")
    parser.add_argument("--snippet", action="store_true",
                        help="strip stdlib/library frames from a traceback before explaining")
    parser.add_argument("--debug", action="store_true",
                        help="dry run: print the prompt that would be sent to Claude, then exit")
    parser.add_argument("--list-profiles", action="store_true", dest="list_profiles",
                        help="list all named profiles in ~/.errexrc")
    parser.add_argument("--explain-env", metavar="VAR", dest="explain_env",
                        help="explain an environment variable (e.g. --explain-env PYTHONPATH)")
    parser.add_argument("--open", action="store_true",
                        help="export the last explanation as HTML and open it in the browser")
    parser.add_argument("--rerun", action="store_true",
                        help="re-run the last shell command and explain if it fails")
    parser.add_argument("--top", metavar="N", type=int,
                        help="limit root cause analysis to the top N most likely causes")
    parser.add_argument("--word-wrap", metavar="N", type=int, dest="word_wrap",
                        help="set the output console width in characters")
    parser.add_argument("--add-note", metavar="TEXT", dest="add_note",
                        help="append a personal note to the last history entry")
    parser.add_argument("--format-json", action="store_true", dest="format_json",
                        help="parse the error as JSON and reformat it before explaining")
    parser.add_argument("--interactive", action="store_true",
                        help="browse recent history with a numbered picker")
    parser.add_argument("--webhook", metavar="URL",
                        help="POST the explanation as JSON to a URL (Slack, Discord, or generic)")
    parser.add_argument("--digest", action="store_true",
                        help="print a digest of recent errors from history")
    parser.add_argument("--digest-since", dest="digest_since", type=int, default=24, metavar="HOURS",
                        help="digest window in hours (default: 24)")
    parser.add_argument("--digest-webhook", dest="digest_webhook", default=None, metavar="URL",
                        help="send digest to a Slack/Discord webhook URL")
    parser.add_argument("--find-name", metavar="NAME", dest="find_name",
                        help="retrieve a history entry saved with --save-as NAME")
    parser.add_argument("--timeout", metavar="N", type=int, default=30,
                        help="API request timeout in seconds (default: 30)")
    parser.add_argument("--output", metavar="FILE",
                        help="save the explanation to a file (in addition to printing)")
    parser.add_argument("--terse", action="store_true",
                        help="one-sentence diagnosis — shorter than --brief, great for scripting")
    parser.add_argument("--no-color", action="store_true", dest="no_color",
                        help="plain-text output with no rich formatting (safe to pipe)")
    parser.add_argument("--since", metavar="DATE",
                        help="filter --history/--recent to entries on or after DATE (YYYY-MM-DD)")
    parser.add_argument("--env", action="store_true",
                        help="auto-attach system info (OS, Python, shell, runtimes) as context")
    parser.add_argument("--explain-regex", metavar="PATTERN", dest="explain_regex",
                        help="explain what a regular expression matches in plain English")
    parser.add_argument("--explain-sql", metavar="QUERY", dest="explain_sql",
                        help="explain what a SQL query does and flag potential performance issues")
    parser.add_argument("--list-named", action="store_true", dest="list_named",
                        help="list all history entries saved with --save-as")
    parser.add_argument("--run", metavar="CMD",
                        help="run a shell command and auto-explain any error output")
    parser.add_argument("--delete-profile", metavar="NAME", dest="delete_profile",
                        help="delete a named profile from ~/.errexrc")
    parser.add_argument("--pin", action="store_true",
                        help="mark the last history entry as pinned (protected from --clear-history)")
    parser.add_argument("--unpin", action="store_true",
                        help="remove the pin from the last history entry")
    parser.add_argument("--redact", action="store_true",
                        help="strip API keys, tokens, and passwords from error text before sending to Claude")
    parser.add_argument("--explain-yaml", metavar="FILE", dest="explain_yaml",
                        help="explain a YAML config file (auto-detects docker-compose, k8s, GitHub Actions)")
    parser.add_argument("--filter", metavar="TYPE", dest="filter_type",
                        help="filter --history/--recent to entries matching an error type (e.g. TypeError, 404)")
    parser.add_argument("--export-csv", metavar="FILE", dest="export_csv",
                        help="export history to a CSV file for spreadsheet analysis")
    parser.add_argument("--perf", action="store_true",
                        help="show response time and tokens/second after each explanation")
    parser.add_argument("--explain-dockerfile", metavar="FILE", dest="explain_dockerfile",
                        help="explain a Dockerfile layer by layer with security and performance notes")
    parser.add_argument("--search", metavar="TERM",
                        help="full-text search across all history fields (error, explanation, name, notes)")
    parser.add_argument("--inline", nargs=2, metavar=("FILE", "LINE"),
                        help="explain a specific line of a code file in context (e.g. --inline app.py 42)")
    parser.add_argument("--dedup", action="store_true",
                        help="scan history and show groups of near-duplicate errors")
    parser.add_argument("--last", action="store_true",
                        help="print the last explanation from history without re-running Claude")
    parser.add_argument("--no-cache", action="store_true", dest="no_cache",
                        help="skip the local pattern cache and response cache; always call Claude")
    parser.add_argument("--list-patterns", action="store_true", dest="list_patterns",
                        help="show all built-in offline error patterns")
    parser.add_argument("--clear-cache", action="store_true", dest="clear_cache_flag",
                        help="clear the response cache (~/.errex_response_cache.json)")
    parser.add_argument("--fix-apply", action="store_true", dest="fix_apply",
                        help="get a fix command from Claude and run it (asks for confirmation)")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="auto-confirm fix commands from --fix-apply without prompting")
    parser.add_argument("--open-ticket", action="store_true", dest="open_ticket",
                        help="open a Red Hat Customer Portal support case with this error")
    parser.add_argument("--rht-username", dest="rht_username", default=None, metavar="USER",
                        help="Red Hat username (or set RHT_USERNAME env var)")
    parser.add_argument("--rht-password", dest="rht_password", default=None, metavar="PASS",
                        help="Red Hat password (or set RHT_PASSWORD env var)")
    parser.add_argument("--rht-severity", dest="rht_severity", type=int, default=None,
                        choices=[1, 2, 3, 4], metavar="1-4",
                        help="ticket severity: 1=Urgent 2=High 3=Normal 4=Low (default: 3)")
    parser.add_argument("--rht-product", dest="rht_product", default=None, metavar="NAME",
                        help="Red Hat product name for the ticket")
    parser.add_argument("--rht-version", dest="rht_version", default=None, metavar="VER",
                        help="product version for the ticket")
    parser.set_defaults(**config)
    args = parser.parse_args()

    _constants.API_TIMEOUT = args.timeout

    no_color = args.no_color or args.ci
    width = args.word_wrap or None
    if no_color or width:
        output.console = Console(no_color=no_color, highlight=False, width=width)
        output.err_console = Console(stderr=True, no_color=no_color, highlight=False, width=width)

    if args.ci:
        args.terse = True

    if args.rate is not None:
        rate_last(args.rate)
        return

    if args.clear_cache_flag:
        n = clear_cache()
        output.console.print(f"[green]Cache cleared ({n} entries).[/green]")
        return

    if args.bulk:
        run_bulk(
            args.bulk,
            model=args.model,
            brief=args.brief or False,
            terse=args.terse,
            lang=args.lang,
            copy=args.copy or False,
            show_tokens=args.tokens,
        )
        return

    if "--config" in sys.argv:
        manage_config(args.config)
        return

    if args.clear_history is not None:
        days = args.clear_history if args.clear_history > 0 else None
        clear_history(days)
        return

    if args.recent is not None:
        show_recent(args.recent, since=args.since, filter_type=args.filter_type)
        return

    if args.summarize_log:
        summarize_log(
            args.summarize_log,
            model=args.model,
            copy=args.copy or False,
            show_tokens=args.tokens,
            perf=args.perf,
        )
        return

    if args.retry:
        retry_last(
            model=args.model,
            brief=args.brief or False,
            fix=args.fix,
            lang=args.lang,
            copy=args.copy or False,
            show_tokens=args.tokens,
            chat=args.chat,
        )
        return

    if args.doctor:
        run_doctor(offline=getattr(args, "offline", False))
        return

    if args.completion:
        print_completion(args.completion)
        return

    if args.grep:
        grep_and_explain(
            args.grep[0],
            args.grep[1],
            model=args.model,
            lang=args.lang,
            copy=args.copy or False,
            show_tokens=args.tokens,
        )
        return

    if args.explain_exit is not None:
        explain_exit_code(args.explain_exit, model=args.model, copy=args.copy or False)
        return

    if args.explain_http is not None:
        explain_http(args.explain_http, model=args.model, copy=args.copy or False)
        return

    if args.explain_cron:
        explain_cron(args.explain_cron, model=args.model, copy=args.copy or False)
        return

    if args.list_profiles:
        list_profiles()
        return

    if args.explain_env:
        explain_env_var(args.explain_env, model=args.model, copy=args.copy or False)
        return

    if args.explain_sql:
        explain_sql(args.explain_sql, model=args.model, copy=args.copy or False, show_tokens=args.tokens, perf=args.perf)
        return

    if args.list_named:
        list_named()
        return

    if args.run:
        run_command(
            args.run,
            model=args.model,
            brief=args.brief or False,
            lang=args.lang,
            copy=args.copy or False,
            show_tokens=args.tokens,
        )
        return

    if args.delete_profile:
        delete_profile(args.delete_profile)
        return

    if args.pin:
        pin_entry(True)
        return

    if args.unpin:
        pin_entry(False)
        return

    if args.explain_yaml:
        explain_yaml(
            args.explain_yaml,
            model=args.model,
            copy=args.copy or False,
            show_tokens=args.tokens,
            perf=args.perf,
        )
        return

    if args.export_csv:
        export_csv(args.export_csv)
        return

    if args.explain_dockerfile:
        explain_dockerfile(
            args.explain_dockerfile,
            model=args.model,
            copy=args.copy or False,
            show_tokens=args.tokens,
            perf=args.perf,
        )
        return

    if args.search:
        search_history(args.search)
        return

    if args.inline:
        path_arg, line_arg = args.inline
        try:
            line_num = int(line_arg)
        except ValueError:
            output.err_console.print(f"[red]errex: LINE must be an integer, got: {line_arg!r}[/red]")
            sys.exit(1)
        explain_inline(
            path_arg,
            line_num,
            model=args.model,
            copy=args.copy or False,
            show_tokens=args.tokens,
            perf=args.perf,
        )
        return

    if args.dedup:
        dedup_history()
        return

    if args.list_patterns:
        from rich.table import Table
        tbl = Table(title="errex — built-in offline patterns", show_lines=False, box=None)
        tbl.add_column("#", style="dim", width=4)
        tbl.add_column("Pattern", style="cyan")
        for i, title in enumerate(_list_patterns(), 1):
            tbl.add_row(str(i), title)
        output.console.print(tbl)
        return

    if args.last:
        show_last()
        return

    if args.open:
        open_last_in_browser()
        return

    if args.rerun:
        rerun_last_command(
            model=args.model,
            brief=args.brief or False,
            lang=args.lang,
            copy=args.copy or False,
            show_tokens=args.tokens,
        )
        return

    if args.add_note:
        add_note(args.add_note)
        return

    if args.interactive:
        interactive_history()
        return

    if args.find_name:
        find_by_name(args.find_name)
        return

    if args.ask:
        ask_about_last(
            args.ask,
            model=args.model,
            show_tokens=args.tokens,
            copy=args.copy or False,
        )
        return

    if args.digest:
        from .digest import generate_digest, format_digest_text, send_digest
        d = generate_digest(since_hours=args.digest_since)
        output.console.print(format_digest_text(d))
        if args.digest_webhook:
            ok = send_digest(args.digest_webhook, d)
            if ok:
                output.console.print("[green]✓ Digest sent to webhook[/green]")
            else:
                output.console.print("[red]✗ Failed to send digest to webhook[/red]")
        return

    if args.stats:
        show_stats()
        return

    if args.web:
        from .web_ui import serve
        serve(host=args.host)
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

    if args.export:
        fmt = args.export_format or ("html" if args.export.endswith(".html") else "md")
        export_history(args.export, fmt)
        return

    if args.explain_diff is not None:
        if args.explain_diff == "-" or args.explain_diff is True:
            if not sys.stdin.isatty():
                diff_text = sys.stdin.read().strip()
            else:
                output.console.print("[dim]Paste your diff below. Press Ctrl+D when done:[/dim]\n")
                diff_text = sys.stdin.read().strip()
        else:
            diff_text = read_file(args.explain_diff)
        if not diff_text:
            output.err_console.print("[red]errex: no diff content provided.[/red]")
            sys.exit(1)
        explain_diff(
            diff_text,
            model=args.model,
            lang=args.lang,
            copy=args.copy or False,
            show_tokens=args.tokens,
            perf=args.perf,
        )
        return

    if args.test_gen:
        error_text_for_test = None
        if not sys.stdin.isatty():
            error_text_for_test = sys.stdin.read().strip() or None
        generate_test(
            args.test_gen,
            error_text=error_text_for_test,
            model=args.model,
            lang=args.lang,
            copy=args.copy or False,
            show_tokens=args.tokens,
            perf=args.perf,
        )
        return

    if args.lint:
        lint_file(
            args.lint,
            model=args.model,
            lang=args.lang,
            copy=args.copy or False,
            show_tokens=args.tokens,
            perf=args.perf,
        )
        return

    if args.explain_code:
        explain_code(
            args.explain_code,
            model=args.model,
            lang=args.lang,
            copy=args.copy or False,
            show_tokens=args.tokens,
            chat=args.chat,
            perf=args.perf,
        )
        return

    if args.install_shell:
        install_shell()
        return

    if args.history is not None:
        show_history(args.history or None, since=args.since, filter_type=args.filter_type)
        return

    if args.explain_regex:
        explain_regex(
            args.explain_regex,
            model=args.model,
            copy=args.copy or False,
            show_tokens=args.tokens,
            perf=args.perf,
        )
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

    if args.similar:
        find_similar(error_text)
        return

    context_text = read_file(args.context) if args.context else None

    if args.env:
        env_block = get_env_info()
        context_text = (context_text + "\n\n" if context_text else "") + f"System environment:\n{env_block}"

    if args.format_json:
        formatted = format_json_error(error_text)
        if formatted != error_text:
            output.err_console.print("[dim](JSON parsed and reformatted)[/dim]")
        error_text = formatted

    if args.snippet:
        trimmed = extract_snippet(error_text)
        if trimmed != error_text:
            n_orig = error_text.count("\n") + 1
            n_trim = trimmed.count("\n") + 1
            output.err_console.print(f"[dim](snippet: {n_orig} → {n_trim} lines after stripping library frames)[/dim]")
        error_text = trimmed

    if args.redact:
        error_text, n_redacted = redact_secrets(error_text)
        if n_redacted:
            output.err_console.print(f"[dim](redacted {n_redacted} secret pattern{'s' if n_redacted != 1 else ''})[/dim]")

    if args.ci and os.environ.get("GITHUB_ACTIONS"):
        first_line = error_text.splitlines()[0][:200] if error_text else "error"
        print(f"::error::{first_line}")

    if args.fix_apply:
        cfg = load_config()
        apply_fix(
            error_text,
            model=args.model,
            lang=args.lang,
            context=args.context,
            yes=args.yes,
            open_ticket=args.open_ticket or cfg.get("rht_auto_ticket", False),
            rht_username=args.rht_username or cfg.get("rht_username"),
            rht_password=args.rht_password or cfg.get("rht_password"),
            rht_product=args.rht_product or cfg.get("rht_product", "Red Hat Enterprise Linux"),
            rht_version=args.rht_version or cfg.get("rht_version", "9.0"),
            rht_severity=args.rht_severity or cfg.get("rht_severity", 3),
        )
        return

    explain_error(
        error_text,
        model=args.model,
        brief=args.brief or False,
        terse=args.terse,
        json_output=args.json_output,
        fix=args.fix,
        lang=args.lang,
        copy=args.copy or False,
        share=args.share,
        show_tokens=args.tokens,
        chat=args.chat,
        context=context_text,
        do_notify=args.notify,
        issues=args.issues,
        translate=args.translate,
        save_as=args.save_as,
        output_file=args.output,
        webhook=args.webhook,
        dry_run=args.debug,
        top_n=args.top,
        perf=args.perf,
        no_cache=args.no_cache,
        use_cache=not args.no_cache,
    )

    if args.open_ticket:
        from .ticketing import open_rht_ticket
        cfg = load_config()
        open_rht_ticket(
            error_text,
            username=args.rht_username or cfg.get("rht_username"),
            password=args.rht_password or cfg.get("rht_password"),
            product=args.rht_product or cfg.get("rht_product", "Red Hat Enterprise Linux"),
            version=args.rht_version or cfg.get("rht_version", "9.0"),
            severity=args.rht_severity or cfg.get("rht_severity", 3),
        )

    if args.ci:
        sys.exit(1)

    check_for_update()


if __name__ == "__main__":
    main()
