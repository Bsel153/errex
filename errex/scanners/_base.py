"""Shared data model for all scanners."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

SEVERITIES = ("critical", "high", "medium", "low", "info")
_RANK = {s: i for i, s in enumerate(SEVERITIES)}


@dataclass
class Finding:
    id: str
    severity: str           # critical | high | medium | low | info
    category: str           # security | misconfiguration | error
    platform: str           # macos | windows | network | cross
    title: str
    detail: str
    fix_cmd: str | None = None
    fix_fn: Callable[[], bool] | None = None
    explanation: str = ""
    cve_ids: list[str] = field(default_factory=list)

    def is_fixable(self) -> bool:
        return self.fix_cmd is not None or self.fix_fn is not None

    def web_fixable(self) -> bool:
        """True if the fix can be applied from the web UI (no sudo / pure Python)."""
        return self.fix_fn is not None

    def severity_rank(self) -> int:
        return _RANK.get(self.severity, 99)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "severity": self.severity,
            "category": self.category,
            "platform": self.platform,
            "title": self.title,
            "detail": self.detail,
            "fix_cmd": self.fix_cmd,
            "fixable": self.is_fixable(),
            "web_fixable": self.web_fixable(),
            "explanation": self.explanation,
            "cve_ids": self.cve_ids,
        }


@dataclass
class FixResult:
    finding_id: str
    success: bool
    message: str

    def to_dict(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "success": self.success,
            "message": self.message,
        }


@dataclass
class ScanResult:
    platform: str
    started_at: str
    findings: list[Finding] = field(default_factory=list)
    fix_results: list[FixResult] = field(default_factory=list)

    def by_severity(self, severity: str) -> list[Finding]:
        return [f for f in self.findings if f.severity == severity]

    def fixable(self) -> list[Finding]:
        return [f for f in self.findings if f.is_fixable()]

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "started_at": self.started_at,
            "findings": [f.to_dict() for f in self.findings],
            "fix_results": [r.to_dict() for r in self.fix_results],
        }
