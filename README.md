# errex — Error Explainer

[![CI](https://github.com/Bsel153/errex/actions/workflows/ci.yml/badge.svg)](https://github.com/Bsel153/errex/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/errex)](https://pypi.org/project/errex/)
[![Python versions](https://img.shields.io/pypi/pyversions/errex)](https://pypi.org/project/errex/)

Paste or pipe any error message and get a clear, plain-English explanation powered by Claude.

```
$ cat traceback.txt | errex

────────────────────── errex — Error Analysis ──────────────────────

**TypeError: unsupported operand type(s) for +: 'int' and 'str'**

This is a Python type error. You're trying to add an integer and a
string together, which Python doesn't allow...
```

## Install

```bash
pip install errex
export ANTHROPIC_API_KEY=sk-ant-...
```

Requires Python 3.9+ and an [Anthropic API key](https://console.anthropic.com/).

## Quick start

```bash
errex                        # interactive paste
errex traceback.txt          # read from a file
cat error.log | errex        # pipe from stdin
errex --watch server.log     # tail a log, auto-explain errors
```

## All flags

### Explaining errors

| Flag | What it does |
|------|-------------|
| `errex [FILE]` | Explain an error from a file, stdin, or interactive paste |
| `--brief` | One-paragraph summary instead of full analysis |
| `--fix` | Output only the fix command, no explanation |
| `--lang LANG` | Language hint when the error is ambiguous (e.g. `rust`, `go`, `java`) |
| `--model MODEL` | Choose which Claude model to use (default: `claude-sonnet-4-6`) |
| `--json` | Structured JSON output: `error_type`, `root_cause`, `fix_steps`, `gotchas` |
| `--context FILE` | Attach a source file as extra context for more targeted explanations |
| `errex A.txt B.txt` | Compare two error files and find shared root causes |

### Code tools

| Flag | What it does |
|------|-------------|
| `--explain-code FILE` | Walk through what a piece of code does in plain English |
| `--lint FILE` | Scan a code file for bugs, security issues, and anti-patterns |
| `--test-gen FILE` | Generate a test case for a code file; pipe an error to reproduce the bug |
| `--explain-diff [FILE]` | Explain a git diff — pipe `git diff \| errex --explain-diff` or pass a `.patch` file |

### History & search

| Flag | What it does |
|------|-------------|
| `--history [SEARCH]` | View past explanations, optionally filtered by keyword |
| `--recent [N]` | Show the last N explanations (default: 5) |
| `--similar` | Find past errors in your history that match the current one |
| `--ask "question"` | Ask a follow-up about the last error without re-explaining it |
| `--retry` | Re-explain the last error with different flags (e.g. `--retry --model claude-opus-4-7`) |
| `--stats` | Usage dashboard: total runs, models, top error types, busiest day/hour |
| `--export FILE` | Export history to a styled HTML or Markdown file (`--export-format html\|md`) |
| `--clear-history [DAYS]` | Delete all history, or only entries older than N days |

### Workflow

| Flag | What it does |
|------|-------------|
| `--watch LOGFILE` | Tail a log file and auto-explain new errors (deduplicates repeats) |
| `--summarize-log FILE` | Digest all distinct error types in a large log file |
| `--issues` | Search GitHub Issues for bugs matching your error |
| `--share` | Post the explanation to paste.rs and print a shareable link |
| `--copy` | Copy the explanation to the clipboard |
| `--chat` | Stay in a Q&A loop after the explanation |
| `--notify` | Send a desktop notification when the explanation is ready |

### Code tools

| Flag | What it does |
|------|-------------|
| `--explain-code FILE` | Walk through what a piece of code does in plain English |
| `--lint FILE` | Scan a code file for bugs, security issues, and anti-patterns |
| `--test-gen FILE` | Generate a test case for a code file; pipe an error to reproduce the bug |
| `--explain-diff [FILE]` | Explain a git diff — pipe `git diff \| errex --explain-diff` or pass a `.patch` file |
| `--grep PATTERN FILE` | Filter a log file by regex, then explain matching lines |

### Translation & output

| Flag | What it does |
|------|-------------|
| `--translate LANG` | Respond in a spoken language (`--translate Spanish`, `--translate Japanese`) |
| `--save-as NAME` | Tag this explanation with a name for quick retrieval |
| `--json` | Structured JSON output: `error_type`, `root_cause`, `fix_steps`, `gotchas` |
| `--fix` | Output only the fix command, no explanation |
| `--copy` | Copy the explanation to the clipboard |
| `--share` | Post the explanation to paste.rs and print a shareable link |
| `--tokens` | Show input/output token counts after each explanation |

### Setup & config

| Flag | What it does |
|------|-------------|
| `--config [key=value]` | View or edit `~/.errexrc` — e.g. `--config model=claude-opus-4-7` |
| `--setup` | First-run wizard: check API key, detect languages, write config, install shell integration |
| `--doctor` | Health check: verify API key, connectivity, config, and version |
| `--completion bash\|zsh` | Print a shell completion script (`source <(errex --completion zsh)`) |
| `--scan` | Scan common log locations for recent error files and pick one to explain |
| `--install-shell` | Add `errex-last()` to your shell — run it after any failed command |
| `--web` | Launch a local web UI at `http://localhost:7337` |
| `--update` | Check PyPI for a newer version |
| `--version` | Show the installed version |

## Config file

`~/.errexrc` sets your defaults (all fields optional):

```json
{
  "model": "claude-opus-4-7",
  "brief": false,
  "lang": "python",
  "copy": false
}
```

Or manage it from the CLI:
```bash
errex --config                        # show all settings
errex --config model=claude-opus-4-7  # set a value
errex --config lang=null              # reset to default
```

## Shell integration

```bash
errex --install-shell   # adds errex-last() to ~/.zshrc or ~/.bashrc
```

After any failed command, run `errex-last` to explain why it failed.

## History

Every explanation is saved to `~/.errex_history` (one JSON object per line).

```bash
errex --recent           # last 5 explanations
errex --history KeyError # search history
errex --stats            # usage dashboard
errex --export report.html  # export to HTML
```

## What you get

For any error, errex explains:

1. **What kind of error it is** and which language or tool produced it
2. **What it means** in plain English
3. **The most likely root cause**, ranked by probability
4. **Numbered fix steps** with code snippets where helpful
5. **Common gotchas** — the non-obvious things that trip people up
