"""Tests for Rex, errex's mascot."""
from __future__ import annotations

import random

from errex.mascot import say, FACE, _LINES


def test_say_includes_face():
    line = say("all_clear", rng=random.Random(0))
    assert FACE in line


def test_say_picks_from_context_bank():
    for ctx in ("welcome", "all_clear", "issues_found", "fix_applied"):
        line = say(ctx, rng=random.Random(1))
        text = line.split(FACE, 1)[1].strip()
        assert text in _LINES[ctx]


def test_say_unknown_context_falls_back():
    line = say("nonsense-context", rng=random.Random(2))
    text = line.split(FACE, 1)[1].strip()
    assert text in _LINES["issues_found"]


def test_say_is_deterministic_with_seeded_rng():
    a = say("welcome", rng=random.Random(42))
    b = say("welcome", rng=random.Random(42))
    assert a == b
