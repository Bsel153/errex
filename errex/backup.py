"""Auto-backup — copies files to a local backup dir before errex modifies them.

Pure local file copies (no network, no cloud). Lets a customer recover a file
if an auto-applied fix changes something they didn't expect.
"""
from __future__ import annotations

import datetime
import json
import shutil
from pathlib import Path

_BACKUP_ROOT = Path.home() / ".errex_backups"
_MANIFEST = _BACKUP_ROOT / "manifest.jsonl"


def _now_stamp() -> str:
    return datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")


def _record(entry: dict) -> None:
    _BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    with open(_MANIFEST, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def backup_files(paths: list[str], reason: str = "") -> list[dict]:
    """
    Copy each existing file in *paths* into a timestamped backup folder.

    Returns a list of records: {"original": ..., "backup": ..., "timestamp": ...}.
    Missing files and directories are skipped silently — backup is best-effort
    and must never block a fix from running.
    """
    records: list[dict] = []
    stamp = _now_stamp()
    dest_dir = _BACKUP_ROOT / stamp
    for raw in paths:
        src = Path(raw).expanduser()
        if not src.is_file():
            continue
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / src.name
            n = 1
            while dest.exists():
                dest = dest_dir / f"{src.stem}.{n}{src.suffix}"
                n += 1
            shutil.copy2(src, dest)
        except OSError:
            continue
        record = {
            "original": str(src),
            "backup": str(dest),
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "reason": reason,
        }
        _record(record)
        records.append(record)
    return records


def list_backups(limit: int = 20) -> list[dict]:
    """Return the most recent backup records, newest first."""
    if not _MANIFEST.exists():
        return []
    entries = []
    with open(_MANIFEST, encoding="utf-8") as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return list(reversed(entries))[:limit]


def restore_backup(backup_path: str) -> dict:
    """Copy a backed-up file back to its original location."""
    entries = []
    if _MANIFEST.exists():
        with open(_MANIFEST, encoding="utf-8") as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    match = next((e for e in entries if e["backup"] == backup_path), None)
    if not match:
        return {"error": f"No backup record found for '{backup_path}'."}

    src = Path(match["backup"])
    dest = Path(match["original"])
    if not src.is_file():
        return {"error": f"Backup file is missing: {src}"}
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    except OSError as e:
        return {"error": str(e)}
    return {"ok": True, "restored_to": str(dest)}
