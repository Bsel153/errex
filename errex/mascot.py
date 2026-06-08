"""Rex — errex's friendly little mascot.

A tiny bit of personality dropped into scan results and the welcome flow.
No artwork required: a small face plus a rotating bank of one-liners,
chosen for the moment (all-clear, issues found, fix applied, welcome).
"""
from __future__ import annotations

import random

FACE = "(•‿•)"

_LINES: dict[str, tuple[str, ...]] = {
    "welcome": (
        "Hi, I'm Rex! I'll keep an eye on this machine from now on.",
        "Nice to meet you — let's see what's going on here.",
        "I'm Rex. Think of me as your machine's tiny security guard.",
    ),
    "all_clear": (
        "Nothing to see here — your machine looks great!",
        "Clean as a whistle. Whatever you're doing, keep doing it.",
        "All clear! I'll keep watching so you don't have to.",
    ),
    "issues_found": (
        "Found a few things worth a look — nothing we can't handle.",
        "Spotted some issues below. Let's get them sorted.",
        "A few things need your attention — details below.",
    ),
    "fix_applied": (
        "Fixed it! One less thing to worry about.",
        "Done — that issue's taken care of.",
        "Sorted! On to the next thing.",
    ),
}


def say(context: str, rng: "random.Random | None" = None) -> str:
    """Return a 'face + line' string for the given context (e.g. 'all_clear')."""
    lines = _LINES.get(context, _LINES["issues_found"])
    chooser = rng or random
    return f"{FACE}  {chooser.choice(lines)}"
