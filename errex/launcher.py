"""Create OS desktop shortcuts that launch the errex web UI."""
from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
from pathlib import Path

_APP_NAME = "errex"
_APP_DESC = "Error explainer & security scanner"


def _python() -> str:
    return sys.executable


def _errex_cmd() -> str:
    """Return the path to the errex entry-point script, falling back to -m errex."""
    ep = shutil.which("errex")
    if ep:
        return ep
    return f"{_python()} -m errex"


def create_shortcut() -> Path:
    """Create a desktop shortcut appropriate for the current OS. Returns the path created."""
    system = platform.system()
    if system == "Darwin":
        return _create_macos_app()
    if system == "Windows":
        return _create_windows_shortcut()
    return _create_linux_desktop()


# ── macOS — .app bundle ───────────────────────────────────────────────────────

_MACOS_SCRIPT = """\
#!/usr/bin/env bash
export PATH="{py_dir}:$PATH"
# Load shell env so ANTHROPIC_API_KEY etc. are available
[ -f "$HOME/.zshrc" ] && source "$HOME/.zshrc" 2>/dev/null
[ -f "$HOME/.bashrc" ] && source "$HOME/.bashrc" 2>/dev/null
{errex} --web &
sleep 1
open http://localhost:8787
wait
"""

_MACOS_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>errex</string>
  <key>CFBundleDisplayName</key><string>errex</string>
  <key>CFBundleIdentifier</key><string>com.errex.app</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleExecutable</key><string>errex-launcher</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
</dict>
</plist>
"""


def _create_macos_app() -> Path:
    desktop = Path.home() / "Desktop"
    app_path = desktop / "errex.app"
    macos_dir = app_path / "Contents" / "MacOS"
    res_dir = app_path / "Contents" / "Resources"
    macos_dir.mkdir(parents=True, exist_ok=True)
    res_dir.mkdir(parents=True, exist_ok=True)

    (app_path / "Contents" / "Info.plist").write_text(_MACOS_PLIST)

    launcher = macos_dir / "errex-launcher"
    py_dir = str(Path(_python()).parent)
    errex_bin = shutil.which("errex") or f"{_python()} -m errex"
    launcher.write_text(_MACOS_SCRIPT.format(py_dir=py_dir, errex=errex_bin))
    launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    return app_path


# ── Windows — .bat launcher + Start Menu shortcut ─────────────────────────────

_WIN_LAUNCHER = """\
@echo off
start "" "{errex}" --web
timeout /t 2 /nobreak >nul
start http://localhost:8787
"""


def _create_windows_shortcut() -> Path:
    desktop = Path.home() / "Desktop"
    bat = desktop / "errex.bat"
    errex_bin = shutil.which("errex") or f"{_python()} -m errex"
    bat.write_text(_WIN_LAUNCHER.format(errex=errex_bin))

    # Also try to create a proper .lnk via PowerShell
    lnk = desktop / "errex.lnk"
    try:
        ps = (
            f'$ws = New-Object -ComObject WScript.Shell; '
            f'$s = $ws.CreateShortcut("{lnk}"); '
            f'$s.TargetPath = "{bat}"; '
            f'$s.Description = "{_APP_DESC}"; '
            f'$s.Save()'
        )
        subprocess.run(["powershell", "-Command", ps],
                       capture_output=True, timeout=10)
        if lnk.exists():
            bat.unlink(missing_ok=True)
            return lnk
    except Exception:
        pass

    return bat


# ── Linux — .desktop file ─────────────────────────────────────────────────────

_LINUX_LAUNCHER = """\
#!/usr/bin/env bash
# Load user env
[ -f "$HOME/.bashrc" ] && source "$HOME/.bashrc" 2>/dev/null
[ -f "$HOME/.profile" ] && source "$HOME/.profile" 2>/dev/null
{errex} --web &
sleep 1
xdg-open http://localhost:8787 2>/dev/null || \\
  python3 -c "import webbrowser; webbrowser.open('http://localhost:8787')"
wait
"""

_LINUX_DESKTOP = """\
[Desktop Entry]
Version=1.0
Type=Application
Name=errex
Comment={desc}
Exec={launcher}
Icon={icon}
Terminal=false
Categories=Utility;Development;
StartupNotify=true
"""


def _create_linux_desktop() -> Path:
    desktop = Path.home() / "Desktop"
    desktop.mkdir(exist_ok=True)

    # Write launcher script
    scripts_dir = Path.home() / ".local" / "bin"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    launcher_path = scripts_dir / "errex-launcher.sh"
    errex_bin = shutil.which("errex") or f"{_python()} -m errex"
    launcher_path.write_text(_LINUX_LAUNCHER.format(errex=errex_bin))
    launcher_path.chmod(launcher_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP)

    # Write .desktop file on Desktop and in applications dir
    icon_path = _find_icon()
    desktop_entry = _LINUX_DESKTOP.format(
        desc=_APP_DESC,
        launcher=str(launcher_path),
        icon=icon_path or "utilities-terminal",
    )
    desktop_file = desktop / "errex.desktop"
    desktop_file.write_text(desktop_entry)
    desktop_file.chmod(desktop_file.stat().st_mode | stat.S_IEXEC)

    # Also install to ~/.local/share/applications for app menu
    apps_dir = Path.home() / ".local" / "share" / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    (apps_dir / "errex.desktop").write_text(desktop_entry)

    return desktop_file


def _find_icon() -> str | None:
    """Return path to errex icon if bundled, else None."""
    candidates = [
        Path(__file__).parent / "assets" / "errex.png",
        Path(__file__).parent / "assets" / "icon.png",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def run_create_shortcut() -> None:
    """CLI entry point for --create-shortcut."""
    from rich.console import Console
    console = Console()
    try:
        path = create_shortcut()
        console.print(f"\n[green]✓[/green] Desktop shortcut created: [bold]{path}[/bold]")
        console.print(
            "\n  Double-click it to open errex in your browser.\n"
            "  Or run [cyan]errex --web[/cyan] anytime from the terminal.\n"
        )
    except Exception as e:
        console.print(f"\n[red]✗[/red] Could not create shortcut: {e}")
        console.print("  You can still run errex with: [cyan]errex --web[/cyan]\n")
        raise SystemExit(1)
