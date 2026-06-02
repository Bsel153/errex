from __future__ import annotations
import json
import urllib.request
import urllib.error
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from ._paths import HISTORY_FILE


def generate_digest(since_hours: int = 24) -> dict:
    """Read HISTORY_FILE and return a summary dict for the given time window."""
    empty: dict = {
        "window_hours": since_hours,
        "total": 0,
        "error_types": {},
        "models": {},
        "avg_rating": None,
        "rated_count": 0,
        "recent": [],
    }

    if not Path(HISTORY_FILE).exists():
        return empty

    now = datetime.now(timezone.utc)
    entries = []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_str = e.get("timestamp", "")
                if not ts_str:
                    continue
                try:
                    ts = datetime.fromisoformat(ts_str)
                    # Make timezone-aware if naive
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                diff = (now - ts).total_seconds() / 3600
                if diff <= since_hours:
                    entries.append(e)
    except OSError:
        return empty

    if not entries:
        return empty

    from .utils import extract_error_type

    error_types: Counter = Counter()
    models: Counter = Counter()
    ratings = []

    for e in entries:
        error_text = e.get("error", "")
        error_types[extract_error_type(error_text)] += 1
        model = e.get("model", "unknown")
        if model:
            models[model] += 1
        rating = e.get("rating")
        if rating is not None:
            try:
                ratings.append(float(rating))
            except (ValueError, TypeError):
                pass

    avg_rating = (sum(ratings) / len(ratings)) if ratings else None

    # Last 10 entries as recent list
    recent_entries = entries[-10:]
    recent = []
    for e in recent_entries:
        ts_str = e.get("timestamp", "")
        # Format timestamp nicely
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            ts_fmt = ts.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            ts_fmt = ts_str
        recent.append({
            "ts": ts_fmt,
            "type": extract_error_type(e.get("error", "")),
            "brief": e.get("brief", False),
        })

    return {
        "window_hours": since_hours,
        "total": len(entries),
        "error_types": dict(error_types.most_common(10)),
        "models": dict(models),
        "avg_rating": avg_rating,
        "rated_count": len(ratings),
        "recent": recent,
    }


def format_digest_text(digest: dict) -> str:
    """Return a human-readable ASCII summary of the digest."""
    hours = digest.get("window_hours", 24)
    total = digest.get("total", 0)
    avg_rating = digest.get("avg_rating")
    rated_count = digest.get("rated_count", 0)
    error_types = digest.get("error_types", {})
    recent = digest.get("recent", [])

    title = f"errex digest — last {hours}h"
    separator = "═" * len(title)

    lines = [
        title,
        separator,
        f"Total errors explained: {total}",
    ]

    if avg_rating is not None:
        lines.append(f"Avg rating: {avg_rating:.1f}/5 ({rated_count} rated)")
    elif rated_count == 0:
        lines.append("Avg rating: n/a (no ratings)")

    if error_types:
        lines.append("")
        lines.append("Top error types:")
        for etype, count in error_types.items():
            lines.append(f"  {count}x  {etype}")
    else:
        lines.append("")
        lines.append("Top error types: (none)")

    if recent:
        lines.append("")
        lines.append(f"Most recent (last {min(5, len(recent))}):")
        for entry in recent[-5:]:
            lines.append(f"  [{entry['ts']}] {entry['type']}")

    return "\n".join(lines)


def format_digest_slack(digest: dict) -> dict:
    """Return a Slack blocks JSON payload dict."""
    hours = digest.get("window_hours", 24)
    total = digest.get("total", 0)
    avg_rating = digest.get("avg_rating")
    rated_count = digest.get("rated_count", 0)
    error_types = digest.get("error_types", {})

    header_text = f":bar_chart: errex digest — last {hours}h"

    # Build mrkdwn section text
    parts = [f"*Total errors explained:* {total}"]
    if avg_rating is not None:
        parts.append(f"*Avg rating:* {avg_rating:.1f}/5 ({rated_count} rated)")

    if error_types:
        parts.append("\n*Top error types:*")
        for etype, count in list(error_types.items())[:5]:
            parts.append(f"  {count}x  `{etype}`")

    section_text = "\n".join(parts)

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": header_text,
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": section_text,
            },
        },
    ]

    return {"blocks": blocks}


def send_digest(webhook_url: str, digest: dict) -> bool:
    """POST the Slack digest payload to webhook_url. Returns True on 2xx, False on error."""
    payload = format_digest_slack(digest)
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "errex"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
        return 200 <= status < 300
    except (urllib.error.URLError, OSError):
        return False
