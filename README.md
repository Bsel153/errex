# errex — Error Explainer

[![CI](https://github.com/Bsel153/errex/actions/workflows/ci.yml/badge.svg)](https://github.com/Bsel153/errex/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/errex)](https://pypi.org/project/errex/)
[![Python versions](https://img.shields.io/pypi/pyversions/errex)](https://pypi.org/project/errex/)

Paste or pipe any error message and get a clear, plain-English explanation powered by Claude.

```
$ cat traceback.txt | errex.py

────────────────────────────────────────────────────
  errex — Error Analysis
────────────────────────────────────────────────────

**TypeError: unsupported operand type(s) for +: 'int' and 'str'**

This is a Python type error...
```

## Install

```bash
pip install errex
export ANTHROPIC_API_KEY=sk-...
```

Requires Python 3.9+ and an [Anthropic API key](https://console.anthropic.com/).

## Usage

```bash
# Interactive — paste your error, then Ctrl+D (Mac/Linux) or Ctrl+Z+Enter (Windows)
errex

# Read from a file
errex traceback.txt

# Pipe from another command
cat error.log | errex

# Watch a log file and auto-explain errors as they appear
errex --watch server.log

# Get just the fix command, no explanation
errex --fix traceback.txt

# One-paragraph summary instead of full analysis
errex --brief traceback.txt

# Hint the language when the error is ambiguous
errex --lang rust traceback.txt

# Copy the explanation to the clipboard
errex --copy traceback.txt

# Structured JSON output (error_type, root_cause, fix_steps, gotchas)
errex --json traceback.txt

# Use a different Claude model
errex --model claude-opus-4-7 traceback.txt

# View past explanations
errex --history
errex --history "KeyError"
```

## Web UI

```bash
errex --web
# → opens http://localhost:7337
```

Paste your error in the browser, pick a model, hit **Explain** (or ⌘Enter). No extra dependencies.

## Shell integration

Run `errex --install-shell` to add an `errex-last` function to your shell config.
After any failed command, just run `errex-last` to explain why it failed.

## Config file

Create `~/.errexrc` to set your defaults (all fields optional):

```json
{
  "model": "claude-opus-4-7",
  "brief": false,
  "lang": "python"
}
```

CLI flags always override the config file.

Past explanations are saved to `~/.errex_history` (one JSON object per line).

## What you get

For any error, errex explains:

1. **What kind of error it is** and which language or tool produced it
2. **What it means** in plain English
3. **The most likely root cause**, ranked by probability
4. **Numbered fix steps** with code snippets where helpful
5. **Common gotchas** — the non-obvious things that trip people up
