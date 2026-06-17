"""Create Jira issues from errex scan findings — no external dependencies."""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tickets import Ticket

_PRIORITY_MAP = {
    "critical": "Highest",
    "high":     "High",
    "medium":   "Medium",
    "low":      "Low",
    "info":     "Lowest",
}


def _get_credentials() -> tuple[str, str, str] | None:
    url = os.environ.get("JIRA_URL", "")
    user = os.environ.get("JIRA_USER", "")
    token = os.environ.get("JIRA_TOKEN", "")
    if url and user and token:
        return url.rstrip("/"), user, token
    return None


def _api(
    method: str,
    url: str,
    user: str,
    token: str,
    body: dict | None = None,
) -> dict:
    creds = base64.b64encode(f"{user}:{token}".encode()).decode()
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/json",
            "Accept": "application/json",
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
        return {"error": f"Jira API HTTP {e.code}: {e.reason}", "body": body_text}
    except Exception as e:
        return {"error": str(e)}


def create_issue(
    ticket: "Ticket",
    jira_url: str | None = None,
    jira_user: str | None = None,
    jira_token: str | None = None,
    project_key: str | None = None,
) -> dict:
    creds = _get_credentials()
    base_url = jira_url or (creds[0] if creds else "")
    user = jira_user or (creds[1] if creds else "")
    token = jira_token or (creds[2] if creds else "")
    project = project_key or os.environ.get("JIRA_PROJECT", "")

    if not base_url or not user or not token:
        return {
            "error": "Jira credentials not configured. "
                     "Set JIRA_URL, JIRA_USER, and JIRA_TOKEN env vars, "
                     "or pass --jira-url, --jira-user, --jira-token."
        }
    if not project:
        return {"error": "No Jira project key. Pass --jira-project KEY or set JIRA_PROJECT."}

    priority = _PRIORITY_MAP.get(ticket.severity, "Medium")
    description = (
        f"*Severity:* {ticket.severity.upper()}\n"
        f"*Source:* {ticket.source}\n"
        f"*errex ticket ID:* {ticket.id}\n\n"
        f"----\n\n{ticket.detail}"
    )

    payload = {
        "fields": {
            "project": {"key": project},
            "summary": f"[{ticket.severity.upper()}] {ticket.title}",
            "description": description,
            "issuetype": {"name": "Bug"},
            "priority": {"name": priority},
            "labels": ["errex"],
        },
    }

    url = f"{base_url}/rest/api/2/issue"
    result = _api("POST", url, user, token, payload)
    if "key" in result:
        result["url"] = f"{base_url}/browse/{result['key']}"
    return result
