"""Local ticket store — scan findings with open/closed/snoozed lifecycle."""
from __future__ import annotations

import datetime
import json
import uuid
from pathlib import Path

_TICKETS_FILE = Path.home() / ".errex_tickets.jsonl"

STATUSES = ("open", "closed", "snoozed")


class Ticket:
    def __init__(self, data: dict):
        self._d = data

    @property
    def id(self) -> str: return self._d["id"]
    @property
    def title(self) -> str: return self._d["title"]
    @property
    def severity(self) -> str: return self._d.get("severity", "info")
    @property
    def detail(self) -> str: return self._d.get("detail", "")
    @property
    def status(self) -> str: return self._d.get("status", "open")
    @property
    def source(self) -> str: return self._d.get("source", "scan")
    @property
    def created_at(self) -> str: return self._d.get("created_at", "")
    @property
    def updated_at(self) -> str: return self._d.get("updated_at", "")
    @property
    def finding_id(self) -> str | None: return self._d.get("finding_id")
    @property
    def github_issue_number(self) -> int | None: return self._d.get("github_issue_number")
    @property
    def snooze_until(self) -> str | None: return self._d.get("snooze_until")

    def to_dict(self) -> dict:
        return dict(self._d)

    def is_snoozed(self) -> bool:
        if self.status != "snoozed" or not self.snooze_until:
            return False
        return datetime.datetime.utcnow().isoformat() < self.snooze_until.rstrip("Z")

    def effective_status(self) -> str:
        if self.status == "snoozed" and not self.is_snoozed():
            return "open"
        return self.status


def _now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def create_ticket(
    title: str,
    severity: str,
    detail: str = "",
    source: str = "scan",
    finding_id: str | None = None,
) -> Ticket:
    data = {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "severity": severity,
        "detail": detail,
        "status": "open",
        "source": source,
        "finding_id": finding_id,
        "created_at": _now(),
        "updated_at": _now(),
        "github_issue_number": None,
        "snooze_until": None,
    }
    ticket = Ticket(data)
    _append(ticket)
    return ticket


def _append(ticket: Ticket) -> None:
    with open(_TICKETS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(ticket.to_dict()) + "\n")


def _rewrite(tickets: list[Ticket]) -> None:
    with open(_TICKETS_FILE, "w", encoding="utf-8") as f:
        for t in tickets:
            f.write(json.dumps(t.to_dict()) + "\n")


def load_all() -> list[Ticket]:
    if not _TICKETS_FILE.exists():
        return []
    tickets = []
    try:
        with open(_TICKETS_FILE, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    tickets.append(Ticket(json.loads(line)))
                except (json.JSONDecodeError, ValueError, KeyError):
                    continue
    except FileNotFoundError:
        pass  # removed between exists() check and open()
    return tickets


def update_ticket(ticket_id: str, **kwargs) -> Ticket | None:
    tickets = load_all()
    updated = None
    for t in tickets:
        if t.id == ticket_id or t.id.startswith(ticket_id):
            t._d.update(kwargs)
            t._d["updated_at"] = _now()
            updated = t
    if updated:
        _rewrite(tickets)
    return updated


def close_ticket(ticket_id: str) -> Ticket | None:
    return update_ticket(ticket_id, status="closed")


def reopen_ticket(ticket_id: str) -> Ticket | None:
    return update_ticket(ticket_id, status="open", snooze_until=None)


def snooze_ticket(ticket_id: str, days: int = 7) -> Ticket | None:
    until = (datetime.datetime.utcnow() + datetime.timedelta(days=days)).isoformat() + "Z"
    return update_ticket(ticket_id, status="snoozed", snooze_until=until)


def get_open_tickets() -> list[Ticket]:
    return [t for t in load_all() if t.effective_status() == "open"]


def find_by_finding_id(finding_id: str) -> Ticket | None:
    for t in load_all():
        if t.finding_id == finding_id:
            return t
    return None
