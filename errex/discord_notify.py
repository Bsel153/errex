"""Discord webhook notifications for errex tickets and scan summaries."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tickets import Ticket

_SEVERITY_COLORS = {
    "critical": 0xC00000,
    "high":     0xE07000,
    "medium":   0xC8A000,
    "low":      0x4488AA,
    "info":     0x8A8D90,
}

_SEV_EMOJI = {
    "critical": "🔴",
    "high":     "🟠",
    "medium":   "🟡",
    "low":      "🔵",
    "info":     "⚪",
}


def _get_webhook(url: str | None = None) -> str | None:
    return url or os.environ.get("ERREX_DISCORD_WEBHOOK")


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
        return {"error": f"Discord webhook HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def notify_new_ticket(
    ticket: "Ticket",
    webhook_url: str | None = None,
    github_issue_url: str | None = None,
) -> dict:
    """Post a new-ticket embed to Discord."""
    url = _get_webhook(webhook_url)
    if not url:
        return {"error": "No Discord webhook URL. Set $ERREX_DISCORD_WEBHOOK or pass --discord-webhook."}

    icon = _SEV_EMOJI.get(ticket.severity, "•")
    color = _SEVERITY_COLORS.get(ticket.severity, 0x8A8D90)
    fields = [
        {"name": "Severity", "value": ticket.severity.upper(), "inline": True},
        {"name": "Ticket ID", "value": f"`{ticket.id}`",       "inline": True},
        {"name": "Source",    "value": ticket.source,          "inline": True},
    ]
    if github_issue_url:
        fields.append({"name": "GitHub Issue", "value": f"[View →]({github_issue_url})", "inline": False})

    embed = {
        "title": f"{icon} New Finding: {ticket.title}",
        "description": ticket.detail[:300] + ("…" if len(ticket.detail) > 300 else ""),
        "color": color,
        "fields": fields,
        "footer": {"text": "errex security scanner"},
    }
    return _post(url, {"embeds": [embed]})


def notify_ticket_closed(ticket: "Ticket", webhook_url: str | None = None) -> dict:
    """Post a resolved-ticket embed to Discord."""
    url = _get_webhook(webhook_url)
    if not url:
        return {"error": "No Discord webhook URL."}

    embed = {
        "title": f"✅ Resolved: {ticket.title}",
        "description": f"Ticket `{ticket.id}` has been closed.",
        "color": 0x3D9970,
        "fields": [
            {"name": "Severity", "value": ticket.severity.upper(), "inline": True},
            {"name": "Source",   "value": ticket.source,           "inline": True},
        ],
        "footer": {"text": "errex security scanner"},
    }
    return _post(url, {"embeds": [embed]})


def notify_scan_summary(
    open_count: int,
    critical_count: int,
    new_count: int,
    webhook_url: str | None = None,
) -> dict:
    """Post a scan-summary embed to Discord."""
    url = _get_webhook(webhook_url)
    if not url:
        return {"error": "No Discord webhook URL."}

    if open_count == 0:
        color, title = 0x3D9970, "✅ errex Scan — All Clear"
        desc = "No open security issues."
    elif critical_count > 0:
        color = 0xC00000
        title = f"🔴 errex Scan — {critical_count} Critical Issue(s)"
        desc = f"{open_count} total open, {new_count} new this scan."
    else:
        color = 0xE07000
        title = f"🟠 errex Scan — {open_count} Open Issue(s)"
        desc = f"{new_count} new this scan."

    embed = {
        "title": title,
        "description": desc,
        "color": color,
        "fields": [
            {"name": "Open Tickets",  "value": str(open_count),    "inline": True},
            {"name": "Critical/High", "value": str(critical_count),"inline": True},
            {"name": "New This Scan", "value": str(new_count),     "inline": True},
        ],
        "footer": {"text": "errex security scanner"},
    }
    return _post(url, {"embeds": [embed]})
