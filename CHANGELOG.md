# Changelog

All notable changes to errex are documented here.

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
