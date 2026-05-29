from __future__ import annotations

import json
import sys

from ._paths import HISTORY_FILE, CONFIG_FILE
from . import output, _constants


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return {**_constants.CONFIG_DEFAULTS, **json.load(f)}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_constants.CONFIG_DEFAULTS)


def manage_config(assignment: str | None) -> None:
    """View or set a config value in ~/.errexrc."""
    file_config: dict = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                file_config = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    if assignment is None:
        output.console.rule("[bold cyan]errex — Config[/bold cyan]")
        output.console.print(f"[dim]{CONFIG_FILE}[/dim]\n")
        from rich.table import Table
        table = Table(show_header=True, header_style="bold magenta", box=None, show_edge=False)
        table.add_column("Key", style="cyan", min_width=8)
        table.add_column("Value", min_width=20)
        table.add_column("Source", style="dim")
        for key, default in _constants.CONFIG_DEFAULTS.items():
            if key in file_config:
                table.add_row(key, str(file_config[key]), "~/.errexrc")
            else:
                table.add_row(key, str(default), "default")
        output.console.print(table)
        output.console.print(f"\n[dim]Set a value:   errex --config model=claude-opus-4-7[/dim]")
        output.console.print(f"[dim]Clear a value: errex --config lang=null[/dim]")
        return

    if "=" not in assignment:
        output.err_console.print(f"[red]errex: expected key=value, got: {assignment!r}[/red]")
        output.err_console.print(f"[dim]Valid keys: {', '.join(_constants.CONFIG_DEFAULTS)}[/dim]")
        sys.exit(1)

    key, _, raw = assignment.partition("=")
    key, raw = key.strip(), raw.strip()

    if key not in _constants.CONFIG_TYPES:
        output.err_console.print(f"[red]errex: unknown config key '{key}'[/red]")
        output.err_console.print(f"[dim]Valid keys: {', '.join(_constants.CONFIG_DEFAULTS)}[/dim]")
        sys.exit(1)

    if raw.lower() == "null":
        file_config.pop(key, None)
        with open(CONFIG_FILE, "w") as f:
            json.dump(file_config, f, indent=2)
        output.console.print(f"[green]Cleared[/green] [cyan]{key}[/cyan]  [dim](reset to default: {_constants.CONFIG_DEFAULTS[key]})[/dim]")
        return

    if _constants.CONFIG_TYPES[key] is bool:
        if raw.lower() in ("true", "1", "yes"):
            value: bool | str = True
        elif raw.lower() in ("false", "0", "no"):
            value = False
        else:
            output.err_console.print(f"[red]errex: '{key}' expects true/false, got: {raw!r}[/red]")
            sys.exit(1)
    else:
        value = raw

    file_config[key] = value
    with open(CONFIG_FILE, "w") as f:
        json.dump(file_config, f, indent=2)
    output.console.print(f"[green]Set[/green] [cyan]{key}[/cyan] = [bold]{value}[/bold]  [dim]({CONFIG_FILE})[/dim]")


def load_profile(name: str, file_config: dict) -> dict:
    """Return config merged with the named profile from ~/.errexrc profiles dict."""
    profiles = file_config.get("profiles", {})
    if name not in profiles:
        output.err_console.print(f"[red]errex: profile '{name}' not found.[/red]")
        available = list(profiles.keys())
        if available:
            output.err_console.print(f"[dim]Available profiles: {', '.join(available)}[/dim]")
        else:
            output.err_console.print("[dim]No profiles saved yet. Create one by adding a \"profiles\" key to ~/.errexrc[/dim]")
        sys.exit(1)
    return {**_constants.CONFIG_DEFAULTS, **file_config, **profiles[name]}


def list_profiles() -> None:
    """List all named profiles saved in ~/.errexrc."""
    if not CONFIG_FILE.exists():
        output.console.print(f"[yellow]No config file at {CONFIG_FILE}. Run [cyan]errex --setup[/cyan] to create one.[/yellow]")
        sys.exit(0)
    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        output.err_console.print(f"[red]errex: could not read config: {e}[/red]")
        sys.exit(1)

    profiles = data.get("profiles", {})
    if not profiles:
        output.console.print("[yellow]No profiles saved yet.[/yellow]")
        output.console.print('[dim]Add a "profiles" key to ~/.errexrc:[/dim]')
        output.console.print('[dim]  {"profiles": {"go": {"lang": "go", "model": "claude-opus-4-7"}}}[/dim]')
        return

    output.console.rule("[bold cyan]errex — Profiles[/bold cyan]")
    output.console.print(f"[dim]{CONFIG_FILE}[/dim]\n")
    from rich.table import Table
    table = Table(show_header=True, header_style="bold magenta", box=None, show_edge=False)
    table.add_column("Profile", style="cyan", min_width=12)
    table.add_column("Settings")
    for name, settings in profiles.items():
        parts = "  ".join(f"{k}={v}" for k, v in settings.items())
        table.add_row(name, parts)
    output.console.print(table)
    output.console.print(f"\n[dim]Use with: errex --profile NAME[/dim]")


def delete_profile(name: str) -> None:
    """Delete a named profile from ~/.errexrc."""
    if not CONFIG_FILE.exists():
        output.err_console.print(f"[red]errex: no config file at {CONFIG_FILE}[/red]")
        sys.exit(1)

    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        output.err_console.print(f"[red]errex: could not read config: {e}[/red]")
        sys.exit(1)

    profiles = data.get("profiles", {})
    if name not in profiles:
        output.err_console.print(f"[red]errex: profile '{name}' not found.[/red]")
        available = list(profiles.keys())
        if available:
            output.err_console.print(f"[dim]Available profiles: {', '.join(available)}[/dim]")
        else:
            output.err_console.print("[dim]No profiles saved.[/dim]")
        sys.exit(1)

    del profiles[name]
    if profiles:
        data["profiles"] = profiles
    else:
        data.pop("profiles", None)

    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)

    output.console.print(f"[green]Deleted profile[/green] [cyan]{name}[/cyan]  [dim]({CONFIG_FILE})[/dim]")
