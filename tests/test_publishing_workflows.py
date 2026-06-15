import yaml
from pathlib import Path


def _load(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text())


def test_pypi_workflow_on_release():
    wf = _load(".github/workflows/publish-pypi.yml")
    assert "release" in wf["on"]


def test_pypi_workflow_has_oidc_permissions():
    wf = _load(".github/workflows/publish-pypi.yml")
    publish = wf["jobs"]["publish"]
    assert publish.get("permissions", {}).get("id-token") == "write"


def test_pypi_workflow_uses_trusted_publishing():
    wf = _load(".github/workflows/publish-pypi.yml")
    steps = wf["jobs"]["publish"]["steps"]
    uses = [s.get("uses", "") for s in steps]
    assert any("pypi-publish" in u for u in uses)


def test_vscode_workflow_on_release():
    wf = _load(".github/workflows/publish-vscode.yml")
    assert "release" in wf["on"]


def test_vscode_workflow_publishes_vsix():
    wf = _load(".github/workflows/publish-vscode.yml")
    steps = wf["jobs"]["publish"]["steps"]
    runs = [s.get("run", "") for s in steps]
    assert any("vsce publish" in r for r in runs)


def test_release_guide_exists():
    content = Path("RELEASE.md").read_text()
    assert "PyPI" in content
    assert "VS Code" in content
    assert "Trusted Publishing" in content
