# Changelog

All notable changes to errex are documented here.

## [0.23.0] — 2026-06-15
### Added
- `--backups`: list auto-fix backups (newest first); files are snapshotted to `~/.errex_backups/` before any fix is applied
- `--restore-backup PATH`: restore a file from a backup created by auto-fix
- `--cloud-backup`: copy the backup folder into a detected cloud-sync folder (Dropbox, Google Drive, OneDrive, iCloud)
- `--restore-point`: create a Time Machine snapshot (macOS), System Restore point (Windows), or timeshift snapshot (Linux) before a large fix
- `--mascot`: print Rex `(•‿•)` with a context-aware motivational line; shown automatically after scans
- `--scan-speak`: read scan findings aloud via `say` (macOS), `spd-say`/`espeak` (Linux), or PowerShell (Windows)
- `--simple`: simplified high-contrast output — fewer colours, no Unicode decoration; good for accessibility
- `--devices`: list known local network devices with friendly nicknames
- `--device-rename IP --name NICK`: assign a human-readable name to a network device
- `--sync-url` / `--sync-key`: opt-in cloud sync of scan summaries and ticket events
- Health streaks: `--scan-status` now reports consecutive clean days
- Anniversary alerts: congratulatory findings at 30 / 90 / 180 / 365 days of use
- Welcome scan: `--setup` triggers a brief health scan on first run
- Fix confidence scores and desktop notifications when auto-fix is applied
- Predictive alerts for disk fill rate and error frequency trends
- Duplicate file and stale browser cache detection in the scanner
- Unauthorized device alerts for new devices seen on the network
- Large-text / dark mode toggles in the web dashboard

