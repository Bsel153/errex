"""Slack webhook notifications for errex tickets and scan summaries."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tickets import Ticket

_SEV_EMOJI = {
    "critical": ":red_circle:",
    "high":     ":large_orange_circle:",
    "medium":   ":large_yellow_circle:",
    "low":      ":large_blue_circle:",
    "info":     ":white_circle:",
}


def _get_webhook(url: str | None = None) -> str | None:
    return url or os.environ.get("ERREX_SLACK_WEBHOOK")


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
        return {"error": f"Slack webhook HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def notify_new_ticket(
    ticket: "Ticket",
    webhook_url: str | None = None,
    github_issue_url: str | None = None,
) -> dict:
    url = _get_webhook(webhook_url)
    if not url:
        return {"error": "No Slack webhook URL. Set $ERREX_SLACK_WEBHOOK or pass --slack-webhook."}

    icon = _SEV_EMOJI.get(ticket.severity, "•")
    text = f"{icon} *New Finding: {ticket.title}*\n"
    text += f">Severity: {ticket.severity.upper()} | Ticket: `{ticket.id}` | Source: {ticket.source}\n"
    text += f">{ticket.detail[:300]}"
    if github_issue_url:
        text += f"\n<{github_issue_url}|View GitHub Issue>"

    return _post(url, {"text": text})


def notify_ticket_closed(ticket: "Ticket", webhook_url: str | None = None) -> dict:
    url = _get_webhook(webhook_url)
    if not url:
        return {"error": "No Slack webhook URL."}

    text = f":white_check_mark: *Resolved: {ticket.title}*\n"
    text += f">Ticket `{ticket.id}` has been closed. (was {ticket.severity.upper()})"

    return _post(url, {"text": text})


def notify_fix_applied(title: str, webhook_url: str | None = None) -> dict:
    url = _get_webhook(webhook_url)
    if not url:
        return {"error": "No Slack webhook URL."}

    return _post(url, {"text": f":white_check_mark: *errex auto-fixed an issue*\n>{title}"})


def notify_explanation(
    text: str,
    error_snippet: str,
    webhook_url: str | None = None,
) -> dict:
    """Post an error explanation to Slack after the main explain flow completes."""
    url = _get_webhook(webhook_url)
    if not url:
        return {"error": "No Slack webhook URL. Set $ERREX_SLACK_WEBHOOK or pass --slack-webhook."}

    snippet = error_snippet[:200] + ("…" if len(error_snippet) > 200 else "")
    body = text[:1200] + ("\n_(truncated — run errex locally for full output)_" if len(text) > 1200 else "")

    message = (
        f":mag: *errex — Error Explained*\n"
        f">*Error snippet:* `{snippet}`\n\n"
        f"{body}"
    )
    return _post(url, {"text": message})


def notify_scan_summary(
    open_count: int,
    critical_count: int,
    new_count: int,
    webhook_url: str | None = None,
) -> dict:
    url = _get_webhook(webhook_url)
    if not url:
        return {"error": "No Slack webhook URL."}

    if open_count == 0:
        text = ":white_check_mark: *errex Scan — All Clear*\nNo open security issues."
    elif critical_count > 0:
        text = (
            f":red_circle: *errex Scan — {critical_count} Critical Issue(s)*\n"
            f">{open_count} total open, {new_count} new this scan."
        )
    else:
        text = (
            f":large_orange_circle: *errex Scan — {open_count} Open Issue(s)*\n"
            f">{new_count} new this scan."
        )

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"Open: *{open_count}* | Critical/High: *{critical_count}* | New: *{new_count}*"},
            ],
        },
    ]
    return _post(url, {"text": text, "blocks": blocks})
