"""Sync errex tickets to GitHub Issues — no external dependencies."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tickets import Ticket

_SEVERITY_LABELS = {
    "critical": "severity: critical",
    "high": "severity: high",
    "medium": "severity: medium",
    "low": "severity: low",
    "info": "severity: info",
}

_SEV_EMOJI = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🔵",
    "info": "⚪",
}

_LABEL_COLORS = {
    "errex":              ("EE0000", "Created by errex scanner"),
    "severity: critical": ("b60205", ""),
    "severity: high":     ("e4e669", ""),
    "severity: medium":   ("fbca04", ""),
    "severity: low":      ("0075ca", ""),
    "severity: info":     ("cfd3d7", ""),
}


def _get_token(token: str | None = None) -> str | None:
    return token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def _parse_repo(repo: str) -> tuple[str, str] | None:
    parts = repo.split("/", 1)
    if len(parts) != 2 or not parts[1]:
        return None
    return parts[0], parts[1]


def _api(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "errex",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            body_text = e.read().decode(errors="replace")
        except Exception:
            body_text = ""
        return {"error": f"GitHub API HTTP {e.code}: {e.reason}", "body": body_text}
    except Exception as e:
        return {"error": str(e)}


def ensure_labels(repo: str, token: str | None = None) -> None:
    """Create errex severity labels on the repo if they don't already exist."""
    tok = _get_token(token)
    if not tok:
        return
    parsed = _parse_repo(repo)
    if not parsed:
        return
    owner, repo_name = parsed
    url = f"https://api.github.com/repos/{owner}/{repo_name}/labels"
    existing = _api("GET", url, tok)
    if not isinstance(existing, list):
        return
    existing_names = {lbl["name"] for lbl in existing}
    for name, (color, desc) in _LABEL_COLORS.items():
        if name not in existing_names:
            _api("POST", url, tok, {"name": name, "color": color, "description": desc})


def create_issue(ticket: "Ticket", repo: str, token: str | None = None) -> dict:
    """Open a GitHub Issue for *ticket*. Returns the API response dict."""
    tok = _get_token(token)
    if not tok:
        return {"error": "No GitHub token. Set $GITHUB_TOKEN or pass --github-token."}
    parsed = _parse_repo(repo)
    if not parsed:
        return {"error": f"Invalid repo '{repo}' — expected 'owner/repo'."}
    owner, repo_name = parsed

    ensure_labels(repo, tok)

    icon = _SEV_EMOJI.get(ticket.severity, "•")
    body = (
        f"**Severity:** {ticket.severity.upper()}\n"
        f"**Source:** {ticket.source}\n"
        f"**errex ticket ID:** `{ticket.id}`\n\n"
        f"---\n\n{ticket.detail}"
    )
    payload = {
        "title": f"{icon} [{ticket.severity.upper()}] {ticket.title}",
        "body": body,
        "labels": ["errex", _SEVERITY_LABELS.get(ticket.severity, "errex")],
    }
    url = f"https://api.github.com/repos/{owner}/{repo_name}/issues"
    return _api("POST", url, tok, payload)


def close_issue(issue_number: int, repo: str, token: str | None = None) -> dict:
    """Close a GitHub Issue by number."""
    tok = _get_token(token)
    if not tok:
        return {"error": "No GitHub token."}
    parsed = _parse_repo(repo)
    if not parsed:
        return {"error": f"Invalid repo '{repo}'."}
    owner, repo_name = parsed
    url = f"https://api.github.com/repos/{owner}/{repo_name}/issues/{issue_number}"
    return _api("PATCH", url, tok, {"state": "closed"})
