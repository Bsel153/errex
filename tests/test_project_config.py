import pytest
from pathlib import Path
from errex.project_config import init_project, load_project_config, TEMPLATE


def test_template_is_valid_yaml():
    import yaml
    data = yaml.safe_load(TEMPLATE)
    assert data["model"] == "claude-sonnet-4-6"
    assert data["redact"] is True


def test_template_has_scan_section():
    import yaml
    data = yaml.safe_load(TEMPLATE)
    assert "scan" in data


def test_init_project_creates_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_project()
    assert (tmp_path / ".errex.yml").exists()
    content = (tmp_path / ".errex.yml").read_text()
    assert "model:" in content


def test_init_project_no_overwrite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".errex.yml").write_text("existing: true\n")
    init_project(force=False)
    assert (tmp_path / ".errex.yml").read_text() == "existing: true\n"


def test_init_project_force_overwrite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".errex.yml").write_text("old: true\n")
    init_project(force=True)
    content = (tmp_path / ".errex.yml").read_text()
    assert "model:" in content
    assert content == TEMPLATE


def test_load_project_config_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_project_config() == {}


def test_load_project_config_reads_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".errex.yml").write_text("model: claude-opus-4-8\nbrief: true\n")
    cfg = load_project_config()
    assert cfg["model"] == "claude-opus-4-8"
    assert cfg["brief"] is True


def test_load_project_config_bad_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".errex.yml").write_text(": : : invalid yaml {{{\n")
    cfg = load_project_config()
    assert cfg == {}
