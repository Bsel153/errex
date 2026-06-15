import json
import pytest
from pathlib import Path
from errex.init_cmd import detect_stack, format_context, save_project_context, load_project_context

def test_detect_python_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "myapp"\nversion = "1.0.0"\nrequires-python = ">=3.11"\ndependencies = ["fastapi"]\n'
    )
    stack = detect_stack(tmp_path)
    assert stack["language"] == "Python"
    assert stack.get("project_name") == "myapp"
    assert stack.get("framework") == "FastAPI"

def test_detect_node(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"name":"myapp","dependencies":{"react":"^18.0.0"}}'
    )
    stack = detect_stack(tmp_path)
    assert "JavaScript" in stack["language"]
    assert stack.get("framework") == "React"

def test_detect_rust(tmp_path):
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "mybin"\nversion = "0.1.0"\nedition = "2021"\n'
    )
    stack = detect_stack(tmp_path)
    assert stack["language"] == "Rust"
    assert stack.get("rust_edition") == "2021"

def test_detect_go(tmp_path):
    (tmp_path / "go.mod").write_text("module github.com/user/myapp\n\ngo 1.22\n")
    stack = detect_stack(tmp_path)
    assert stack["language"] == "Go"
    assert stack.get("go_version") == "1.22"

def test_detect_empty(tmp_path):
    assert detect_stack(tmp_path) == {}

def test_format_context():
    stack = {"language": "Python", "project_name": "errex", "project_version": "0.22.0", "framework": "FastAPI"}
    ctx = format_context(stack)
    assert "Python" in ctx and "errex" in ctx and "FastAPI" in ctx

def test_save_load_roundtrip(tmp_path):
    stack = {"language": "Rust", "project_name": "mybin"}
    save_project_context(stack, tmp_path)
    assert load_project_context(tmp_path) == stack

def test_load_walks_up_to_git_root(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".errex").write_text('{"language":"Go"}')
    subdir = tmp_path / "pkg" / "utils"
    subdir.mkdir(parents=True)
    assert load_project_context(subdir)["language"] == "Go"

def test_load_returns_empty_when_not_found(tmp_path):
    assert load_project_context(tmp_path) == {}
