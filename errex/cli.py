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


def _print_tickets() -> None:
    from .tickets import get_open_tickets, load_all
    _sev_icons = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}
    open_tickets = get_open_tickets()
    if not open_tickets:
        all_tickets = load_all()
        if all_tickets:
            output.console.print("\n  [green]✓ No open tickets.[/green]  "
                                 f"({len(all_tickets)} closed/snoozed)\n")
        else:
            output.console.print("\n  [dim]No tickets yet. Run [bold]errex --scan[/bold] "
                                 "to generate tickets from findings.[/dim]\n")
        return
    output.console.print(f"\n  [bold]Open Tickets[/bold] ({len(open_tickets)})\n")
    for t in open_tickets:
        icon = _sev_icons.get(t.severity, "•")
        gh = f"  [dim]GH #{t.github_issue_number}[/dim]" if t.github_issue_number else ""
        notes_tag = f"  [dim]📝 {len(t.notes)} note(s)[/dim]" if t.notes else ""
        output.console.print(f"  {icon} [bold]{t.id}[/bold]  {t.title}{gh}{notes_tag}")
        if t.detail:
            output.console.print(f"     [dim]{t.detail[:80]}[/dim]")
        for note in t.notes[-2:]:
            output.console.print(f"     [dim]📝 {note.get('text', '')[:80]}[/dim]")
    output.console.print(
        f"\n  [dim]Close: errex --ticket-close ID  |  "
        f"Snooze: errex --ticket-snooze ID  |  "
        f"Note: errex --ticket-note ID --note \"text\"[/dim]\n"
    )


