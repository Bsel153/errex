import yaml
from pathlib import Path


def _load(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text())


def test_pypi_workflow_on_tag():
    wf = _load(".github/workflows/publish.yml")
    triggers = wf[True]  # YAML parses bare `on:` as boolean True
    assert "push" in triggers
    assert "v*" in triggers["push"]["tags"]


def test_pypi_workflow_uses_pypi_publish_action():
    wf = _load(".github/workflows/publish.yml")
    steps = wf["jobs"]["publish"]["steps"]
    uses = [s.get("uses", "") for s in steps]
    assert any("pypi-publish" in u for u in uses)


def test_pypi_workflow_uses_api_token_not_oidc():
    wf = _load(".github/workflows/publish.yml")
    steps = wf["jobs"]["publish"]["steps"]
    publish_step = next(s for s in steps if "pypi-publish" in s.get("uses", ""))
    assert "PYPI_API_TOKEN" in str(publish_step.get("with", {}).get("password", ""))


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
