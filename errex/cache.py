from __future__ import annotations
import hashlib
import json
import time
from pathlib import Path

CACHE_FILE = Path.home() / ".errex_response_cache.json"
CACHE_TTL_DAYS = 30

def _fingerprint(error_text: str, model: str, brief: bool, terse: bool) -> str:
    """SHA-1 of normalized inputs."""
    key = f"{error_text.strip().lower()}|{model}|{brief}|{terse}"
    return hashlib.sha1(key.encode()).hexdigest()

def get_cached(error_text: str, model: str, brief: bool, terse: bool) -> str | None:
    """Return cached response string, or None if missing/expired."""
    fp = _fingerprint(error_text, model, brief, terse)
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    entry = data.get(fp)
    if not entry:
        return None
    age_days = (time.time() - entry.get("ts", 0)) / 86400
    if age_days > CACHE_TTL_DAYS:
        return None
    return entry.get("response")

def save_cached(error_text: str, model: str, brief: bool, terse: bool, response: str) -> None:
    """Write a response to the cache."""
    fp = _fingerprint(error_text, model, brief, terse)
    data: dict = {}
    if CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data[fp] = {"response": response, "ts": time.time(), "model": model}
    # Keep cache from growing forever — evict entries older than TTL
    now = time.time()
    data = {k: v for k, v in data.items()
            if (now - v.get("ts", 0)) / 86400 <= CACHE_TTL_DAYS}
    data[fp] = {"response": response, "ts": time.time(), "model": model}
    CACHE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

def clear_cache() -> int:
    """Delete the cache file. Returns number of entries cleared."""
    if not CACHE_FILE.exists():
        return 0
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        count = len(data)
    except Exception:
        count = 0
    CACHE_FILE.unlink()
    return count

def cache_stats() -> dict:
    """Return basic cache stats."""
    if not CACHE_FILE.exists():
        return {"entries": 0, "size_kb": 0}
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        size_kb = CACHE_FILE.stat().st_size // 1024
        return {"entries": len(data), "size_kb": size_kb}
    except Exception:
        return {"entries": 0, "size_kb": 0}
