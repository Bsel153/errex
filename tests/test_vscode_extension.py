import json
from pathlib import Path

EXT = Path(__file__).parent.parent / "extensions/vscode"


def test_package_json_valid():
    pkg = json.loads((EXT / "package.json").read_text())
    assert pkg["name"] == "errex"
    assert "errex.explainSelection" in [c["command"] for c in pkg["contributes"]["commands"]]
    assert pkg["engines"]["vscode"]


def test_extension_ts_exists():
    assert (EXT / "src/extension.ts").exists()


def test_tsconfig_exists():
    assert (EXT / "tsconfig.json").exists()


def test_vscodeignore_exists():
    assert (EXT / ".vscodeignore").exists()
