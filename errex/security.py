"""Security helpers: TLS cert generation, privacy report, permissions summary."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

_TLS_DIR = Path.home() / ".errex_tls"
_HISTORY_FILE = Path.home() / ".errex_history"
_CACHE_FILE = Path.home() / ".errex_response_cache.json"
_CONFIG_FILE = Path.home() / ".errex_config.json"


# ── TLS ──────────────────────────────────────────────────────────────────────

def generate_self_signed_cert(cert_dir: Path = _TLS_DIR) -> tuple[str, str]:
    """Generate a self-signed RSA cert if one doesn't already exist.

    Returns (cert_path, key_path). Requires openssl on PATH.
    The cert is valid for 365 days and only suitable for local/private use.
    """
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path = cert_dir / "errex.crt"
    key_path = cert_dir / "errex.key"

    if cert_path.exists() and key_path.exists():
        return str(cert_path), str(key_path)

    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key_path),
            "-out", str(cert_path),
            "-days", "365", "-nodes",
            "-subj", "/CN=errex-local/O=errex/C=US",
        ],
        check=True,
        capture_output=True,
    )
    key_path.chmod(0o600)
    return str(cert_path), str(key_path)


# ── Privacy report ────────────────────────────────────────────────────────────

PRIVACY_TEXT = """\
errex Privacy Disclosure
════════════════════════

WHAT ERREX READS
  • Error text / stack traces you paste or pipe in
  • Source files you explicitly attach with --context
  • Your history file (~/.errex_history) for --history / --stats
  • ANTHROPIC_API_KEY environment variable (never logged or stored)
  • RHT_USERNAME / RHT_PASSWORD (only when --open-ticket is used)

WHAT IS SENT OVER THE NETWORK
  • Your error text (and context file, if provided) is sent to Anthropic's
    API to generate an explanation.  Anthropic's privacy policy applies:
    https://www.anthropic.com/privacy
  • Nothing is sent to any errex servers — there are none.
  • --tunnel sends traffic through Cloudflare (encrypted).
  • --share posts the explanation to paste.rs (public).
  • --digest-webhook / --webhook POSTs to the URL you supply.

WHAT IS STORED LOCALLY
  File                                 Contents
  ────────────────────────────────     ──────────────────────────────
  ~/.errex_history                     Error text + explanation (truncated to 200 chars)
  ~/.errex_response_cache.json         SHA-1 fingerprinted explanations (30-day TTL)
  ~/.errex_config.json                 Your settings (model, brief, etc.)
  ~/.errex_tls/                        Self-signed TLS cert (if --tls was used)

WHAT IS NOT STORED
  • Raw API keys are never written to disk.
  • No telemetry, analytics, or crash reporting.
  • No data is ever sent to the errex project or its maintainers.

HOW TO OPT OUT
  --no-history          Don't save this explanation to ~/.errex_history
  --clear-history       Delete all history
  --clear-cache         Delete the response cache
  errex is open source — you can audit every line of code.
"""


def get_privacy_text() -> str:
    return PRIVACY_TEXT


def get_permissions_summary() -> dict:
    """Return a structured summary of all files and env vars errex accesses."""
    import json

    def _file_info(p: Path) -> dict:
        if not p.exists():
            return {"path": str(p), "exists": False, "size_kb": 0}
        size = round(p.stat().st_size / 1024, 1)
        return {"path": str(p), "exists": True, "size_kb": size}

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    rht_user = os.environ.get("RHT_USERNAME", "")

    return {
        "files": {
            "history": _file_info(_HISTORY_FILE),
            "cache": _file_info(_CACHE_FILE),
            "config": _file_info(_CONFIG_FILE),
            "tls_cert": _file_info(_TLS_DIR / "errex.crt"),
        },
        "environment": {
            "ANTHROPIC_API_KEY": f"set (sk-ant-***…{api_key[-4:]})" if len(api_key) > 8 else ("set" if api_key else "not set"),
            "RHT_USERNAME": rht_user if rht_user else "not set",
            "RHT_PASSWORD": "set" if os.environ.get("RHT_PASSWORD") else "not set",
            "HOME": os.environ.get("HOME", ""),
        },
        "network": [
            "Anthropic API (api.anthropic.com) — only when explaining errors",
            "Cloudflare tunnel (trycloudflare.com) — only with --tunnel",
            "paste.rs — only with --share",
            "Your webhook URL — only with --webhook / --digest-webhook",
            "Red Hat API (api.access.redhat.com) — only with --open-ticket",
        ],
    }
