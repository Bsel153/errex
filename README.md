# errex — Error Explainer

[![CI](https://github.com/Bsel153/errex/actions/workflows/ci.yml/badge.svg)](https://github.com/Bsel153/errex/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/errex)](https://pypi.org/project/errex/)
[![Python versions](https://img.shields.io/pypi/pyversions/errex)](https://pypi.org/project/errex/)

Paste or pipe any error message and get a clear, plain-English explanation powered by Claude — often without touching the API at all.

```
$ cat traceback.txt | errex

────────────────────── errex — Error Analysis ──────────────────────

⚡ matched local pattern

**TypeError: unsupported operand type(s) for +: 'int' and 'str'**

This is a Python type error. You're trying to add an integer and a
string together, which Python doesn't allow...
```

## Install

```bash
pip install errex
export ANTHROPIC_API_KEY=sk-ant-...
```

Requires Python 3.9+. An [Anthropic API key](https://console.anthropic.com/) is needed for full explanations; local lookup commands work without one.

## Quick start

```bash
errex                        # interactive paste
errex traceback.txt          # read from a file
cat error.log | errex        # pipe from stdin
errex --watch server.log     # tail a log, auto-explain errors
```

## How it works

errex resolves every query through a three-tier speed hierarchy, from fastest to slowest:

1. **⚡ Instant (local patterns)** — 71 built-in patterns covering Python, JavaScript/Node.js, Rust, Java, Go, Docker, shell, Git, network, pip/npm. Matches happen in microseconds; no API call is made and no key is required. The response badge reads `⚡ matched local pattern`.

2. **📦 Fast (response cache)** — When Claude has already answered the same error, the cached response is returned instantly from `~/.errex_response_cache.json` (30-day TTL). The response badge reads `📦 cached response`.

3. **🤖 Full (Claude)** — For anything new or complex, errex calls the Claude API and stores the result in the cache. Use `--no-cache` to skip tiers 1 and 2 and always call Claude directly.

## Local lookup commands (no API key needed)

These commands return instant answers from built-in tables and never call Claude.

```bash
errex --explain-exit 139       # SIGSEGV — segmentation fault
errex --explain-http 429       # Too Many Requests — rate limited
errex --explain-cron "*/5 * * * *"  # "every 5 minutes"
errex --explain-env PYTHONPATH # what the variable controls
errex --list-patterns          # show all 71 built-in patterns in a table
```

## All flags

### Explaining errors

| Flag | What it does |
|------|-------------|
| `errex [FILE]` | Explain an error from a file, stdin, or interactive paste |
| `--brief` | One-paragraph summary instead of full analysis |
| `--fix` | Output only the fix command, no explanation |
| `--fix-apply` | Get a fix command from Claude and run it (prompts for confirmation) |
| `--yes` / `-y` | Auto-confirm `--fix-apply` without prompting |
| `--open-ticket` | Open a Red Hat Customer Portal support case with this error |
| `--rht-username USER` | Red Hat username (or set `RHT_USERNAME` env var) |
| `--rht-password PASS` | Red Hat password (or set `RHT_PASSWORD` env var) |
| `--rht-severity 1-4` | Ticket severity: 1=Urgent 2=High 3=Normal 4=Low (default: 3) |
| `--rht-product NAME` | Red Hat product name for the ticket |
| `--rht-version VER` | Product version for the ticket |
| `--lang LANG` | Language hint when the error is ambiguous (e.g. `rust`, `go`, `java`) |
| `--model MODEL` | Choose which Claude model to use (default: `claude-sonnet-4-6`) |
| `--json` | Structured JSON output: `error_type`, `root_cause`, `fix_steps`, `gotchas` |
| `--context FILE` | Attach a source file as extra context for more targeted explanations |
| `--top N` | Limit root cause to top N most likely causes |
| `--snippet` | Strip stdlib/library frames from a traceback before explaining |
| `--format-json` | Reformat JSON error before explaining |
| `errex A.txt B.txt` | Compare two error files and find shared root causes |

### Code tools

| Flag | What it does |
|------|-------------|
| `--explain-code FILE` | Walk through what a piece of code does in plain English |
| `--lint FILE` | Scan a code file for bugs, security issues, and anti-patterns |
| `--test-gen FILE` | Generate a test case for a code file; pipe an error to reproduce the bug |
| `--explain-diff [FILE]` | Explain a git diff — pipe `git diff \| errex --explain-diff` or pass a `.patch` file |
| `--explain-regex PATTERN` | Explain what a regex matches: breakdown, examples, gotchas |
| `--explain-sql QUERY` | Explain a SQL query: clause breakdown, performance notes, gotchas |
| `--explain-yaml FILE` | Explain a YAML config (auto-detects docker-compose, k8s, GitHub Actions) |
| `--explain-dockerfile FILE` | Explain a Dockerfile layer by layer |
| `--inline FILE LINE` | Explain a specific line of code in context |
| `--grep PATTERN FILE` | Filter a log file by regex, then explain matching lines |
| `--env` | Auto-attach system info (OS, Python, shell, runtimes) as context |
| `--run CMD` | Run a shell command and auto-explain any error output |
| `--redact` | Strip API keys, tokens, and passwords from error text before sending to Claude |

### Local lookups

| Flag | What it does |
|------|-------------|
| `--explain-exit CODE` | Explain a shell exit code (e.g. `139` → SIGSEGV / segfault) |
| `--explain-http CODE` | Explain an HTTP status code |
| `--explain-cron EXPR` | Explain a cron expression in plain English |
| `--explain-env VAR` | Explain what an environment variable controls |
| `--list-patterns` | Show all 71 built-in patterns in a table |

### History & search

| Flag | What it does |
|------|-------------|
| `--history [SEARCH]` | View past explanations, optionally filtered by keyword |
| `--recent [N]` | Show the last N explanations (default: 5) |
| `--since DATE` | Filter `--history`/`--recent` to entries on or after `YYYY-MM-DD` |
| `--similar` | Find past errors in your history that match the current one |
| `--search TERM` | Full-text search across all history fields |
| `--interactive` | Browse history with a numbered picker |
| `--dedup` | Show groups of near-duplicate errors in history |
| `--ask "question"` | Ask a follow-up about the last error without re-explaining it |
| `--retry` | Re-explain the last error with different flags (e.g. `--retry --model claude-opus-4-7`) |
| `--stats` | Usage dashboard: total runs, models, top error types, busiest day/hour |
| `--export FILE` | Export history to a styled HTML or Markdown file (`--export-format html\|md`) |
| `--export-csv FILE` | Export history to CSV (timestamp, model, error type, rating, name) |
| `--save-as NAME` | Tag this explanation with a name for quick retrieval |
| `--find-name NAME` | Retrieve a history entry saved with `--save-as` |
| `--list-named` | List all history entries saved with `--save-as` |
| `--add-note TEXT` | Append a note to the last history entry |
| `--pin` / `--unpin` | Mark the last history entry as pinned (protected from `--clear-history`) |
| `--filter TYPE` | Filter `--history`/`--recent` to entries matching an error type (e.g. `TypeError`) |
| `--clear-history [DAYS]` | Delete all history, or only entries older than N days (pinned entries kept) |
| `--rate SCORE` | Rate last explanation 1–5 |

### Cache & performance

| Flag | What it does |
|------|-------------|
| `--no-cache` | Skip the local pattern cache and response cache; always call Claude |
| `--clear-cache` | Wipe the response cache (`~/.errex_response_cache.json`) |
| `--tokens` | Show input/output token counts after each explanation |
| `--perf` | Show response time and tokens/second after each explanation |
| `--timeout N` | API request timeout in seconds (default: 30) |

### Workflow & integrations

| Flag | What it does |
|------|-------------|
| `--watch LOGFILE` | Tail a log file and auto-explain new errors (deduplicates repeats) |
| `--summarize-log FILE` | Digest all distinct error types in a large log file |
| `--bulk FILE` | Explain multiple errors from a file separated by blank lines |
| `--issues` | Search GitHub Issues for bugs matching your error |
| `--share` | Post the explanation to paste.rs and print a shareable link |
| `--copy` | Copy the explanation to the clipboard |
| `--chat` | Stay in a Q&A loop after the explanation |
| `--notify` | Send a desktop notification when the explanation is ready |
| `--webhook URL` | POST explanation to a Slack, Discord, or generic webhook URL |
| `--ci` | CI mode: no-color + terse output + GitHub Actions annotations + exits 1 |

### Output & formatting

| Flag | What it does |
|------|-------------|
| `--translate LANG` | Respond in a spoken language (`--translate Spanish`, `--translate Japanese`) |
| `--json` | Structured JSON output: `error_type`, `root_cause`, `fix_steps`, `gotchas` |
| `--terse` | Single-sentence diagnosis — shorter than `--brief`, great for scripting |
| `--output FILE` | Save the explanation to a file alongside printing |
| `--no-color` | Plain-text output with no rich formatting (safe to pipe) |
| `--word-wrap N` | Set output console width |
| `--copy` | Copy the explanation to the clipboard |
| `--share` | Post the explanation to paste.rs and print a shareable link |

### System health scan

errex can scan your machine for security issues, misconfigurations, and outdated software — no API key needed for the scan itself.

```bash
errex --scan                 # run a full system scan
errex --scan --scan-network  # include network device scan
errex --scan-status          # show last scan result and health streak
```

| Flag | What it does |
|------|-------------|
| `--scan` | Run a full system health scan (logs, configs, CVEs, malware) |
| `--scan-schedule FREQ` | Schedule automatic scans (`daily`, `weekly`, `monthly`) |
| `--scan-status` | Show last scan result and current health-streak days |
| `--scan-network` | Also scan local network devices |
| `--scan-severity LEVEL` | Only report findings at or above this severity (`low`, `medium`, `high`, `critical`) |
| `--scan-fix` | Auto-apply safe fixes for scan findings |
| `--scan-no-explain` | Skip Claude explanations; show findings only |
| `--scan-quiet` | Suppress all scan output (useful in scripts; check exit code) |
| `--scan-speak` | Read scan findings aloud via OS text-to-speech |
| `--scan-malware [PATH]` | Run a malware/hash scan on PATH (default: home directory) |
| `--check-hash FILE` | Check a file's SHA-256 hash against known-malware databases |
| `--vt-api-key KEY` | VirusTotal API key for extended hash lookups |
| `--simple` | Simplified, high-contrast output — fewer colours, larger text; good for accessibility |
| `--mascot` | Show Rex (errex's mascot) with a context-aware motivational line |

### Scan tickets

Scan findings are tracked as tickets so nothing gets lost between sessions.

| Flag | What it does |
|------|-------------|
| `--tickets` | List all open scan tickets |
| `--ticket-close ID` | Mark a ticket as resolved |
| `--ticket-snooze ID` | Snooze a ticket (default: 7 days; override with `--snooze-days N`) |
| `--snooze-days N` | Number of days to snooze (used with `--ticket-snooze`) |
| `--ticket-reopen ID` | Reopen a previously closed/snoozed ticket |
| `--ticket-note ID --note TEXT` | Append a note to a ticket |

### Network devices

errex remembers the devices on your local network and lets you give them friendly names.

| Flag | What it does |
|------|-------------|
| `--devices` | List all known network devices with their nicknames |
| `--device-rename IP --name NICK` | Set a friendly nickname for a device (e.g. `--device-rename 10.0.0.5 --name "Living Room TV"`) |

### Backup & restore

Before applying any auto-fix, errex backs up the affected files so you can always roll back.

```bash
errex --backups               # see all auto-fix backups
errex --restore-backup PATH   # restore a specific backup
errex --cloud-backup          # copy backups to a detected cloud-sync folder
errex --restore-point         # create an OS restore point before a big fix
```

| Flag | What it does |
|------|-------------|
| `--backups` | List all auto-fix backups (newest first) |
| `--restore-backup PATH` | Restore a file from its backup (PATH is the backup file path shown by `--backups`) |
| `--cloud-backup` | Copy the backup folder into a detected cloud-sync folder (Dropbox, Google Drive, OneDrive, iCloud) |
| `--restore-point` | Create an OS-level restore point before fixing: Time Machine snapshot (macOS), System Restore (Windows), or timeshift (Linux) |

### Weekly digest & notifications

| Flag | What it does |
|------|-------------|
| `--digest` | Print a summary of errors and fixes from the last 7 days |
| `--digest-since N` | Override the look-back window to the last N hours |
| `--discord-webhook URL` | Post the explanation or scan summary to a Discord channel |
| `--github-token TOKEN` | GitHub token for `--issues` lookups and PR annotations |
| `--github-repo OWNER/REPO` | GitHub repo to open issues against |

### Cloud sync

| Flag | What it does |
|------|-------------|
| `--sync-url URL` | Remote endpoint to sync scan summaries and ticket events |
| `--sync-key KEY` | API key for the sync endpoint (or set `ERREX_SYNC_KEY` env var) |

### Pro license

```bash
errex --activate ERREX-PRO-XXXXXX-XXXXXXXX   # activate a Pro license key
errex --license                               # show current license status
```

| Flag | What it does |
|------|-------------|
| `--activate KEY` | Activate an errex Pro license key |
| `--license` | Show current license status (free / Pro, expiry, seat) |

### Setup & config

| Flag | What it does |
|------|-------------|
| `--config [key=value]` | View or edit `~/.errexrc` — e.g. `--config model=claude-opus-4-7` |
| `--profile NAME` | Use a named config profile |
| `--list-profiles` | List all named profiles in `~/.errexrc` |
| `--delete-profile NAME` | Delete a named profile from `~/.errexrc` |
| `--setup` | First-run wizard: check API key, detect languages, write config, install shell integration |
| `--doctor` | Health check: verify API key, connectivity, config, and version |
| `--completion bash\|zsh` | Print a shell completion script (`source <(errex --completion zsh)`) |
| `--install-shell` | Add `errex-last()` to your shell — run it after any failed command |
| `--web` | Launch a local web UI at `http://localhost:7337` |
| `--update` | Check PyPI for a newer version |
| `--version` | Show the installed version |

## Web UI

```bash
errex --web   # opens http://localhost:7337
```

The web UI provides a browser-based interface with:

- **Real-time token streaming** — explanation text appears as Claude generates it
- **History sidebar** — past explanations listed on the left; click any entry to reload it
- **Source badge** — shows whether the result came from ⚡ a local pattern or 🤖 Claude
- **Full / Brief mode tabs** — toggle between detailed and summary views
- **Copy button** and `Cmd/Ctrl+Enter` keyboard shortcut

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

Named profiles let you keep separate configs for different projects:
```bash
errex --profile work                  # activate the "work" profile
errex --list-profiles                 # list all profiles
errex --delete-profile work           # remove a profile
```

## Shell integration

```bash
errex --install-shell   # adds errex-last() to ~/.zshrc or ~/.bashrc
```

After any failed command, run `errex-last` to explain why it failed.

## History

Every explanation is saved to `~/.errex_history` (one JSON object per line).

```bash
errex --recent              # last 5 explanations
errex --history KeyError    # search history
errex --search "import"     # full-text search across all fields
errex --interactive         # browse with a numbered picker
errex --dedup               # show groups of near-duplicate errors
errex --stats               # usage dashboard
errex --export report.html  # export to HTML
errex --rate 5              # rate the last explanation 1–5
```

## CI/CD integration

Use `--ci` for pipeline-friendly output:

```bash
cat build.log | errex --ci
```

`--ci` mode enables:
- No-color, terse output safe for log capture
- GitHub Actions [error annotations](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/workflow-commands-for-github-actions#setting-an-error-message) (`::error::`) printed to stdout
- Exit code 1 so the step fails visibly

Example GitHub Actions step:

```yaml
- name: Explain build failure
  if: failure()
  run: cat build.log | errex --ci
```

## Deployment

### Docker (quickstart)

```bash
docker run -e ANTHROPIC_API_KEY=sk-... -p 7337:7337 ghcr.io/bsel153/errex:latest
```

Or with `docker-compose`:

```bash
export ANTHROPIC_API_KEY=sk-...
docker-compose up -d
```

Open `http://localhost:7337` in your browser. All history, cache, and config are stored in the `errex-data` Docker volume.

**With authentication and TLS** (recommended for public-facing deployments):

```yaml
# docker-compose.yml
command: ["--auth", "admin:changeme", "--tls"]
```

### systemd (Linux server)

```bash
# 1. Create a dedicated user
sudo useradd -r -m -d /var/lib/errex errex

# 2. Install errex
sudo pip install errex

# 3. Install the service file
sudo cp deploy/errex.service /etc/systemd/system/errex.service

# 4. Set your API key
sudo systemctl edit errex
# Add under [Service]:
#   Environment=ANTHROPIC_API_KEY=sk-...

# 5. Enable and start
sudo systemctl daemon-reload
sudo systemctl enable --now errex

# 6. (Optional) Add nginx reverse proxy
sudo cp deploy/nginx.conf /etc/nginx/sites-available/errex
sudo ln -s /etc/nginx/sites-available/errex /etc/nginx/sites-enabled/
sudo certbot --nginx -d errex.yourdomain.com
sudo systemctl reload nginx
```

The service listens on `127.0.0.1:7337` by default and is proxied through nginx with HTTPS.

### LAN / mobile access

```bash
errex --web --host 0.0.0.0 --port 7337
```

Access from any device on your local network at `http://<your-ip>:7337`.

For temporary public internet access with a shareable link and QR code:

```bash
errex --web --tunnel
```

## What you get

For any error, errex explains:

1. **What kind of error it is** and which language or tool produced it
2. **What it means** in plain English
3. **The most likely root cause**, ranked by probability
4. **Numbered fix steps** with code snippets where helpful
5. **Common gotchas** — the non-obvious things that trip people up
