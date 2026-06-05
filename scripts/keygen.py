#!/usr/bin/env python3
"""Generate errex license keys.

NOTE: This script is intentionally committed to the repo for internal use.
Do NOT bundle it in PyInstaller builds or distribute it to end users.
The secret being in the repo is an accepted tradeoff for this tier of product.
"""
import base64, hashlib, hmac, sys
from datetime import date

_SECRET = b"errex_lic_v1_7Kx9mP4qN8jH3n6L2wR5vT0yF"

def _sign(payload: str) -> str:
    mac = hmac.new(_SECRET, payload.encode(), hashlib.sha256).digest()
    return base64.b32encode(mac[:5]).decode().rstrip("=")

def generate(tier: str = "pro", months: int = 12) -> str:
    today = date.today()
    total_months = today.month + months
    exp_year = today.year + (total_months - 1) // 12
    exp_month = ((total_months - 1) % 12) + 1
    expiry = f"{exp_year}{exp_month:02d}"
    return f"ERREX-{tier.upper()}-{expiry}-{_sign(f'{tier}:{expiry}')}"

if __name__ == "__main__":
    tier = sys.argv[1] if len(sys.argv) > 1 else "pro"
    months = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    key = generate(tier, months)
    print(f"\n  License key: {key}")
    print(f"  Tier: {tier} | Valid for: {months} months\n")
