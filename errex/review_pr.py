"""Review a GitHub pull request using Claude."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

from . import output


def _parse_pr_url(url: str) -> tuple[str, str, int] | None:
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)", url)
    if m:
        return m.group(1), m.group(2), int(m.group(3))
    m = re.match(r"([^/]+)/([^/]+)#(\d+)$", url)
    if m:
        return m.group(1), m.group(2), int(m.group(3))
    return None


def _fetch_diff(owner: str, repo: str, number: int, token: str | None = None) -> str:
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
    headers = {
        "Accept": "application/vnd.github.v3.diff",
        "User-Agent": "errex",
    }
    if token:
        headers["Authorization"] = f"token {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode(errors="replace")


def _fetch_pr_info(owner: str, repo: str, number: int, token: str | None = None) -> dict:
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "errex",
    }
    if token:
        headers["Authorization"] = f"token {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def review_pr(
    url: str,
    model: str | None = None,
    token: str | None = None,
    copy: bool = False,
    show_tokens: bool = False,
    perf: bool = False,
) -> None:
    parsed = _parse_pr_url(url)
    if not parsed:
        output.err_console.print(f"[red]errex: cannot parse PR URL: {url!r}[/red]")
        output.err_console.print("  Expected: https://github.com/owner/repo/pull/123")
        sys.exit(1)

    owner, repo, number = parsed
    token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

    output.console.print(f"[dim]Fetching PR #{number} from {owner}/{repo}…[/dim]")
    try:
        diff = _fetch_diff(owner, repo, number, token)
    except urllib.error.HTTPError as e:
        output.err_console.print(f"[red]errex: GitHub API error: {e.code} {e.reason}[/red]")
        if e.code == 404:
            output.err_console.print("  PR not found or repo is private (pass --github-token)")
        sys.exit(1)

    if not diff.strip():
        output.console.print("[yellow]PR has no diff (empty or merged).[/yellow]")
        return

    try:
        info = _fetch_pr_info(owner, repo, number, token)
        title = info.get("title", f"PR #{number}")
        body = (info.get("body") or "")[:500]
    except Exception:
        title = f"PR #{number}"
        body = ""

    max_diff_chars = 12000
    if len(diff) > max_diff_chars:
        diff = diff[:max_diff_chars] + f"\n\n… (truncated — {len(diff)} chars total)"

    prompt = (
        f"You are a senior code reviewer. Review this GitHub pull request.\n\n"
        f"**PR Title:** {title}\n"
        f"**Description:** {body}\n\n"
        f"**Diff:**\n```diff\n{diff}\n```\n\n"
        f"Provide a structured review:\n"
        f"1. **Summary** — one sentence describing what the PR does\n"
        f"2. **Issues** — bugs, security problems, logic errors (file:line format)\n"
        f"3. **Suggestions** — improvements, simplifications, style\n"
        f"4. **Verdict** — approve / request changes / comment\n\n"
        f"Be concise. Only flag real issues, not style preferences."
    )

    from .core import call_claude
    from . import _constants

    model = model or os.environ.get("ERREX_MODEL") or _constants.DEFAULT_MODEL

    output.console.print(f"\n[bold]──── errex — PR Review: {title} ────[/bold]\n")
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
