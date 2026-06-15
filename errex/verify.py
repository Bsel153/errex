"""Fix verification — re-run a command or scan after a fix to confirm resolution."""
from __future__ import annotations
import subprocess
import shlex
from typing import Callable


def verify_fix(
    command: str,
    original_error: str = "",
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """
    Re-run `command` and check if the original error still appears.
    Returns: {success: bool, output: str, same_error: bool, exit_code: int}
    """
    if progress_cb:
        progress_cb(f"Re-running: {command}")
    try:
        result = subprocess.run(
            shlex.split(command),
            capture_output=True, text=True, timeout=60,
        )
        combined = result.stdout + result.stderr
        snippet = original_error.strip()[:80].lower()
        same_error = (snippet in combined.lower()) if snippet else (result.returncode != 0)
        return {"success": result.returncode == 0, "output": combined,
                "same_error": same_error, "exit_code": result.returncode}
    except FileNotFoundError:
        cmd0 = shlex.split(command)[0] if command.strip() else command
        return {"success": False, "output": f"Command not found: {cmd0}",
                "same_error": True, "exit_code": -1}
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "Command timed out after 60s.",
                "same_error": True, "exit_code": -1}
    except Exception as e:
        return {"success": False, "output": str(e), "same_error": True, "exit_code": -1}


def show_verify_result(result: dict, console) -> None:
    """Print a human-readable verification summary."""
    if result["success"] and not result["same_error"]:
        console.print("\n[green]✓ Fix verified — command exits 0 and the original error is gone.[/green]\n")
    elif result["success"] and result["same_error"]:
        console.print("\n[yellow]⚠ Command exits 0 but the original error text still appears in output.[/yellow]\n")
    elif not result["success"] and not result["same_error"]:
        console.print("\n[yellow]⚠ Command still fails, but with a different error — partial progress.[/yellow]\n")
        if result["output"].strip():
            console.print(f"[dim]{result['output'][:400]}[/dim]\n")
    else:
        console.print("\n[red]✗ Fix did not resolve the error.[/red]\n")
        if result["output"].strip():
            console.print(f"[dim]{result['output'][:400]}[/dim]\n")
