"""VirusTotal file-hash lookup — requires a free VT API key."""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

_VT_API_URL = "https://www.virustotal.com/api/v3/files/{}"
_KEY_ENV = "VIRUSTOTAL_API_KEY"


def _get_api_key(api_key: str | None = None) -> str | None:
    return api_key or os.environ.get(_KEY_ENV)


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def lookup_hash(file_hash: str, api_key: str | None = None) -> dict:
    """Query VirusTotal for *file_hash*. Returns a result dict."""
    key = _get_api_key(api_key)
    if not key:
        return {"error": f"No VirusTotal API key. Set ${_KEY_ENV} or pass --vt-api-key."}

    url = _VT_API_URL.format(file_hash)
    req = urllib.request.Request(url, headers={"x-apikey": key})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"status": "not_found", "hash": file_hash}
        if e.code == 401:
            return {"error": "Invalid VirusTotal API key."}
        if e.code == 429:
            return {"error": "VirusTotal rate limit reached (free tier: 4 req/min). Retry in 60 s."}
        return {"error": f"VirusTotal HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"error": f"VirusTotal request failed: {e}"}

    try:
        stats = data["data"]["attributes"]["last_analysis_stats"]
        malicious = stats.get("malicious", 0)
        suspicious = stats.get("suspicious", 0)
        total = sum(stats.values())
        name = (data["data"]["attributes"].get("meaningful_name") or file_hash[:16] + "…")
        return {
            "status": "found",
            "hash": file_hash,
            "name": name,
            "malicious": malicious,
            "suspicious": suspicious,
            "total": total,
            "clean": total - malicious - suspicious,
            "ratio": f"{malicious}/{total}",
            "link": f"https://www.virustotal.com/gui/file/{file_hash}",
        }
    except (KeyError, TypeError):
        return {"error": "Unexpected VirusTotal response format.", "raw": str(data)[:300]}


def check_file(path: str | Path, api_key: str | None = None) -> dict:
    """Hash *path* and look it up on VirusTotal."""
    p = Path(path)
    if not p.exists():
        return {"error": f"File not found: {path}"}
    if not p.is_file():
        return {"error": f"Not a file: {path}"}
    file_hash = sha256_file(p)
    result = lookup_hash(file_hash, api_key=api_key)
    result.setdefault("file", str(p))
    return result


def format_result(result: dict) -> str:
    """Human-readable single-line summary of a VT lookup result."""
    if "error" in result:
        return f"[VT] Error: {result['error']}"
    status = result.get("status")
    if status == "not_found":
        return f"[VT] {result.get('file', result.get('hash', '?'))}: not in VirusTotal database (hash never seen)"
    m = result.get("malicious", 0)
    s = result.get("suspicious", 0)
    ratio = result.get("ratio", "?")
    name = result.get("name", "?")
    link = result.get("link", "")
    if m == 0 and s == 0:
        verdict = "CLEAN"
    elif m > 0:
        verdict = f"MALICIOUS ({ratio} engines)"
    else:
        verdict = f"SUSPICIOUS ({s} engines)"
    return f"[VT] {name}: {verdict}  {link}"
