# errex — AI Error Explainer for VS Code

Instantly explain any error message in plain English, powered by [errex](https://github.com/errex/errex) and Claude.

## What it does

Select an error message in any editor, right-click, and choose **Explain Error with errex**. A panel opens beside your editor with a clear, plain-English explanation of the error, including what caused it and how to fix it.

## Requirements

- [errex](https://pypi.org/project/errex/) installed and on your PATH:
  ```
  pip install errex
  ```
- An Anthropic API key for full Claude-powered explanations (optional — errex falls back to local pattern matching without one).

## How to use

### Right-click (editor context menu)

1. Select the error text in any editor file or terminal output pasted into a file.
2. Right-click the selection.
3. Choose **errex: Explain Error with errex**.
4. The explanation appears in a panel beside your editor.

### Command palette

Open the Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`) and run:

- **errex: Explain Error with errex** — explains the current selection.
- **errex: Explain Error from Clipboard** — reads the error from your clipboard.

## Settings

| Setting | Default | Description |
|---|---|---|
| `errex.anthropicApiKey` | `""` | Anthropic API key. Falls back to `ANTHROPIC_API_KEY` env var if empty. |
| `errex.cliPath` | `"errex"` | Path to the errex CLI binary. |
| `errex.useWebUi` | `false` | Send errors to a running errex web UI instead of the CLI. |
| `errex.webUiUrl` | `"http://localhost:7337"` | URL of the errex web UI backend. |

## Web UI mode

If you have the errex web UI running locally, enable `errex.useWebUi` to send errors to it instead of shelling out to the CLI. Set `errex.webUiUrl` to the address of your running instance.

## Links

- [errex on GitHub](https://github.com/errex/errex)
- [errex on PyPI](https://pypi.org/project/errex/)
- [Report issues](https://github.com/errex/errex/issues)
