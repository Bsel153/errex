from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

from . import output

RHT_API_BASE = "https://api.access.redhat.com/rs"

_SEVERITY_NAMES = {1: "1 (Urgent)", 2: "2 (High)", 3: "3 (Normal)", 4: "4 (Low)"}


def open_rht_ticket(
    error_text: str,
    explanation: str = "",
    *,
    username: str | None = None,
    password: str | None = None,
    product: str = "Red Hat Enterprise Linux",
    version: str = "9.0",
    severity: int = 3,
) -> tuple[str, str] | None:
    """Open a support case on the Red Hat Customer Portal.

    Returns (case_number, case_url) on success, None on failure.
    Credentials fall back to RHT_USERNAME / RHT_PASSWORD env vars.
    """
    username = username or os.environ.get("RHT_USERNAME", "")
    password = password or os.environ.get("RHT_PASSWORD", "")

    if not username or not password:
        output.console.print(
            "[red]✗ Cannot open RHT ticket: set RHT_USERNAME and RHT_PASSWORD "
            "env vars (or pass --rht-username / --rht-password)[/red]"
        )
        return None

    severity_name = _SEVERITY_NAMES.get(severity, "3 (Normal)")
    first_line = error_text.strip().splitlines()[0][:200] if error_text.strip() else "Unresolved error"
    summary = f"errex: {first_line}"

    description = (
        "This ticket was opened by errex because the error could not be resolved automatically.\n\n"
    )
    if explanation:
        description += f"## errex analysis\n\n{explanation}\n\n"
    description += f"## Original error\n\n```\n{error_text.strip()}\n```"

    payload = json.dumps({
        "summary": summary,
        "description": description,
        "product": {"name": product},
        "version": {"name": version},
        "severity": {"name": severity_name},
    }).encode()

    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    req = urllib.request.Request(
        f"{RHT_API_BASE}/cases",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Basic {token}",
        },
        method="POST",
    )

    output.console.print("[dim]Opening Red Hat Customer Portal support case…[/dim]")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            case_number = data.get("caseNumber", "")
            case_uri = data.get(
                "caseUri",
                f"https://access.redhat.com/support/cases/#/case/{case_number}",
            )
            output.console.print(f"[green]✓ RHT case opened: #{case_number}[/green]")
            output.console.print(f"  {case_uri}")
            return case_number, case_uri
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace") if exc.fp else ""
        output.console.print(f"[red]✗ RHT API error {exc.code}: {body[:300]}[/red]")
        return None
    except Exception as exc:  # noqa: BLE001
        output.console.print(f"[red]✗ Failed to open RHT ticket: {exc}[/red]")
        return None
