"""errex init — detect project tech stack and save as local context."""
from __future__ import annotations
import json
import re
from pathlib import Path


_PROJECT_FILE = ".errex"


def detect_stack(root: Path | None = None) -> dict:
    root = root or Path.cwd()
    stack: dict = {}

    # Python
    if (root / "pyproject.toml").exists():
        _parse_pyproject(root / "pyproject.toml", stack)
    elif (root / "setup.py").exists() or (root / "setup.cfg").exists():
        stack["language"] = "Python"
    if (root / "requirements.txt").exists():
        stack.setdefault("language", "Python")

    # Node / JS / TS
    if (root / "package.json").exists():
        _parse_package_json(root / "package.json", stack)

    # Rust
    if (root / "Cargo.toml").exists():
        _parse_cargo_toml(root / "Cargo.toml", stack)

    # Go
    if (root / "go.mod").exists():
        _parse_go_mod(root / "go.mod", stack)

    # Ruby
    if (root / "Gemfile").exists():
        stack["language"] = "Ruby"
        _parse_gemfile(root / "Gemfile", stack)

    # Java / Kotlin
    if (root / "pom.xml").exists():
        stack["language"] = "Java"
        stack["build"] = "Maven"
    elif (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        stack.setdefault("language", "Java/Kotlin")
        stack["build"] = "Gradle"

    # .NET
    if list(root.glob("*.csproj")) or list(root.glob("*.sln")):
        stack["language"] = "C#"
        stack["runtime"] = ".NET"

    # Docker
    if (root / "Dockerfile").exists():
        stack["containerized"] = True

    # Version files
    if (root / ".python-version").exists():
        stack["python_version"] = (root / ".python-version").read_text().strip()
    if (root / ".nvmrc").exists():
        stack["node_version"] = (root / ".nvmrc").read_text().strip()
    elif (root / ".node-version").exists():
        stack["node_version"] = (root / ".node-version").read_text().strip()

    return stack


def _parse_pyproject(path: Path, stack: dict) -> None:
    text = path.read_text()
    stack["language"] = "Python"
    # Try tomllib (3.11+) then tomli then regex fallback
    try:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore
        data = tomllib.loads(text)
        proj = data.get("project", {})
        if proj.get("name"):
            stack["project_name"] = proj["name"]
        if proj.get("version"):
            stack["project_version"] = proj["version"]
        if proj.get("requires-python"):
            stack["python_requires"] = proj["requires-python"]
        deps_str = " ".join(proj.get("dependencies", []))
        if "django" in deps_str.lower():
            stack["framework"] = "Django"
        elif "flask" in deps_str.lower():
            stack["framework"] = "Flask"
        elif "fastapi" in deps_str.lower():
            stack["framework"] = "FastAPI"
        return
    except Exception:
        pass
    # regex fallback
    m = re.search(r'name\s*=\s*["\']([^"\']+)', text)
    if m:
        stack["project_name"] = m.group(1)
    m = re.search(r'requires-python\s*=\s*["\']([^"\']+)', text)
    if m:
        stack["python_requires"] = m.group(1)


def _parse_package_json(path: Path, stack: dict) -> None:
    try:
        data = json.loads(path.read_text())
        is_ts = (path.parent / "tsconfig.json").exists()
        stack["language"] = "TypeScript" if is_ts else "JavaScript"
        if data.get("name"):
            stack["project_name"] = data["name"]
        if data.get("version"):
            stack["project_version"] = data["version"]
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        if "react" in deps:
            stack["framework"] = "React"
        elif "vue" in deps:
            stack["framework"] = "Vue"
        elif "next" in deps:
            stack["framework"] = "Next.js"
        elif "express" in deps:
            stack["framework"] = "Express"
        if data.get("engines", {}).get("node"):
            stack["node_version"] = data["engines"]["node"]
    except Exception:
        stack.setdefault("language", "JavaScript")


def _parse_cargo_toml(path: Path, stack: dict) -> None:
    text = path.read_text()
    stack["language"] = "Rust"
    m = re.search(r'name\s*=\s*"([^"]+)"', text)
    if m:
        stack["project_name"] = m.group(1)
    m = re.search(r'edition\s*=\s*"([^"]+)"', text)
    if m:
        stack["rust_edition"] = m.group(1)


def _parse_go_mod(path: Path, stack: dict) -> None:
    text = path.read_text()
    stack["language"] = "Go"
    m = re.search(r"^module\s+(\S+)", text, re.MULTILINE)
    if m:
        stack["project_name"] = m.group(1)
    m = re.search(r"^go\s+(\S+)", text, re.MULTILINE)
    if m:
        stack["go_version"] = m.group(1)


def _parse_gemfile(path: Path, stack: dict) -> None:
    text = path.read_text()
    m = re.search(r"ruby ['\"]([^'\"]+)['\"]", text)
    if m:
        stack["ruby_version"] = m.group(1)
    if "rails" in text.lower():
        stack["framework"] = "Rails"
    elif "sinatra" in text.lower():
        stack["framework"] = "Sinatra"


def format_context(stack: dict) -> str:
    """Format stack as a compact one-liner for Claude prompts."""
    if not stack:
        return ""
    parts = []
    if stack.get("project_name"):
        s = stack["project_name"]
        if stack.get("project_version"):
            s += f" v{stack['project_version']}"
        parts.append(f"Project: {s}")
    if stack.get("language"):
        lang = stack["language"]
        for key, suffix in [("python_requires", ""), ("python_version", ""), ("go_version", ""), ("node_version", "node "), ("rust_edition", "edition ")]:
            if stack.get(key):
                lang += f" ({suffix}{stack[key]})"
                break
        parts.append(f"Language: {lang}")
    if stack.get("framework"):
        parts.append(f"Framework: {stack['framework']}")
    if stack.get("build"):
        parts.append(f"Build: {stack['build']}")
    if stack.get("containerized"):
        parts.append("Docker: yes")
    return " | ".join(parts)


def save_project_context(stack: dict, path: Path | None = None) -> Path:
    target = (path or Path.cwd()) / _PROJECT_FILE
    target.write_text(json.dumps(stack, indent=2))
    return target


def load_project_context(start: Path | None = None) -> dict:
    """Walk up from start looking for .errex, stopping at git root."""
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        candidate = directory / _PROJECT_FILE
        if candidate.exists():
            try:
                return json.loads(candidate.read_text())
            except Exception:
                return {}
        if (directory / ".git").exists():
            break
    return {}


def run_init(root: Path | None = None) -> None:
    from rich.console import Console
    from rich.table import Table
    console = Console()
    root = root or Path.cwd()

    console.print(f"\n[bold]errex init[/bold] — scanning [cyan]{root}[/cyan]...\n")
    stack = detect_stack(root)

    if not stack:
        console.print("[yellow]No project files detected.[/yellow] Create a pyproject.toml, package.json, Cargo.toml, go.mod, or Gemfile first.\n")
        return

    table = Table(show_header=False, box=None, padding=(0, 1))
    for k, v in stack.items():
        val = str(v)
        table.add_row(f"[dim]{k}[/dim]", f"[green]{val}[/green]")
    console.print(table)

    ctx = format_context(stack)
    console.print(f"\n[dim]Context string:[/dim] {ctx}\n")

    saved = save_project_context(stack, root)
    console.print(f"[green]✓[/green] Saved to [cyan]{saved.name}[/cyan] — future errex calls in this directory will include this context.\n")
    console.print("[dim]Tip: add .errex to .gitignore if it contains sensitive info.[/dim]\n")
