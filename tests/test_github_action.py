import yaml
from pathlib import Path


def test_action_yml_valid():
    action = yaml.safe_load(Path(".github/actions/explain/action.yml").read_text())
    assert action["name"]
    assert "error-text" in action["inputs"]
    assert "explanation" in action["outputs"]
    assert action["runs"]["using"] == "composite"


def test_action_has_steps():
    action = yaml.safe_load(Path(".github/actions/explain/action.yml").read_text())
    steps = action["runs"]["steps"]
    assert len(steps) >= 2
    step_ids = [s.get("id") for s in steps]
    assert "explain" in step_ids
