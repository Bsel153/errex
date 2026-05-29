import platform
import subprocess

from rich.console import Console
from rich.markdown import Markdown
from rich.rule import Rule
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns

console = Console()
err_console = Console(stderr=True)


def show_token_usage(input_tokens: int, output_tokens: int) -> None:
    total = input_tokens + output_tokens
    console.print(
        f"[dim]tokens: {input_tokens:,} in · {output_tokens:,} out · {total:,} total[/dim]"
    )


def show_perf(elapsed: float, output_tokens: int) -> None:
    tps = output_tokens / elapsed if elapsed > 0 else 0
    console.print(f"[dim]perf: {elapsed:.2f}s · {tps:.0f} tok/s[/dim]")


def copy_to_clipboard(text: str) -> None:
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["pbcopy"], input=text.encode(), check=True)
        elif system == "Linux":
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
        elif system == "Windows":
            subprocess.run(["clip"], input=text.encode(), check=True)
        err_console.print("[dim](copied to clipboard)[/dim]")
    except (subprocess.CalledProcessError, FileNotFoundError):
        err_console.print("[yellow]errex: could not copy to clipboard[/yellow]")
