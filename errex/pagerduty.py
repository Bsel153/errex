"""PagerDuty Events API v2 integration for errex scan findings."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tickets import Ticket

_PD_API = "https://events.pagerduty.com/v2/enqueue"

_SEV_MAP = {
    "critical": "critical",
    "high":     "error",
    "medium":   "warning",
    "low":      "info",
    "info":     "info",
}

# Only fire PagerDuty for these severities
_FIRE_SEVERITIES = {"critical", "high"}


def create_incident(ticket: "Ticket", routing_key: str) -> dict:
    """Trigger a PagerDuty incident for a critical or high-severity ticket.

    Returns {"ok": True} on success, {"error": "..."} on failure.
    Returns {"skipped": True} when severity is below high.
    """
    if ticket.severity not in _FIRE_SEVERITIES:
        return {"skipped": True, "reason": f"severity {ticket.severity!r} below threshold"}

    severity = _SEV_MAP.get(ticket.severity, "error")
    payload = {
        "routing_key": routing_key,
        "event_action": "trigger",
        "dedup_key": ticket.id,
        "payload": {
            "summary": ticket.title,
            "severity": severity,
            "source": "errex",
            "custom_details": {
                "severity": ticket.severity,
                "detail": ticket.detail[:500],
                "source": ticket.source,
                "ticket_id": ticket.id,
            },
        },
    }

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        _PD_API, data=data, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "errex"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_body = json.loads(resp.read())
            return {"ok": True, "dedup_key": resp_body.get("dedup_key")}
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode(errors="replace")
        except Exception:
            body = ""
        return {"error": f"PagerDuty HTTP {e.code}: {e.reason}", "body": body}
    except Exception as e:
        return {"error": str(e)}


def get_routing_key(explicit: str | None = None) -> str | None:
    """Return routing key from argument or env var."""
    return explicit or os.environ.get("PAGERDUTY_ROUTING_KEY")
