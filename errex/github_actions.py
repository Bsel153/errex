"""Explain GitHub Actions job failures using Claude."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

from . import output, _constants


def _parse_run_url(url: str) -> tuple[str, str, str] | None:
    """Parse https://github.com/{owner}/{repo}/actions/runs/{run_id}"""
    m = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/actions/runs/(\d+)",
        url.strip(),
    )
    if m:
        return m.group(1), m.group(2), m.group(3)
    return None


def _gh_get(url: str, token: str | None) -> dict | list:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "errex",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _gh_get_text(url: str, token: str | None) -> str:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "errex",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 410:
            return "(log expired)"
        raise


def explain_github_actions(run_url: str, model: str | None = None, token: str | None = None) -> None:
    """Fetch failed GitHub Actions job logs and explain with Claude."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        output.err_console.print("[red]errex: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)

    parsed = _parse_run_url(run_url)
    if not parsed:
        output.err_console.print(
            f"[red]errex: cannot parse GitHub Actions URL: {run_url!r}[/red]\n"
            "  Expected: https://github.com/owner/repo/actions/runs/12345"
        )
        sys.exit(1)

    owner, repo, run_id = parsed
    _token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

    output.console.print(f"[dim]Fetching jobs for run {run_id} in {owner}/{repo}…[/dim]")

    try:
        jobs_data = _gh_get(
            f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/jobs",
            _token,
        )
    except urllib.error.HTTPError as e:
        output.err_console.print(f"[red]errex: GitHub API error: {e.code} {e.reason}[/red]")
        if e.code == 404:
            output.err_console.print("  Run not found or repo is private (pass --github-token)")
        sys.exit(1)
    except Exception as e:
        output.err_console.print(f"[red]errex: {e}[/red]")
        sys.exit(1)

    jobs = jobs_data.get("jobs", [])
    failed_jobs = [j for j in jobs if j.get("conclusion") == "failure"]

    if not failed_jobs:
        output.console.print("[green]No failed jobs found in this run.[/green]")
        return

    output.console.rule(f"[bold cyan]errex — GitHub Actions: {owner}/{repo} run {run_id}[/bold cyan]")
    output.console.print(f"\n[bold]{len(failed_jobs)} failed job(s):[/bold]\n")

    log_blocks: list[str] = []

    for job in failed_jobs[:3]:  # cap at 3 jobs
        job_id = job["id"]
        job_name = job.get("name", str(job_id))
        output.console.print(f"  • [red]{job_name}[/red]")

        try:
            log_text = _gh_get_text(
                f"https://api.github.com/repos/{owner}/{repo}/actions/jobs/{job_id}/logs",
                _token,
            )
            last_200 = "\n".join(log_text.splitlines()[-200:])
            log_blocks.append(f"=== Job: {job_name} ===\n{last_200}")
        except Exception as e:
            log_blocks.append(f"=== Job: {job_name} ===\n(could not fetch log: {e})")

    combined_log = "\n\n".join(log_blocks)
    if len(combined_log) > 10000:
        combined_log = combined_log[:10000] + "\n… (truncated)"

    prompt = (
        f"The following GitHub Actions job(s) failed in {owner}/{repo} (run {run_id}). "
        f"Explain why each job failed and provide specific steps to fix it. "
        f"Be concise and actionable. Use markdown.\n\n"
        f"```\n{combined_log}\n```"
    )

    from .core import call_claude

    _model = model or os.environ.get("ERREX_MODEL") or _constants.CONFIG_DEFAULTS["model"]

    output.console.print("\n[bold]Explanation (Claude):[/bold]\n")
    call_claude("github-actions-failure", model=_model, messages=[{"role": "user", "content": prompt}])
    print()
    output.console.rule(style="dim")
    output.console.print()
