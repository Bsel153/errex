"""Prometheus metrics exporter for errex."""
from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from . import output
from ._paths import HISTORY_FILE


def _count_history_errors(hours: int = 24) -> int:
    if not HISTORY_FILE.exists():
        return 0
    cutoff = time.time() - hours * 3600
    count = 0
    for line in HISTORY_FILE.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            ts = entry.get("timestamp", "")
            if ts:
                from datetime import datetime
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.timestamp() >= cutoff:
                    count += 1
        except Exception:
            continue
    return count


def _scan_metrics() -> dict:
    from .tickets import load_tickets
    tickets = load_tickets()
    open_tickets = [t for t in tickets if t.status == "open"]
    sev_counts = {}
    for t in open_tickets:
        sev_counts[t.severity] = sev_counts.get(t.severity, 0) + 1
    return {
        "open_total": len(open_tickets),
        "by_severity": sev_counts,
        "total_tickets": len(tickets),
    }


def _streak_days() -> int:
    status_file = Path.home() / ".errex_scan_status"
    if not status_file.exists():
        return 0
    try:
        data = json.loads(status_file.read_text())
        return data.get("streak", 0)
    except Exception:
        return 0


def generate_metrics() -> str:
    lines = []

    error_24h = _count_history_errors(24)
    lines.append("# HELP errex_errors_24h Number of errors explained in the last 24 hours")
    lines.append("# TYPE errex_errors_24h gauge")
    lines.append(f"errex_errors_24h {error_24h}")

    try:
        scan = _scan_metrics()
        lines.append("# HELP errex_tickets_open Number of open scan tickets")
        lines.append("# TYPE errex_tickets_open gauge")
        lines.append(f"errex_tickets_open {scan['open_total']}")

        lines.append("# HELP errex_tickets_total Total scan tickets ever created")
        lines.append("# TYPE errex_tickets_total counter")
        lines.append(f"errex_tickets_total {scan['total_tickets']}")

        lines.append("# HELP errex_tickets_by_severity Open tickets by severity")
        lines.append("# TYPE errex_tickets_by_severity gauge")
        for sev in ("critical", "high", "medium", "low", "info"):
            count = scan["by_severity"].get(sev, 0)
            lines.append(f'errex_tickets_by_severity{{severity="{sev}"}} {count}')
    except Exception:
        pass

    streak = _streak_days()
    lines.append("# HELP errex_health_streak_days Consecutive clean scan days")
    lines.append("# TYPE errex_health_streak_days gauge")
    lines.append(f"errex_health_streak_days {streak}")

    lines.append("")
    return "\n".join(lines)


def serve_prometheus(port: int, host: str = "127.0.0.1") -> None:
    class MetricsHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/metrics" or self.path == "/":
                body = generate_metrics().encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, fmt, *args):
            pass

    server = HTTPServer((host, port), MetricsHandler)
    output.console.print(f"[green]✓ Prometheus metrics at http://{host}:{port}/metrics[/green]")
    output.console.print("[dim]Press Ctrl+C to stop.[/dim]")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
