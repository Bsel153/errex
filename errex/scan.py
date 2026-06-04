"""errex scan — orchestrates platform checks and explains findings via Claude."""
from __future__ import annotations

import datetime
import platform as _sys_platform
import subprocess
from typing import Callable

from .scanners._base import Finding, FixResult, ScanResult, SEVERITIES

SCAN_EXPLAIN_PROMPT = """\
You are a security engineer reviewing a system scan result.

Finding: [{severity}] {title}
Detail: {detail}

In 3-4 sentences explain:
1. What this means in plain English
2. Why it is a risk
3. The single most important fix step

Be direct. No preamble.\
"""


def detect_platform() -> str:
    """Return 'macos', 'windows', or 'linux'."""
    s = _sys_platform.system().lower()
    if s == "darwin":
        return "macos"
    if s == "windows":
        return "windows"
    return "linux"


def run_scan(
    platform: str | None = None,
    network: bool = False,
    severity_filter: str | None = None,
    progress_cb: Callable[[str, int, int], None] | None = None,
) -> ScanResult:
    """
    Run all security checks for the given platform.

    progress_cb(check_name, checks_done, total_checks) is called before each check.
    severity_filter keeps only findings at that severity level and above
    (e.g. 'high' keeps critical + high, drops medium/low/info).
    """
    plat = platform or detect_platform()
    started_at = datetime.datetime.utcnow().isoformat() + "Z"

    checks: list[tuple[str, Callable[[], Finding | None]]] = []

    if plat == "macos":
        from .scanners import macos
        checks.extend(macos.get_checks())
    elif plat == "windows":
        from .scanners import windows
        checks.extend(windows.get_checks())
    elif plat == "linux":
        from .scanners import linux
        checks.extend(linux.get_checks())

    from .scanners import cve
    checks.append(("Python Package CVEs", cve.check_python_packages))

    findings: list[Finding] = []
    total = len(checks) + (1 if network else 0)

    for i, (name, fn) in enumerate(checks):
        if progress_cb:
            progress_cb(name, i, total)
        try:
            result = fn()
            if result is not None:
                findings.append(result)
        except Exception:
            pass

    if network:
        if progress_cb:
            progress_cb("Network devices", len(checks), total)
        try:
            from .scanners import network as net
            findings.extend(net.get_findings())
        except Exception:
            pass

    if severity_filter and severity_filter in SEVERITIES:
        threshold = SEVERITIES.index(severity_filter)
        findings = [f for f in findings if SEVERITIES.index(f.severity) <= threshold]

    return ScanResult(platform=plat, started_at=started_at, findings=findings)


def explain_findings(
    findings: list[Finding],
    api_key: str,
    model: str = "claude-sonnet-4-6",
    stream_cb: Callable[[str, str], None] | None = None,
) -> list[Finding]:
    """
    Fill in finding.explanation for each finding using Claude.
    stream_cb(finding_id, token) is called for each streamed token.
    Skips 'info' severity findings (device inventory, etc.).
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    for finding in findings:
        if finding.severity == "info":
            continue

        prompt = SCAN_EXPLAIN_PROMPT.format(
            severity=finding.severity.upper(),
            title=finding.title,
            detail=finding.detail[:500],
        )
        try:
            if stream_cb:
                parts: list[str] = []
                with client.messages.stream(
                    model=model,
                    max_tokens=300,
                    messages=[{"role": "user", "content": prompt}],
                ) as stream:
                    for token in stream.text_stream:
                        parts.append(token)
                        stream_cb(finding.id, token)
                finding.explanation = "".join(parts)
            else:
                resp = client.messages.create(
                    model=model,
                    max_tokens=300,
                    messages=[{"role": "user", "content": prompt}],
                )
                finding.explanation = resp.content[0].text
        except Exception as e:
            finding.explanation = f"[Could not generate explanation: {e}]"

    return findings


def auto_fix(
    findings: list[Finding],
    dry_run: bool = False,
) -> list[FixResult]:
    """
    Apply fixes for all fixable findings.

    Prefers fix_fn (Python, no shell) over fix_cmd (subprocess).
    With dry_run=True, reports what would be done without executing.
    """
    results: list[FixResult] = []

    for finding in findings:
        if not finding.is_fixable():
            continue

        if dry_run:
            desc = finding.fix_cmd or "python fix function"
            results.append(FixResult(finding.id, True, f"Would run: {desc}"))
            continue

        if finding.fix_fn:
            try:
                success = finding.fix_fn()
                results.append(FixResult(finding.id, success, "Applied" if success else "Failed"))
            except Exception as exc:
                results.append(FixResult(finding.id, False, str(exc)))
        elif finding.fix_cmd:
            try:
                proc = subprocess.run(
                    finding.fix_cmd, shell=True,
                    capture_output=True, text=True, timeout=30,
                )
                success = proc.returncode == 0
                msg = proc.stdout.strip() or proc.stderr.strip() or ("Applied" if success else "Failed")
                results.append(FixResult(finding.id, success, msg[:200]))
            except Exception as exc:
                results.append(FixResult(finding.id, False, str(exc)))

    return results


def verify_scan(
    before: "ScanResult",
    platform: str | None = None,
    network: bool = False,
) -> dict:
    """Re-run the scan and compare to a previous result to see what was resolved."""
    after = run_scan(platform=platform or before.platform, network=network)
    before_ids = {f.id for f in before.findings}
    after_ids = {f.id for f in after.findings}
    return {
        "resolved": sorted(before_ids - after_ids),
        "still_present": sorted(before_ids & after_ids),
        "new_issues": sorted(after_ids - before_ids),
        "after": after,
    }
