"""Microsoft Teams webhook notifications for errex tickets and scan summaries."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tickets import Ticket


def _get_webhook(url: str | None = None) -> str | None:
    return url or os.environ.get("ERREX_TEAMS_WEBHOOK")


def _post(webhook_url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        webhook_url, data=data, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "errex"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"ok": True, "status": resp.status}
    except urllib.error.HTTPError as e:
        return {"error": f"Teams webhook HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def _message_card(summary: str, title: str, facts: list[dict]) -> dict:
    return {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": summary,
        "themeColor": "FF0000",
        "sections": [
            {
                "activityTitle": title,
                "facts": facts,
            }
        ],
    }


def notify_new_ticket(
    ticket: "Ticket",
    webhook_url: str | None = None,
    github_issue_url: str | None = None,
) -> dict:
    """Post a new-ticket card to Microsoft Teams."""
    url = _get_webhook(webhook_url)
    if not url:
        return {"error": "No Teams webhook URL. Set $ERREX_TEAMS_WEBHOOK or pass --teams-webhook."}

    facts = [
        {"name": "Severity", "value": ticket.severity.upper()},
        {"name": "Ticket ID", "value": ticket.id},
        {"name": "Source",    "value": ticket.source},
    ]
    if github_issue_url:
        facts.append({"name": "GitHub Issue", "value": github_issue_url})

    payload = _message_card(
        summary=f"New Finding: {ticket.title}",
        title=f"[{ticket.severity.upper()}] New Finding: {ticket.title}",
        facts=facts,
    )
    return _post(url, payload)


def notify_scan_summary(
    findings: list,
    webhook_url: str | None = None,
) -> dict:
    """Post a scan-summary card to Microsoft Teams."""
    url = _get_webhook(webhook_url)
    if not url:
        return {"error": "No Teams webhook URL."}

    total = len(findings)
    crit = sum(1 for f in findings if getattr(f, "severity", "") == "critical")

    facts = [
        {"name": "Total findings", "value": str(total)},
        {"name": "Critical",       "value": str(crit)},
    ]

    title = "errex Scan Complete — All Clear" if total == 0 else f"errex Scan: {total} finding(s)"
    payload = _message_card(
        summary=title,
        title=title,
        facts=facts,
    )
    return _post(url, payload)


def notify_explanation(
    text: str,
    error_snippet: str,
    webhook_url: str | None = None,
) -> dict:
    """Post an error explanation card to Microsoft Teams."""
    url = _get_webhook(webhook_url)
    if not url:
        return {"error": "No Teams webhook URL."}

    facts = [
        {"name": "Error", "value": error_snippet[:200]},
    ]
    payload = _message_card(
        summary="errex — Error Explained",
        title="errex — Error Explanation",
        facts=facts,
    )
    # Truncate explanation and add it in body
    payload["sections"][0]["activityText"] = text[:1000]
    return _post(url, payload)
