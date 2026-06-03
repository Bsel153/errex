"""CVE/vulnerability database lookups via NVD and OSV (both free, no key required)."""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.parse
import urllib.request
from ._base import Finding

_NVD = "https://services.nvd.nist.gov/rest/json/cves/2.0"
_OSV_BATCH = "https://api.osv.dev/v1/querybatch"
_UA = "errex/0.21.0"


def _http_get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read())


def _http_post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "User-Agent": _UA},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read())


def lookup_nvd(keyword: str, limit: int = 5) -> list[dict]:
    """Search NVD by keyword. Returns list of CVE summary dicts."""
    params = urllib.parse.urlencode({"keywordSearch": keyword, "resultsPerPage": limit})
    try:
        data = _http_get(f"{_NVD}?{params}")
        results = []
        for item in data.get("vulnerabilities", []):
            cve = item.get("cve", {})
            metrics = cve.get("metrics", {})
            cvss_list = (
                metrics.get("cvssMetricV31")
                or metrics.get("cvssMetricV30")
                or metrics.get("cvssMetricV2")
                or []
            )
            cvss = cvss_list[0].get("cvssData", {}) if cvss_list else {}
            descs = cve.get("descriptions", [])
            desc = next((d["value"] for d in descs if d.get("lang") == "en"), "")
            results.append({
                "id": cve.get("id", ""),
                "severity": cvss.get("baseSeverity", "UNKNOWN"),
                "score": cvss.get("baseScore", 0.0),
                "summary": desc[:300],
                "published": cve.get("published", "")[:10],
            })
        return results
    except Exception:
        return []


def check_python_packages() -> Finding | None:
    """Check all installed Python packages against OSV for known CVEs (one batch request)."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--format=json"],
            capture_output=True, text=True, timeout=20,
        )
        packages: list[dict] = json.loads(result.stdout)
    except Exception:
        return None

    if not packages:
        return None

    capped = packages[:60]  # avoid very large payloads
    queries = [
        {"package": {"name": p["name"], "ecosystem": "PyPI"}, "version": p["version"]}
        for p in capped
    ]

    try:
        data = _http_post(_OSV_BATCH, {"queries": queries})
    except Exception:
        return None

    vulnerable: list[tuple[str, str, list]] = []
    for pkg, result_item in zip(capped, data.get("results", [])):
        vulns = result_item.get("vulns", [])
        if vulns:
            vulnerable.append((pkg["name"], pkg["version"], vulns))

    if not vulnerable:
        return None

    has_critical = any(
        any(
            v.get("database_specific", {}).get("severity") in ("HIGH", "CRITICAL")
            for v in vulns
        )
        for _, _, vulns in vulnerable
    )

    pkg_lines = "\n".join(
        f"  {name}=={version}: "
        + ", ".join(
            (v.get("aliases") or [v.get("id", "")])[0]
            for v in vulns[:2]
        )
        for name, version, vulns in vulnerable[:8]
    )

    fix_packages = " ".join(name for name, _, _ in vulnerable)
    return Finding(
        id="cve-python-packages",
        severity="high" if has_critical else "medium",
        category="security",
        platform="cross",
        title=f"{len(vulnerable)} installed Python package(s) have known vulnerabilities",
        detail=f"Vulnerable packages:\n{pkg_lines}\n\nRun 'pip list --outdated' to see available upgrades.",
        fix_cmd=f"pip install --upgrade {fix_packages}",
        cve_ids=[
            a
            for _, _, vulns in vulnerable
            for v in vulns
            for a in (v.get("aliases") or [v.get("id", "")])
            if a.startswith("CVE-")
        ][:10],
    )
