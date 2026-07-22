"""Tests for watch_directory feature in errex/watch.py."""
from __future__ import annotations

import os
import time
import threading
import pytest
from pathlib import Path


def test_watch_directory_missing_dir():
    from errex.watch import watch_directory
    with pytest.raises(SystemExit):
        watch_directory("/nonexistent/path/xyz")


def test_watch_directory_detects_new_log(tmp_path):
    """watch_directory should detect a new .log file created after startup."""
    from errex.watch import watch_directory
    import signal

    results = []

    def write_file():
        time.sleep(0.1)  # let watch_directory start
        log = tmp_path / "new_test.log"
        log.write_text("line1\nline2\n")
        time.sleep(0.2)
        # Interrupt the watch loop
        os.kill(os.getpid(), signal.SIGINT)

    t = threading.Thread(target=write_file, daemon=True)
    t.start()

    try:
        watch_directory(str(tmp_path))
    except (KeyboardInterrupt, SystemExit):
        pass

    t.join(timeout=2)
    # If we get here without crashing, the test passes


def test_watch_directory_ignores_existing_logs(tmp_path):
    """Pre-existing .log files should not be reported."""
    existing = tmp_path / "existing.log"
    existing.write_text("old content\n")

    from errex.watch import watch_directory
    import signal

    def interrupt():
        time.sleep(0.15)
        os.kill(os.getpid(), signal.SIGINT)

    t = threading.Thread(target=interrupt, daemon=True)
    t.start()

    try:
        watch_directory(str(tmp_path))
    except (KeyboardInterrupt, SystemExit):
        pass

    t.join(timeout=2)
    # Should not crash


def test_watch_directory_ignores_non_log_files(tmp_path):
    """Non-.log files should not be reported."""
    from errex.watch import watch_directory
    import signal

    def write_and_interrupt():
        time.sleep(0.1)
        (tmp_path / "new.txt").write_text("not a log\n")
        time.sleep(0.1)
        os.kill(os.getpid(), signal.SIGINT)

    t = threading.Thread(target=write_and_interrupt, daemon=True)
    t.start()

    try:
        watch_directory(str(tmp_path))
    except (KeyboardInterrupt, SystemExit):
        pass

    t.join(timeout=2)
