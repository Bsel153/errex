"""Optional cloud sync — uploads scan summaries and ticket events to an RHT backend.

Inert by default: nothing leaves the machine unless the customer opts in by
setting a sync endpoint and license key (config keys ``sync_url`` /
``sync_key``, or $ERREX_SYNC_URL / $ERREX_SYNC_KEY). Mirrors the
discord_notify.py pattern for optional outbound integrations.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tickets import Ticket

_TIMEOUT = 10


def _get_endpoint(url: str | None = None, key: str | None = None) -> tuple[str | None, str | None]:
    url = url or os.environ.get("ERREX_SYNC_URL")
    key = key or os.environ.get("ERREX_SYNC_KEY")
    return url, key


def is_enabled(config: dict | None = None) -> bool:
    """Return True if sync is configured (a sync URL is set)."""
    config = config or {}
    url, _ = _get_endpoint(config.get("sync_url"), config.get("sync_key"))
    return bool(url)


def _post(url: str, key: str | None, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "errex"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return {"ok": True, "status": resp.status}
    except urllib.error.HTTPError as e:
        return {"error": f"Sync HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def sync_scan_summary(
    summary: dict,
    url: str | None = None,
    key: str | None = None,
) -> dict:
    """Upload a scan-summary payload (same shape as the local scan log entry)."""
    endpoint, token = _get_endpoint(url, key)
    if not endpoint:
        return {"error": "Cloud sync is not configured. Set sync_url / $ERREX_SYNC_URL to enable it."}
    return _post(f"{endpoint.rstrip('/')}/v1/scans", token, summary)


def sync_ticket_event(
    ticket: "Ticket",
    event: str = "opened",
    url: str | None = None,
    key: str | None = None,
) -> dict:
    """Upload a ticket lifecycle event ('opened' or 'closed')."""
    endpoint, token = _get_endpoint(url, key)
    if not endpoint:
        return {"error": "Cloud sync is not configured. Set sync_url / $ERREX_SYNC_URL to enable it."}
    payload = {"event": event, "ticket": ticket.to_dict()}
    return _post(f"{endpoint.rstrip('/')}/v1/tickets", token, payload)