def _ticket_action(
    action: str,
    ticket_id: str,
    snooze_days: int = 7,
    github_repo: str | None = None,
    github_token: str | None = None,
    discord_webhook: str | None = None,
) -> None:
    from .tickets import close_ticket, snooze_ticket, reopen_ticket, load_all
    if action == "close":
        t = close_ticket(ticket_id)
        if not t:
            output.console.print(f"[red]Ticket '{ticket_id}' not found.[/red]")
            return
        output.console.print(f"[green]✓ Closed ticket {t.id}: {t.title}[/green]")
        if t.github_issue_number and github_repo:
            from .github_sync import close_issue
            resp = close_issue(t.github_issue_number, github_repo, token=github_token)
            if "error" not in resp:
                output.console.print(f"  [dim]GitHub Issue #{t.github_issue_number} closed.[/dim]")
            else:
                output.console.print(f"  [yellow]GitHub: {resp['error']}[/yellow]")
        if discord_webhook:
            from .discord_notify import notify_ticket_closed
            notify_ticket_closed(t, webhook_url=discord_webhook)
    elif action == "snooze":
        t = snooze_ticket(ticket_id, days=snooze_days)
        if not t:
            output.console.print(f"[red]Ticket '{ticket_id}' not found.[/red]")
            return
        output.console.print(f"[yellow]Snoozed ticket {t.id} for {snooze_days} day(s).[/yellow]")
    elif action == "reopen":
        t = reopen_ticket(ticket_id)
        if not t:
            output.console.print(f"[red]Ticket '{ticket_id}' not found.[/red]")
            return
        output.console.print(f"[cyan]Reopened ticket {t.id}: {t.title}[/cyan]")


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
    parser.add_argument("--port", type=int, default=7337, metavar="PORT",
                        help="port for the web UI (default: 7337)")
    parser.add_argument("--tunnel", action="store_true",
                        help="expose the web UI publicly via a free Cloudflare quick tunnel (no account needed)")
    parser.add_argument("--auth", default=None, metavar="USER:PASS",
                        help="enable HTTP Basic auth on the web UI (format: user:password)")
    parser.add_argument("--scan", action="store_true",
                        help="run a security scan (firewall, CVEs, misconfigs) on this machine")
    parser.add_argument("--scan-schedule", metavar="FREQ",
                        choices=["hourly", "daily", "weekly"],
                        dest="scan_schedule",
                        help="print setup instructions for automatic scanning (hourly/daily/weekly)")
    parser.add_argument("--scan-status", action="store_true", dest="scan_status",
                        help="show when the last automatic scan ran")
    parser.add_argument("--scan-network", action="store_true", dest="scan_network",
                        help="also discover and check IoT/smart home devices on the LAN (use with --scan)")
    parser.add_argument("--scan-severity", default=None, metavar="LEVEL", dest="scan_severity",
                        choices=["critical", "high", "medium", "low", "info"],
                        help="only show findings at this severity level and above (use with --scan)")
    parser.add_argument("--scan-fix", action="store_true", dest="scan_fix",
                        help="prompt to apply safe fixes after scanning (use with --scan)")
    parser.add_argument("--scan-no-explain", action="store_true", dest="scan_no_explain",
                        help="skip Claude explanations in --scan (faster, no API key needed)")
    parser.add_argument("--scan-quiet", action="store_true", dest="scan_quiet",
                        help="only print a one-line summary plus critical/high findings (use with --scan, ideal for scheduled scans)")
    parser.add_argument("--scan-malware", nargs="?", const="~", metavar="PATH",
                        dest="scan_malware",
                        help="run malware scan (heuristics + ClamAV if installed) on PATH (default: home dir)")
    parser.add_argument("--check-hash", metavar="FILE", dest="check_hash",
                        help="compute SHA-256 of FILE and look it up on VirusTotal")
    parser.add_argument("--vt-api-key", metavar="KEY", dest="vt_api_key",
                        help="VirusTotal API key for --check-hash (or set $VIRUSTOTAL_API_KEY)")
    # ── Ticket management ───────────────────────────────────────────────────────
    parser.add_argument("--tickets", action="store_true",
                        help="list open tickets")
    parser.add_argument("--ticket-close", metavar="ID", dest="ticket_close",
                        help="close a ticket by ID")
    parser.add_argument("--ticket-snooze", metavar="ID", dest="ticket_snooze",
                        help="snooze a ticket for N days (default 7, use --snooze-days to change)")
    parser.add_argument("--snooze-days", metavar="N", dest="snooze_days", type=int, default=7,
                        help="number of days to snooze a ticket (use with --ticket-snooze)")
    parser.add_argument("--ticket-reopen", metavar="ID", dest="ticket_reopen",
                        help="reopen a closed or snoozed ticket")
    parser.add_argument("--ticket-note", metavar="ID", dest="ticket_note",
                        help="add a tech note to a ticket (use with --note \"text\")")
    parser.add_argument("--note", metavar="TEXT", dest="note_text",
                        help="note text to attach (use with --ticket-note)")
    # ── Discord / GitHub integration ────────────────────────────────────────────
    parser.add_argument("--discord-webhook", metavar="URL", dest="discord_webhook",
                        help="Discord webhook URL for scan notifications (or set $ERREX_DISCORD_WEBHOOK)")
    parser.add_argument("--github-token", metavar="TOKEN", dest="github_token",
                        help="GitHub token for creating Issues (or set $GITHUB_TOKEN)")
    parser.add_argument("--github-repo", metavar="OWNER/REPO", dest="github_repo",
                        help="GitHub repo to create Issues in (e.g. myorg/myrepo)")
    parser.add_argument("--verify", action="store_true",
                        help="after --scan-fix or --fix-apply, re-run to confirm the fix worked")
    parser.add_argument("--setup", action="store_true", help="run the setup wizard (API key, environment detection, shell integration)")
    parser.add_argument("--init", action="store_true",
                        help="detect project tech stack and save context for richer explanations")
    parser.add_argument("--context", metavar="FILE", help="attach a code file for more targeted explanations")
    parser.add_argument("--chat", action="store_true", help="stay in a follow-up Q&A loop after the explanation")
    parser.add_argument("--tokens", action="store_true", help="show token usage after each explanation")
    parser.add_argument("--notify", action="store_true", help="send a desktop notification when the explanation is ready")
    parser.add_argument("--update", action="store_true", help="check for a newer version of errex")
    parser.add_argument("--create-shortcut", action="store_true", dest="create_shortcut",
                        help="create a desktop shortcut that opens the errex web UI")
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
    parser.add_argument("--email-report", metavar="EMAIL", dest="email_report", default=None,
                        help="send a device health report to this address (use with --report-period)")
    parser.add_argument("--report-period", choices=["daily", "weekly", "monthly"], default="weekly",
                        dest="report_period",
                        help="period for --email-report (default: weekly)")
    parser.add_argument("--report-preview", action="store_true", dest="report_preview",
                        help="print the HTML health report to stdout without sending")
    parser.add_argument("--smtp-host", metavar="HOST", dest="smtp_host", default="",
                        help="SMTP host for --email-report")
    parser.add_argument("--smtp-port", metavar="PORT", type=int, dest="smtp_port", default=587,
                        help="SMTP port (default: 587)")
    parser.add_argument("--smtp-user", metavar="USER", dest="smtp_user", default="",
                        help="SMTP username")
    parser.add_argument("--smtp-password", metavar="PASS", dest="smtp_password", default="",
                        help="SMTP password (prefer env var ERREX_SMTP_PASSWORD)")
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
    parser.add_argument("--no-history", action="store_true", dest="no_history",
                        help="don't save this explanation to ~/.errex_history")
    parser.add_argument("--tls", action="store_true",
                        help="serve the web UI over HTTPS with a self-signed certificate")
    parser.add_argument("--cert", default=None, metavar="FILE",
                        help="path to TLS certificate file (PEM format) for --web")
    parser.add_argument("--key", default=None, metavar="FILE",
                        help="path to TLS private key file (PEM format) for --web")
    parser.add_argument("--privacy", action="store_true",
                        help="print what data errex reads and stores, then exit")
    parser.add_argument("--show-access", action="store_true", dest="show_access",
                        help="show all files and env vars errex has access to")
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
    parser.add_argument("--mcp", action="store_true",
                        help="start MCP server for Claude Desktop integration (communicates over stdio)")
    parser.add_argument("--activate", metavar="KEY", help="Activate an errex Pro license key")
    parser.add_argument("--license", action="store_true", help="Show license status")
    parser.set_defaults(**config)
    args = parser.parse_args()

    if args.mcp:
        from .mcp_server import serve
        serve()
        return

    if args.init:
        from .init_cmd import run_init
        run_init()
        return

    if args.scan_schedule:
        from ._scan_scheduler import setup_cron
        output.console.print(setup_cron(args.scan_schedule))
        return

    if args.scan_status:
        from ._scan_scheduler import print_scan_status
        print_scan_status()
        return

    if getattr(args, "tickets", False):
        _print_tickets()
        return

    if getattr(args, "ticket_close", None):
        _ticket_action("close", args.ticket_close,
                       github_repo=getattr(args, "github_repo", None) or config.get("github_repo"),
                       github_token=getattr(args, "github_token", None) or config.get("github_token"),
                       discord_webhook=(getattr(args, "discord_webhook", None)
                                        or config.get("discord_webhook")
                                        or __import__("os").environ.get("ERREX_DISCORD_WEBHOOK")))
        return

    if getattr(args, "ticket_snooze", None):
        _ticket_action("snooze", args.ticket_snooze,
                       snooze_days=getattr(args, "snooze_days", 7))
        return

    if getattr(args, "ticket_reopen", None):
        _ticket_action("reopen", args.ticket_reopen)
        return

    if getattr(args, "ticket_note", None):
        note_text = getattr(args, "note_text", None)
        if not note_text:
            output.err_console.print("[red]errex: --ticket-note requires --note \"text\"[/red]")
            sys.exit(1)
        from .tickets import add_note
        t = add_note(args.ticket_note, note_text)
        if not t:
            output.console.print(f"[red]Ticket '{args.ticket_note}' not found.[/red]")
            sys.exit(1)
        output.console.print(f"[green]✓ Note added to ticket {t.id}: {t.title}[/green]")
        output.console.print(f"  [dim]\"{note_text}\"[/dim]")
        return

    # First-run scan (once only, no API key needed)
    _skip_first_scan = (
        args.scan or args.setup
        or getattr(args, "scan_schedule", None)
        or getattr(args, "scan_status", False)
        or getattr(args, "scan_malware", None)
        or getattr(args, "check_hash", None)
        or getattr(args, "email_report", None)
        or getattr(args, "report_preview", False)
        or getattr(args, "tickets", False)
        or getattr(args, "ticket_close", None)
        or getattr(args, "ticket_snooze", None)
        or getattr(args, "ticket_reopen", None)
        or getattr(args, "ticket_note", None)
        or getattr(args, "create_shortcut", False)
        or args.history is not None or args.stats
        or args.list_profiles or args.completion or args.doctor
    )
    if not _skip_first_scan:
        from ._first_run import is_first_run, run_first_scan
        if is_first_run():
            run_first_scan()

    _constants.API_TIMEOUT = args.timeout

    no_color = args.no_color or args.ci
    width = args.word_wrap or None
    if no_color or width:
        output.console = Console(no_color=no_color, highlight=False, width=width)
        output.err_console = Console(stderr=True, no_color=no_color, highlight=False, width=width)

    if args.ci:
        args.terse = True

    if args.activate:
        from .license import activate
        result = activate(args.activate)
        if result["success"]:
            output.console.print(f"\n[green]✓ errex {result['tier'].capitalize()} activated![/green] "
                                 f"Valid until {result['expiry'][:4]}/{result['expiry'][4:]}\n")
        else:
            output.console.print(f"\n[red]✗[/red] {result['error']}\n")
            raise SystemExit(1)
        return

    if getattr(args, "license", False):
        from .license import show_license_status
        show_license_status()
        return

    if args.privacy:
        from .security import get_privacy_text
        output.console.print(get_privacy_text())
        return

    if args.show_access:
        from .security import get_permissions_summary
        import json
        perm = get_permissions_summary()
        output.console.rule("[bold cyan]errex — Data Access[/bold cyan]")
        output.console.print("\n[bold]Files:[/bold]")
        for name, info in perm["files"].items():
            status = f"{info['size_kb']} KB" if info["exists"] else "not found"
            output.console.print(f"  {name:<14} {info['path']}  ({status})")
        output.console.print("\n[bold]Environment variables:[/bold]")
        for k, v in perm["environment"].items():
            output.console.print(f"  {k:<22} {v}")
        output.console.print("\n[bold]Network (only when features are used):[/bold]")
        for item in perm["network"]:
            output.console.print(f"  • {item}")
        output.console.print()
        return

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

    if args.report_preview:
        from .email_report import print_report
        print_report(period=args.report_period)
        return

    if args.email_report:
        from .email_report import send_email_report
        import os as _os
        send_email_report(
            to_addr=args.email_report,
            smtp_host=args.smtp_host or cfg.get("smtp_host", "localhost"),
            smtp_port=args.smtp_port or int(cfg.get("smtp_port", 587)),
            smtp_user=args.smtp_user or cfg.get("smtp_user", ""),
            smtp_password=args.smtp_password or _os.environ.get("ERREX_SMTP_PASSWORD", "") or cfg.get("smtp_password", ""),
            period=args.report_period,
        )
        output.console.print(f"[green]✓[/green] Health report sent to {args.email_report}")
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
        serve(host=args.host, port=args.port, auth=args.auth, tunnel=args.tunnel,
              tls=args.tls, cert=args.cert, key=args.key)
        return

    if args.update:
        check_for_update()
        return

    if getattr(args, "create_shortcut", False):
        from .launcher import run_create_shortcut
        run_create_shortcut()
        return

    if args.setup:
        run_setup()
        return

    if args.scan:
        from .license import require_pro
        require_pro("scan")
        import json as _json
        import os as _os
        from .scan import run_scan, explain_findings, auto_fix, detect_platform
        from .scanners._base import SEVERITIES

        plat = detect_platform()
        _severity_icons = {
            "critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪",
        }

        def _progress(name, done, total):
            output.console.print(f"  Checking [dim]{name}[/dim]…", end="\r")

        output.console.print(f"\n  Scanning [bold]{plat}[/bold]…\n")
        result = run_scan(
            network=args.scan_network,
            severity_filter=args.scan_severity,
            progress_cb=_progress,
        )
        output.console.print(" " * 60, end="\r")  # clear progress line
        try:
            from ._scan_scheduler import log_scan_result
            log_scan_result(result)
        except Exception:
            pass

        if args.output == "json" if hasattr(args, "output") and args.output and args.output.endswith(".json") else False:
            print(_json.dumps(result.to_dict(), indent=2))
            return

        if not result.findings:
            output.console.print("  [green]✔ No issues found.[/green]\n")
            return

        # Display findings grouped by severity (quiet mode: critical/high only, one line each)
        _shown_severities = ("critical", "high") if args.scan_quiet else SEVERITIES
        for severity in _shown_severities:
            for finding in result.findings:
                if finding.severity != severity:
                    continue
                icon = _severity_icons.get(severity, "•")
                output.console.print(
                    f"\n  {icon} [bold]{severity.upper()}[/bold]  {finding.title}"
                )
                if args.scan_quiet:
                    continue
                for line in finding.detail.splitlines()[:5]:
                    output.console.print(f"     [dim]{line}[/dim]")
                if finding.fix_cmd:
                    output.console.print(f"     Fix: [cyan]{finding.fix_cmd}[/cyan]")

        total = len(result.findings)
        fixable = sum(1 for f in result.findings if f.is_fixable())
        output.console.print(
            f"\n  ─── {total} finding(s), {fixable} auto-fixable ───────────────────────────\n"
        )

        # Explain with Claude (skipped in quiet mode — scheduled scans don't need streamed prose)
        if not args.scan_no_explain and not args.scan_quiet:
            api_key = _os.environ.get("ANTHROPIC_API_KEY")
            if api_key:
                output.console.print("  [bold]Explanations[/bold] (Claude)\n")
                for finding in result.findings:
                    if finding.severity == "info":
                        continue
                    icon = _severity_icons.get(finding.severity, "•")
                    output.console.print(f"  {icon} [bold]{finding.title}[/bold]")

                    def _stream(fid, tok, _fid=finding.id):
                        if fid == _fid:
                            output.console.print(tok, end="")

                    explain_findings([finding], api_key, stream_cb=_stream)
                    output.console.print("\n")

        # Batch fix by severity
        _auto_fixed_ids: set[str] = set()
        if args.scan_fix and args.scan_quiet:
            output.console.print("  [dim]--scan-fix prompts are skipped in quiet mode (unattended scans).[/dim]")
        elif args.scan_fix:
            fixable_findings = [f for f in result.findings if f.is_fixable()]
            if not fixable_findings:
                output.console.print("  No auto-fixable issues found.\n")
            else:
                for severity in SEVERITIES:
                    batch = [f for f in fixable_findings if f.severity == severity]
                    if not batch:
                        continue
                    output.console.print(
                        f"\n  Apply [bold]{len(batch)} {severity.upper()}[/bold] fix(es)?"
                    )
                    for f in batch:
                        output.console.print(
                            f"    • {f.title}  [dim]→  {f.fix_cmd or 'python fix'}[/dim]"
                        )
                    resp = input("  [y/N] ").strip().lower()
                    if resp == "y":
                        fix_results = auto_fix(batch)
                        for r in fix_results:
                            mark = "[green]✔[/green]" if r.success else "[red]✗[/red]"
                            output.console.print(f"  {mark} {r.message}")
                            if r.success:
                                _auto_fixed_ids.add(r.finding_id)
        if args.verify:
            from .scan import verify_scan
            output.console.print("\n[bold]Verifying fixes...[/bold]")
            vr = verify_scan(result)
            if vr["resolved"]:
                output.console.print(f"[green]✓ Resolved:[/green] {', '.join(vr['resolved'])}")
            if vr["still_present"]:
                output.console.print(f"[yellow]⚠ Still present:[/yellow] {', '.join(vr['still_present'])}")
            if vr["new_issues"]:
                output.console.print(f"[red]! New issues:[/red] {', '.join(vr['new_issues'])}")

        # ── Ticket + GitHub + Discord integration ──────────────────────────────
        # Flags take priority; fall back to config file, then env vars
        _gh_repo    = getattr(args, "github_repo", None)  or config.get("github_repo")
        _gh_token   = getattr(args, "github_token", None) or config.get("github_token")
        _disc_hook  = (getattr(args, "discord_webhook", None)
                       or config.get("discord_webhook")
                       or __import__("os").environ.get("ERREX_DISCORD_WEBHOOK"))
        if result.findings and (_gh_repo or _disc_hook):
            from .tickets import create_ticket, find_by_finding_id
            from .discord_notify import notify_new_ticket, notify_scan_summary
            if _gh_repo:
                from .github_sync import create_issue
            new_tickets = 0
            for finding in result.findings:
                if finding.severity not in ("critical", "high", "medium"):
                    continue
                if finding.id in _auto_fixed_ids:
                    continue  # successfully auto-fixed this run — don't open a ticket
                existing = find_by_finding_id(finding.id)
                if existing and existing.effective_status() in ("open", "snoozed"):
                    continue  # active ticket exists; skip (closed tickets allow re-ticketing)
                ticket = create_ticket(
                    title=finding.title,
                    severity=finding.severity,
                    detail=finding.detail,
                    source="scan",
                    finding_id=finding.id,
                )
                new_tickets += 1
                gh_issue_url = None
                if _gh_repo:
                    resp = create_issue(ticket, _gh_repo, token=_gh_token)
                    if "number" in resp:
                        from .tickets import update_ticket
                        update_ticket(ticket.id, github_issue_number=resp["number"])
                        owner_repo = _gh_repo
                        gh_issue_url = f"https://github.com/{owner_repo}/issues/{resp['number']}"
                        output.console.print(
                            f"  [dim]GitHub Issue #{resp['number']} opened → {gh_issue_url}[/dim]"
                        )
                    elif "error" in resp:
                        output.console.print(f"  [yellow]GitHub: {resp['error']}[/yellow]")
                if _disc_hook:
                    notify_new_ticket(ticket, webhook_url=_disc_hook, github_issue_url=gh_issue_url)
            if _disc_hook:
                from .tickets import get_open_tickets
                _open = get_open_tickets()
                open_tickets = len(_open)
                crit_count   = sum(1 for t in _open if t.severity == "critical")
                notify_scan_summary(open_tickets, crit_count, new_tickets, webhook_url=_disc_hook)
            if new_tickets:
                output.console.print(f"\n  [cyan]{new_tickets} new ticket(s) created.[/cyan] Run [bold]errex --tickets[/bold] to view.\n")
        return

    if getattr(args, "scan_malware", None):
        from pathlib import Path as _Path
        from .scan import run_malware_scan
        from .scanners._base import SEVERITIES as _SEV
        _mpath = args.scan_malware
        if _mpath == "~":
            _mpath = str(_Path.home())
        output.console.print(f"\n[bold]Malware scan:[/bold] {_mpath}\n")
        _sev_icons = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}
        def _mscan_progress(name, done, total):
            output.console.print(f"  [dim]checking {name}…[/dim]", end="\r")
        _mresult = run_malware_scan(path=_mpath, progress_cb=_mscan_progress)
        output.console.print(" " * 60, end="\r")  # clear progress line
        if not _mresult.findings:
            output.console.print("  [green]✓ No malware indicators found.[/green]\n")
        else:
            for _f in sorted(_mresult.findings, key=lambda x: x.severity_rank()):
                _icon = _sev_icons.get(_f.severity, "•")
                output.console.print(f"  {_icon} [{_f.severity.upper()}] {_f.title}")
                if _f.detail:
                    for _line in _f.detail.splitlines()[:5]:
                        output.console.print(f"      [dim]{_line}[/dim]")
                if _f.fix_cmd:
                    output.console.print(f"      [cyan]Fix:[/cyan] {_f.fix_cmd}")
                output.console.print()
        return

    if getattr(args, "check_hash", None):
        from .scanners.virustotal import check_file, format_result
        _vt_key = getattr(args, "vt_api_key", None)
        output.console.print(f"\n[bold]VirusTotal hash check:[/bold] {args.check_hash}\n")
        _vt_result = check_file(args.check_hash, api_key=_vt_key)
        _summary = format_result(_vt_result)
        if "MALICIOUS" in _summary:
            output.console.print(f"  [red]{_summary}[/red]")
        elif "SUSPICIOUS" in _summary:
            output.console.print(f"  [yellow]{_summary}[/yellow]")
        elif "CLEAN" in _summary:
            output.console.print(f"  [green]{_summary}[/green]")
        else:
            output.console.print(f"  [dim]{_summary}[/dim]")
        if "link" in _vt_result:
            output.console.print(f"\n  Full report: {_vt_result['link']}")
        output.console.print()
        return

    if args.export:
        fmt = args.export_format or ("html" if args.export.endswith(".html") else "md")
        export_history(args.export, fmt)
        return

    if args.explain_diff is not None:
        from .license import require_pro
        require_pro("explain_diff")
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
        from .license import require_pro
        require_pro("test_gen")
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
        from .license import require_pro
        require_pro("explain_code")
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
        no_history=args.no_history,
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
