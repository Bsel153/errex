"""Project-level .errex.yml configuration."""
from __future__ import annotations

import sys
from pathlib import Path

from . import output

TEMPLATE = """\
# errex project configuration
# Place in your repo root; settings here override ~/.errexrc for this project.
# Commit to git so all team members share the same errex defaults.

# Claude model to use
model: claude-sonnet-4-6

# Default language hint (rust, go, python, etc.)
# lang: python

# Always attach system info to explanations
env: false

# Output style
brief: false
terse: false
no_color: false

# Security scanner settings
scan:
  # Severity threshold: only show findings at this level and above
  # severity: medium

  # Skip Claude explanations during scan (faster, offline)
  # no_explain: false

  # Include network device scanning
  # network: false

  # Auto-fix without prompting (use with caution)
  # auto_fix: false

# Redact secrets before sending to Claude
redact: true

# Ignored scanner check IDs (won't report these findings)
# ignore:
#   - diag-disk-low-space
#   - net-telnet-open

# Custom patterns (extend built-in offline matching)
# patterns:
#   - name: "MyApp — connection refused"
#     regex: "MyApp.*ConnectionRefused"
#     explanation: "The backend service is down. Run: systemctl restart myapp"
"""


def init_project(force: bool = False) -> None:
    target = Path.cwd() / ".errex.yml"
    if target.exists() and not force:
        output.console.print(f"[yellow].errex.yml already exists at {target}[/yellow]")
        output.console.print("Use --force to overwrite.")
        return

    target.write_text(TEMPLATE)
    output.console.print(f"[green]✓ Created {target}[/green]")
    output.console.print("[dim]Edit the file and commit it to share settings with your team.[/dim]")


def load_project_config() -> dict:
    target = Path.cwd() / ".errex.yml"
    if not target.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(target.read_text()) or {}
    except ImportError:
        import json
        output.err_console.print("[dim]PyYAML not installed; .errex.yml ignored[/dim]")
        return {}
    except Exception:
        return {}
