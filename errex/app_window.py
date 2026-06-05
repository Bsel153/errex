"""Launch errex web UI in a native PyWebView window (standalone app mode)."""
from __future__ import annotations

import socket
import threading
import time


def launch(host: str = "127.0.0.1", port: int = 7337) -> None:
    """Start the HTTP server in a background thread, then open a native window."""
    try:
        import webview
    except ImportError:
        raise SystemExit(
            "pywebview is required for the standalone app.\n"
            "Install it with: pip install pywebview"
        )

    threading.Thread(target=_run_server, args=(host, port), daemon=True).start()
    _wait_for_server(host, port)

    webview.create_window(
        "errex",
        f"http://{host}:{port}",
        width=1200,
        height=800,
        resizable=True,
        min_size=(900, 600),
    )
    webview.start()


def _run_server(host: str, port: int) -> None:
    from .web_ui import serve
    serve(host=host, port=port)


def _wait_for_server(host: str, port: int, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
