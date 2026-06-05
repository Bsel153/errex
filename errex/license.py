"""License key validation and feature gating for errex Pro."""
from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
from pathlib import Path

_SECRET = b"errex_lic_v1_7Kx9mP4qN8jH3n6L2wR5vT0yF"

_PRO_FEATURES = {
    "scan", "scan_malware", "check_hash", "tickets",
    "discord_webhook", "github_repo", "email_report",
    "watch", "chat", "test_gen", "explain_code",
    "explain_diff", "digest",
}

_CONFIG_FILE = Path.home() / ".errex.json"


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_config(data: dict) -> None:
    _CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _sign(payload: str) -> str:
    mac = hmac.new(_SECRET, payload.encode(), hashlib.sha256).digest()
    return base64.b32encode(mac[:5]).decode().rstrip("=")


def validate_key(key: str) -> dict | None:
    """Return license info dict or None if key is invalid."""
    if not key:
        return None
    parts = key.upper().strip().replace(" ", "").split("-")
    if len(parts) != 4 or parts[0] != "ERREX":
        return None
    tier = parts[1].lower()
    if tier not in ("pro", "team"):
        return None
    expiry = parts[2]
    sig = parts[3]

    if not hmac.compare_digest(sig, _sign(f"{tier}:{expiry}")):
        return None

    try:
        year, month = int(expiry[:4]), int(expiry[4:6])
        exp_date = datetime.date(year, month, 1)
    except (ValueError, IndexError):
        return None

    today = datetime.date.today()
    expired = today.year > year or (today.year == year and today.month > month)

    return {"tier": tier, "expiry": expiry, "expired": expired, "valid": not expired}


def get_license() -> dict | None:
    """Return current license info from config, or None."""
    key = _load_config().get("license_key", "")
    return validate_key(key) if key else None


def is_pro() -> bool:
    info = get_license()
    return bool(info and info.get("valid") and info.get("tier") in ("pro", "team"))


def activate(key: str) -> dict:
    """Activate a license key. Returns result dict."""
    info = validate_key(key)
    if info is None:
        return {"success": False, "error": "Invalid license key."}
    if info.get("expired"):
        yr, mo = info["expiry"][:4], info["expiry"][4:]
        return {"success": False, "error": f"License expired ({yr}/{mo})."}
    config = _load_config()
    config["license_key"] = key.upper().strip()
    _save_config(config)
    return {"success": True, "tier": info["tier"], "expiry": info["expiry"]}


def require_pro(feature: str) -> None:
    """Print upgrade prompt and exit if feature needs Pro and no valid license."""
    if feature not in _PRO_FEATURES:
        return
    if is_pro():
        return
    from rich.console import Console
    from rich.panel import Panel
    Console().print(Panel(
        f"[bold]--{feature.replace('_', '-')}[/bold] requires [bold yellow]errex Pro[/bold yellow].\n\n"
        "  Activate:  [cyan]errex --activate YOUR-LICENSE-KEY[/cyan]\n"
        "  Get a key: [cyan]https://errex.dev/pro[/cyan]  ($9/mo or $79/year)",
        title="[yellow]errex Pro required[/yellow]",
        border_style="yellow",
    ))
    raise SystemExit(1)


def show_license_status() -> None:
    """Print license status to console."""
    from rich.console import Console
    c = Console()
    info = get_license()
    if info is None:
        c.print("\n  [dim]No license activated.[/dim]")
        c.print("  Get errex Pro at [cyan]https://errex.dev/pro[/cyan]\n")
        return
    if info.get("expired"):
        c.print(f"\n  [red]License expired[/red] — tier: {info['tier']}, expired: {info['expiry'][:4]}/{info['expiry'][4:]}")
        c.print("  Renew at [cyan]https://errex.dev/pro[/cyan]\n")
    else:
        c.print(f"\n  [green]✓ errex {info['tier'].capitalize()}[/green] — active until {info['expiry'][:4]}/{info['expiry'][4:]}\n")
