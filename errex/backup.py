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

# Local folders created by desktop sync clients — if one of these exists,
# the provider is already syncing it to the cloud; errex just needs to drop
# a copy inside. No OAuth, no API keys, no extra moving parts.
_CLOUD_SYNC_FOLDERS = {
    "Google Drive":  ("Google Drive", "GoogleDrive", "My Drive"),
    "iCloud Drive":  ("Library/Mobile Documents/com~apple~CloudDocs",),
    "Dropbox":       ("Dropbox",),
    "OneDrive":      ("OneDrive",),
}


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


def detect_cloud_sync_folders() -> list[dict]:
    """
    Find cloud-sync desktop-client folders already on this machine
    (Google Drive, iCloud Drive, Dropbox, OneDrive).

    Returns a list of {"provider": ..., "path": ...} for each folder found.
    Detection only — never copies anything until the customer opts in.
    """
    home = Path.home()
    found = []
    for provider, candidates in _CLOUD_SYNC_FOLDERS.items():
        for rel in candidates:
            path = home / rel
            if path.is_dir():
                found.append({"provider": provider, "path": str(path)})
                break
    return found


def sync_to_cloud_folder(provider_path: str) -> dict:
    """
    Copy the local backup folder into a detected cloud-sync folder
    (e.g. ~/Google Drive/errex_backups). The sync client takes it from there.
    """
    if not _BACKUP_ROOT.is_dir():
        return {"error": "No local backups to sync yet."}
    dest_root = Path(provider_path).expanduser()
    if not dest_root.is_dir():
        return {"error": f"Cloud sync folder not found: {dest_root}"}
    dest = dest_root / "errex_backups"
    try:
        for item in _BACKUP_ROOT.iterdir():
            if item.name == "manifest.jsonl":
                continue
            target = dest / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
    except OSError as e:
        return {"error": str(e)}
    return {"ok": True, "synced_to": str(dest)}


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
