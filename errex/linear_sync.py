"""Create Linear issues from errex scan findings via the Linear GraphQL API."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tickets import Ticket

_LINEAR_API = "https://api.linear.app/graphql"

_PRIORITY_MAP = {
    "critical": 1,  # urgent
    "high":     2,  # high
    "medium":   3,  # medium
    "low":      4,  # low
    "info":     0,  # no priority
}


def _graphql(token: str, query: str, variables: dict | None = None) -> dict:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        _LINEAR_API, data=data, method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "errex",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode(errors="replace")
        except Exception:
            body = ""
        return {"error": f"Linear API HTTP {e.code}: {e.reason}", "body": body}
    except Exception as e:
        return {"error": str(e)}


def create_issue(
    ticket: "Ticket",
    team_id: str | None = None,
    token: str | None = None,
) -> dict:
    """Create a Linear issue from an errex ticket."""
    _token = token or os.environ.get("LINEAR_TOKEN", "")
    _team_id = team_id or os.environ.get("LINEAR_TEAM_ID", "")

    if not _token:
        return {
            "error": "Linear token not configured. Pass --linear-token TOKEN or set $LINEAR_TOKEN."
        }
    if not _team_id:
        return {
            "error": "Linear team ID not configured. Pass --linear-team TEAM_ID or set $LINEAR_TEAM_ID."
        }

    priority = _PRIORITY_MAP.get(ticket.severity, 0)
    title = f"[{ticket.severity.upper()}] {ticket.title}"
    description = (
        f"**Severity:** {ticket.severity.upper()}\n"
        f"**Source:** {ticket.source}\n"
        f"**errex ticket ID:** {ticket.id}\n\n"
        f"---\n\n{ticket.detail}"
    )

    mutation = """
    mutation CreateIssue($title: String!, $description: String!, $teamId: String!, $priority: Int) {
      issueCreate(input: {
        title: $title,
        description: $description,
        teamId: $teamId,
        priority: $priority
      }) {
        success
        issue {
          id
          identifier
          url
        }
      }
    }
    """

    variables = {
        "title": title,
        "description": description,
        "teamId": _team_id,
        "priority": priority,
    }

    result = _graphql(_token, mutation, variables)

    if "error" in result:
        return result

    errors = result.get("errors")
    if errors:
        return {"error": "; ".join(e.get("message", str(e)) for e in errors)}

    issue_data = result.get("data", {}).get("issueCreate", {})
    if not issue_data.get("success"):
        return {"error": "Linear issueCreate returned success=false"}

    issue = issue_data.get("issue", {})
    return {
        "id": issue.get("id"),
        "identifier": issue.get("identifier"),
        "url": issue.get("url"),
    }
