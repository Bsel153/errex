import json
import re
from pathlib import Path

EXT = Path(__file__).parent.parent / "extensions/vscode"


# ── Manifest ──────────────────────────────────────────────────────────────────

def test_package_json_valid():
    pkg = json.loads((EXT / "package.json").read_text())
    assert pkg["name"] == "errex"
    assert "errex.explainSelection" in [c["command"] for c in pkg["contributes"]["commands"]]
    assert pkg["engines"]["vscode"]


def test_both_commands_registered():
    pkg = json.loads((EXT / "package.json").read_text())
    commands = [c["command"] for c in pkg["contributes"]["commands"]]
    assert "errex.explainSelection" in commands
    assert "errex.explainFromClipboard" in commands


def test_context_menu_wired_to_explain_selection():
    pkg = json.loads((EXT / "package.json").read_text())
    menus = pkg.get("contributes", {}).get("menus", {})
    editor_menus = menus.get("editor/context", [])
    cmds = [m["command"] for m in editor_menus]
    assert "errex.explainSelection" in cmds


def test_configuration_properties_present():
    pkg = json.loads((EXT / "package.json").read_text())
    props = pkg["contributes"]["configuration"]["properties"]
    assert "errex.anthropicApiKey" in props
    assert "errex.cliPath" in props
    assert "errex.useWebUi" in props
    assert "errex.webUiUrl" in props


def test_cli_path_default_is_errex():
    pkg = json.loads((EXT / "package.json").read_text())
    cli_prop = pkg["contributes"]["configuration"]["properties"]["errex.cliPath"]
    assert cli_prop["default"] == "errex"


def test_web_ui_url_default():
    pkg = json.loads((EXT / "package.json").read_text())
    url_prop = pkg["contributes"]["configuration"]["properties"]["errex.webUiUrl"]
    assert "localhost" in url_prop["default"]
    assert "7337" in url_prop["default"]


# ── Source ────────────────────────────────────────────────────────────────────

def test_extension_ts_exists():
    assert (EXT / "src/extension.ts").exists()


def test_extension_exports_activate():
    src = (EXT / "src/extension.ts").read_text()
    assert "export function activate" in src


def test_extension_exports_deactivate():
    src = (EXT / "src/extension.ts").read_text()
    assert "export function deactivate" in src


def test_extension_registers_explain_selection():
    src = (EXT / "src/extension.ts").read_text()
    assert "errex.explainSelection" in src


def test_extension_registers_explain_from_clipboard():
    src = (EXT / "src/extension.ts").read_text()
    assert "errex.explainFromClipboard" in src


def test_cli_invocation_uses_no_history_and_terse():
    """The CLI spawn must pass --no-history and --terse so explanations are fast and don't pollute history."""
    src = (EXT / "src/extension.ts").read_text()
    assert "--no-history" in src
    assert "--terse" in src


def test_cli_invocation_reads_from_stdin():
    """The extension should pipe error text via stdin (the '-' argument)."""
    src = (EXT / "src/extension.ts").read_text()
    # The spawn call should include '-' as a positional arg for stdin mode
    assert "'-'" in src or '"-"' in src


def test_web_ui_path_is_explain_endpoint():
    src = (EXT / "src/extension.ts").read_text()
    assert "/explain" in src


def test_html_output_escapes_user_content():
    """Webview HTML must escape <, >, & to prevent script injection from error text."""
    src = (EXT / "src/extension.ts").read_text()
    assert "&amp;" in src or "replace(/&/g" in src
    assert "&lt;" in src or "replace(/</g" in src


def test_uses_vscode_progress_notification():
    src = (EXT / "src/extension.ts").read_text()
    assert "ProgressLocation.Notification" in src


# ── Build config ──────────────────────────────────────────────────────────────

def test_tsconfig_exists():
    assert (EXT / "tsconfig.json").exists()


def test_tsconfig_targets_es6_or_later():
    tsconfig = json.loads((EXT / "tsconfig.json").read_text())
    target = tsconfig.get("compilerOptions", {}).get("target", "").upper()
    # ES2017 or higher is fine for VS Code extensions
    assert target in ("ES6", "ES2017", "ES2018", "ES2019", "ES2020", "ES2021", "ES2022", "ESNEXT")


def test_vscodeignore_exists():
    assert (EXT / ".vscodeignore").exists()


def test_vscodeignore_excludes_source():
    content = (EXT / ".vscodeignore").read_text()
    # Source TypeScript files should be excluded from the packaged extension
    assert "src" in content or ".ts" in content