### Fixed
- `notify()` now escapes `"` and `\` before osascript interpolation (command injection fix)
- CI action now installs from local source (`pip install .`) instead of stale PyPI package
- 8 correctness bugs across backup, cloud sync, restore points, and mascot modules

## [0.22.0] — 2026-06
### Added
- `--tickets`: list open scan tickets; `--ticket-close`, `--ticket-snooze`, `--ticket-reopen`, `--ticket-note` manage lifecycle
- `--discord-webhook URL`: post scan summaries and explanations to a Discord channel
- `--github-token` / `--github-repo`: push tickets to GitHub Issues
- `--scan-malware [PATH]`: layered malware detection — heuristics + ClamAV + VirusTotal hash lookup
- `--check-hash FILE` / `--vt-api-key KEY`: check a file's SHA-256 against VirusTotal
- `--email-report EMAIL`: HTML health digest sent via SMTP; `--smtp-host`, `--smtp-port`, `--email-period`
- `--scan-schedule daily|weekly|monthly`: register background scans
- `--mcp`: stdio JSON-RPC server for Claude Desktop integration
- GitHub Actions composite action (`.github/actions/explain/`) for CI pipeline integration
- VS Code extension (`extensions/vscode/`) with `explainSelection` and `explainFromClipboard` commands
- 20 new error patterns: Rust, Go, Docker, pip, npm, shell, database (109 patterns total)
- Linux security scanner: firewall, SSH config, world-writable files, fail2ban, sudo rules
- One-command installer script and desktop shortcut creation

### Fixed
- 10 correctness, security, and reliability bugs from code review
- 3 ticket/Discord/GitHub integration bugs

## [0.21.0] — 2026-05
### Added
- macOS, Windows, and IoT security scanner; web UI Scan tab
- Docker image, systemd service file, nginx config; `--port` flag
- `--tls` / `--cert` / `--key`: HTTPS with self-signed or custom certificates
- `--privacy`: full disclosure of what errex reads and stores
- `--show-access`: lists files and env vars errex can access
- `--tunnel`: Cloudflare tunnel for temporary public access with a QR code
- `--auth USER:PASS`: HTTP Basic Auth for the web UI
- `--host ADDR`: bind the web server to a specific address
- Stats tab in the web dashboard (`/stats` endpoint)
- `--digest` / `--digest-since` / `--digest-webhook`: weekly error digest with webhook delivery
- `--open-ticket`, `--rht-username`, `--rht-password`, `--rht-severity`, `--rht-product`, `--rht-version`: Red Hat Customer Portal ticket creation

## [0.20.0] — 2026-04
### Added
- Expanded `--doctor` health dashboard: API key, connectivity, config, history, version, system checks
- Enhanced `--fix-apply` for code files: shows diff before applying; `--yes` / `-y` to auto-confirm

## [0.19.0] — 2026-03
### Added
- Response cache (`~/.errex_response_cache.json`, 30-day TTL); `--no-cache` to bypass; `--clear-cache` to wipe
- `--fix-apply`: get a fix command from Claude and run it after confirmation
- 65+ offline patterns built in; `--list-patterns` shows them in a table
- Overhauled web UI: streaming tokens, history sidebar, source badge (⚡ / 📦 / 🤖), Full/Brief tabs
- 48-test integration suite invoking `python -m errex` as a real subprocess
- `errex.py` + `web.py` refactored into `errex/` package with 15+ modules
- Auto-publish to PyPI on `v*` tag push; `workflow_dispatch` trigger for manual releases

## [0.18.0] — 2026-05-28
### Added
- `--redact`: auto-strip API keys, tokens, and passwords from error text before sending to Claude (Anthropic, GitHub, AWS, JWT, Bearer, password/secret/token fields)
- `--explain-yaml FILE`: explain a YAML config file in plain English; auto-detects Docker Compose, Kubernetes manifests, and GitHub Actions workflows
- `--filter TYPE`: narrow `--history` and `--recent` to entries matching an error type keyword (e.g. `--recent --filter TypeError`)
- `--export-csv FILE`: export history to CSV with columns timestamp, model, error_type, error, explanation_length, rating, name, pinned
- `--perf`: show response time and tokens/second after every explanation; works with all explain commands

## [0.17.0] — 2026-05-28
### Added
- `--explain-sql QUERY`: explain what a SQL query does in plain English with a clause-by-clause breakdown, performance notes, and gotchas
- `--list-named`: list all history entries saved with `--save-as` in a table (name, date, model, error snippet)
- `--run CMD`: run any shell command and auto-explain the error output if it fails; falls back to `--explain-exit` when there's no output
- `--delete-profile NAME`: delete a named profile from `~/.errexrc`
- `--pin` / `--unpin`: mark the last history entry as pinned; pinned entries are protected from `--clear-history`

## [0.16.0] — 2026-05-28
### Added
- `--explain-env VAR`: explain environment variables; 40+ known vars answered instantly with current value shown if set
- `--open`: export last explanation as HTML and open in the default browser
- `--rerun`: re-run the last shell command and explain if it fails (zsh/bash history)
- `--top N`: limit root cause analysis to the top N most likely causes
- `--word-wrap N`: set output console width

## [0.15.0] — 2026-05-28
### Added
- `--explain-cron EXPR`: explain a cron expression in plain English; standard patterns answered locally, complex ones via Claude
- `--snippet`: strip stdlib/site-packages/node_modules frames from a traceback before explaining
- `--debug`: dry run — print the prompt that would be sent to Claude, then exit without an API call
- `--list-profiles`: list all named profiles in `~/.errexrc`
- `--explain-http CODE`: explain HTTP status codes; 35+ known codes answered instantly
- `--add-note TEXT`: append a personal note to the last history entry
- `--format-json`: parse a JSON error blob and reformat it before explaining
- `--interactive`: numbered history picker — browse and select entries to view
- `--ci`: CI mode — forces no-color + terse, GitHub Actions `::error::` annotations, exits 1
- `--rate SCORE`: rate the last explanation 1–5; stored in history, average shown in `--stats`
- `--profile NAME`: load a named config profile from `~/.errexrc`; CLI flags always win
- `--bulk FILE`: explain multiple errors from a file separated by blank lines
- `--explain-exit CODE`: explain shell exit codes; 30+ known codes answered instantly
- `--webhook URL`: POST explanation JSON to Slack, Discord, or any generic endpoint
- `--find-name NAME`: retrieve history entries saved with `--save-as`
- `--timeout N`: set API request timeout in seconds (default: 30)

## [0.11.0] — 2026-05-28
### Added
- `--output FILE`: save the explanation to a `.txt` or `.md` file alongside printing
- `--terse`: single-sentence diagnosis, faster than `--brief`, ideal for scripting
- `--no-color`: strip all rich formatting for safe piping to `grep`, `less`, etc.
- `--since YYYY-MM-DD`: filter `--history` and `--recent` to entries on or after a date
- `--env`: auto-attach system info (OS, Python, shell, runtimes) as context; Windows-aware (detects PowerShell vs cmd)
- `--explain-regex PATTERN`: explain what a regex matches — breakdown table, examples, gotchas

## [0.10.0] — 2026-05-28
### Added
- `--doctor`: health check — verifies API key, live API connectivity, config validity, history, and PyPI version
- `--completion bash|zsh`: print a shell completion script (`source <(errex --completion zsh)`)
- `--translate LANG`: respond in any spoken language (e.g. `--translate Spanish`)
- `--save-as NAME`: tag an explanation with a name for quick retrieval from history
- `--grep PATTERN FILE`: filter a log file by regex, then explain the matching lines
- `--test-gen FILE`: generate a pytest/jest/go test case from a code file; pipe an error to reproduce the bug

## [0.9.0] — 2026-05-28
### Added
- `--version`: show the installed version
- `--recent [N]`: show the last N history entries (default 5)
- `--summarize-log FILE`: diagnostic digest of all distinct error types in a large log file
- `--retry`: re-explain the last error from history with different flags
### Changed
- README completely rewritten — full reference table for all 30+ flags

## [0.8.0] — 2026-05-28
### Added
- `--similar`: search your own history for past errors similar to the current one (Jaccard similarity on error fingerprints)
- `--ask "question"`: ask a follow-up about the last error in history without re-explaining it
- `--test-gen FILE`: generate a pytest/jest/go test case from a code file; pipe an error to make it reproduce the bug
- `--explain-diff`: explain a git diff — pipe `git diff | errex --explain-diff` or pass a .patch file
- `--config [key=value]`: view or edit `~/.errexrc` from the CLI; `--config lang=null` clears a value
- `--clear-history [DAYS]`: delete all history or only entries older than N days, with confirmation

## [0.7.0] — 2026-05-28
### Added
- `--explain-code FILE`: paste a code file and get a plain-English walkthrough
- `--issues QUERY`: search GitHub Issues for related bugs and workarounds
- `--lint FILE`: run a quick style/logic lint pass on a code file before explaining errors
- Smarter `--watch`: improved error deduplication with fingerprinting and 30-second cooldown
- `--export FILE`: export full history to a styled HTML or Markdown file (`--export-format html|md`)

## [0.6.0] — 2026-05-28
### Added
- `--notify`: desktop notification when a long explanation finishes
- `--chat`: interactive follow-up Q&A mode after an explanation
- `--context FILE`: attach a source file as extra context alongside the error
- `--tokens`: show input/output token counts after each explanation
- `--compare`: compare two errors for shared root causes (multi-file mode)
- Web UI: `errex --web` launches a local browser interface at http://localhost:7337

## [0.5.0] — 2026-05-28
### Added
- `--scan`: scans common system locations for recent error logs and offers a picker
- `--setup`: first-run wizard — checks API key, detects installed languages, writes `~/.errexrc`, installs shell integration

## [0.4.0] — 2026-05-28
### Added
- `--share`: posts explanation to paste.rs and prints a shareable URL
- `--stats`: usage dashboard — total runs, models used, top error types, busiest day/hour
- `--watch LOGFILE`: tails a log file and auto-explains errors as they appear
- `--fix`: outputs only the fix command, no explanation
- Colorized output via rich (headers, history rendered as markdown)
- Config file: `~/.errexrc` for default model/lang/brief/copy
- `--install-shell`: adds `errex-last()` to shell config
- Multi-file comparison: `errex a.txt b.txt` compares two errors for shared root causes
- CI and PyPI badges in README
- Web UI: `errex --web` launches a local browser interface at http://localhost:7337

## [0.3.0] — 2026-05-28
### Added
- `--history [SEARCH]`: view and search past explanations from `~/.errex_history`
- Auto-publish to PyPI via GitHub Actions on `v*` tag pushes

## [0.2.0] — 2026-05-28
### Added
- `--model`: choose which Claude model to use
- `--brief`: one-paragraph summary instead of full analysis
- `--lang`: language hint for ambiguous errors
- `--copy`: copy explanation to clipboard
- `--json`: structured JSON output (error_type, root_cause, fix_steps, gotchas)
- History: every explanation saved to `~/.errex_history`
- Exit codes: 0 success, 1 usage error, 2 API error
- GitHub Actions CI
- pytest test suite (10 tests)

## [0.1.0] — 2026-05-28
### Added
- Initial release
- Explain errors from a file, stdin, or interactive paste
- Streaming output powered by Claude
- `pip install errex` support via pyproject.toml
