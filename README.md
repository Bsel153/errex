# errex — Error Explainer

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
pip install git+https://github.com/Bsel153/errex.git
export ANTHROPIC_API_KEY=sk-...
```

Requires Python 3.8+ and an [Anthropic API key](https://console.anthropic.com/).

## Usage

```bash
# Interactive — paste your error, then Ctrl+D (Mac/Linux) or Ctrl+Z+Enter (Windows)
errex

# Read from a file
errex traceback.txt

# Pipe from another command
cat error.log | errex
errex < error.log
```

## What you get

For any error, errex explains:

1. **What kind of error it is** and which language or tool produced it
2. **What it means** in plain English
3. **The most likely root cause**, ranked by probability
4. **Numbered fix steps** with code snippets where helpful
5. **Common gotchas** — the non-obvious things that trip people up
