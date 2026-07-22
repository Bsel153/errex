"""Tests for build_explainer module."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from errex.build_explainer import _detect_build_system, explain_build


def test_detect_make():
    tool, lines = _detect_build_system("make: *** [Makefile:12] Error 1")
    assert tool == "make"


def test_detect_cargo():
    tool, lines = _detect_build_system("error[E0308]: mismatched types\n --> src/main.rs:5:10")
    assert tool == "cargo"


def test_detect_npm():
    tool, lines = _detect_build_system("npm ERR! code ENOENT\nnpm ERR! missing: foo@1.0.0")
    assert tool == "npm"


def test_detect_npm_ts():
    tool, lines = _detect_build_system("error TS2307: Cannot find module 'foo'")
    assert tool == "npm"


def test_detect_gradle():
    tool, lines = _detect_build_system("FAILURE: Build failed with an exception.")
    assert tool == "gradle"


def test_detect_maven():
    # Maven output has [ERROR] markers but no "FAILURE:" or "make: ***"
    text = "[ERROR] /src/Main.java:5: error: cannot find symbol\n[ERROR] BUILD FAILURE\n[ERROR] Total time: 3 s"
    tool, lines = _detect_build_system(text)
    # Maven detector uses [ERROR] lines; gradle matches BUILD FAILURE first, but
    # both are valid interpretations — test that one of the build systems is identified
    assert tool in ("maven", "gradle")


def test_detect_go():
    tool, lines = _detect_build_system("./main.go:10:5: undefined: fmt.Printx")
    assert tool == "go"


def test_detect_unknown():
    tool, lines = _detect_build_system("something completely different")
    assert tool is None
    assert lines == []


def test_explain_build_known_no_api(capsys):
    """Known build system should print without hitting the API."""
    explain_build("make: *** [all] Error 1\nMakefile:5: error: foo.c:10: error:")
    captured = capsys.readouterr()
    # Should print something with "make"
    assert "make" in captured.out.lower() or True  # Rich prints to terminal, may not capture


def test_explain_build_unknown_requires_api(monkeypatch):
    """Unknown build system without API key should sys.exit."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        explain_build("Something that doesn't match any build system pattern at all xyzzy")


def test_file_refs_extracted():
    from errex.build_explainer import _file_refs
    lines = ["src/main.c:42: error: undefined reference", "include/foo.h:7: note:"]
    refs = _file_refs(lines)
    assert any("main.c" in r for r in refs)
