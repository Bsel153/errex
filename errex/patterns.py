from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Pattern:
    title: str
    regex: re.Pattern
    explanation: str  # markdown; {0},{1} are substituted with capture groups


PATTERNS: list[Pattern] = [
    # ── Python ───────────────────────────────────────────────────────────────
    Pattern(
        title="Python — ModuleNotFoundError",
        regex=re.compile(r"ModuleNotFoundError: No module named '([^']+)'"),
        explanation=(
            "**`{0}` is not installed** in the active Python environment.\n\n"
            "**Fix:**\n```bash\npip install {0}\n```\n"
            "Make sure the right virtual environment is activated first (`which python`).\n\n"
            "**Gotcha**: The pip package name and the import name often differ — "
            "e.g. `pip install Pillow` but `import PIL`."
        ),
    ),
    Pattern(
        title="Python — ImportError (cannot import name)",
        regex=re.compile(r"ImportError: cannot import name '([^']+)' from '([^']+)'"),
        explanation=(
            "**`{0}` does not exist in `{1}`** — it was removed, renamed, "
            "or never existed in this version.\n\n"
            "**Fix**: Check what the package actually exports:\n"
            "```python\nimport {1}; print(dir({1}))\n```\n"
            "Check the library's changelog for breaking changes between versions.\n\n"
            "**Gotcha**: Often caused by upgrading (or downgrading) a package across a major version boundary."
        ),
    ),
    Pattern(
        title="Python — AttributeError (NoneType)",
        regex=re.compile(r"AttributeError: 'NoneType' object has no attribute '([^']+)'"),
        explanation=(
            "**A variable is `None` where an object is expected.** "
            "You're calling `.{0}` on something that returned `None`.\n\n"
            "**Fix**: Add a guard before the attribute access:\n"
            "```python\nif result is not None:\n    result.{0}\n```\n"
            "Trace back to where the variable is assigned to find why it can be `None`.\n\n"
            "**Gotcha**: In-place methods like `list.sort()` and `list.append()` return `None` — "
            "don't chain them."
        ),
    ),
    Pattern(
        title="Python — AttributeError (module attribute missing)",
        regex=re.compile(r"AttributeError: module '([^']+)' has no attribute '([^']+)'"),
        explanation=(
            "**`{1}` does not exist in the `{0}` module.** "
            "It may have been renamed, moved, or removed in your installed version.\n\n"
            "**Fix**: Check what's available:\n"
            "```python\nimport {0}; print(dir({0}))\n```\n\n"
            "**Gotcha**: If you have a local file named `{0}.py`, it shadows the real package — rename it."
        ),
    ),
    Pattern(
        title="Python — AttributeError",
        regex=re.compile(r"AttributeError: '([^']+)' object has no attribute '([^']+)'"),
        explanation=(
            "**`{0}` objects don't have a `.{1}` attribute.** "
            "Check for a typo, or confirm you have the right object type.\n\n"
            "**Fix**:\n```python\nprint(type(obj))   # confirm the type\nprint(dir(obj))    # list available attributes\n```\n\n"
            "**Gotcha**: If you're expecting a dict, use `obj['{1}']` not `obj.{1}`."
        ),
    ),
    Pattern(
        title="Python — NameError (not defined)",
        regex=re.compile(r"NameError: name '([^']+)' is not defined"),
        explanation=(
            "**`{0}` is used before it's defined** (or it's out of scope).\n\n"
            "**Fix**: Common causes:\n"
            "- Typo in the variable name\n"
            "- Defined inside an `if` block that didn't execute\n"
            "- Forgot to import: `from module import {0}`\n\n"
            "**Gotcha**: In Python 3, `print` is a function — `print 'hello'` gives NameError/SyntaxError."
        ),
    ),
    Pattern(
        title="Python — TypeError (wrong argument count)",
        regex=re.compile(r"TypeError: .+\(\) (takes|missing) \d+ (required )?positional argument"),
        explanation=(
            "**A function was called with the wrong number of arguments.**\n\n"
            "**Fix**: Check the function signature vs how many arguments you're passing. "
            "Common causes:\n"
            "- Forgot `self` when calling an instance method outside the class\n"
            "- Extra or missing argument in a function call\n\n"
            "**Gotcha**: If you stored a bound method in a variable, `self` is already captured — "
            "don't pass it again."
        ),
    ),
    Pattern(
        title="Python — TypeError (unsupported operand types)",
        regex=re.compile(r"TypeError: unsupported operand type\(s\) for (.+): '(\w+)' and '(\w+)'"),
        explanation=(
            "**You can't use `{0}` between a `{1}` and a `{2}`.** Python won't auto-convert types.\n\n"
            "**Fix**: Convert explicitly:\n"
            "```python\nstr(value) + other_string\n# or\nint(string) + number\n```\n\n"
            "**Gotcha**: `+` on strings is concatenation. "
            "Use f-strings for mixed formatting: `f\"{num} items\"`."
        ),
    ),
    Pattern(
        title="Python — TypeError (object not subscriptable/iterable/callable)",
        regex=re.compile(r"TypeError: '([^']+)' object is not (subscriptable|iterable|callable)"),
        explanation=(
            "**A `{0}` object is not {1}.** "
            "You're treating it like a list/dict/function when it isn't.\n\n"
            "**Fix**: Check the type at runtime:\n```python\nprint(type(obj))\n```\n"
            "Common causes: calling `None` as a function, indexing an integer, iterating a non-iterable.\n\n"
            "**Gotcha**: A function that returns `None` — calling the return value then gives this error."
        ),
    ),
    Pattern(
        title="Python — ValueError (int conversion failed)",
        regex=re.compile(r"ValueError: invalid literal for int\(\) with base \d+: '([^']+)'"),
        explanation=(
            "**`'{0}'` cannot be converted to an integer.**\n\n"
            "**Fix**: Validate before converting:\n"
            "```python\nif s.strip().lstrip('-').isdigit():\n    n = int(s)\n```\n"
            "Or wrap in `try/except ValueError`.\n\n"
            "**Gotcha**: `int('3.14')` also raises this — use `int(float('3.14'))` for decimals."
        ),
    ),
    Pattern(
        title="Python — KeyError",
        regex=re.compile(r"KeyError: (.+)"),
        explanation=(
            "**The key {0} doesn't exist in the dictionary.**\n\n"
            "**Fix**: Use `.get()` to avoid the error:\n"
            "```python\nvalue = d.get({0}, default_value)\n```\n"
            "Or check first: `if {0} in d:`\n\n"
            "**Gotcha**: String keys are case-sensitive. `d['Key']` and `d['key']` are different."
        ),
    ),
    Pattern(
        title="Python — IndexError (out of range)",
        regex=re.compile(r"IndexError: (list|tuple) index out of range"),
        explanation=(
            "**You accessed an index that doesn't exist in the {0}.**\n\n"
            "**Fix**: Guard the access:\n"
            "```python\nif index < len(items):\n    item = items[index]\n```\n"
            "Use `items[-1]` for the last element safely.\n\n"
            "**Gotcha**: `range(len(items) + 1)` in a loop will hit this on the last iteration."
        ),
    ),
    Pattern(
        title="Python — IndentationError",
        regex=re.compile(r"IndentationError:", re.IGNORECASE),
        explanation=(
            "**Python found inconsistent indentation.**\n\n"
            "**Fix**:\n"
            "- Use spaces **or** tabs consistently — never mix both\n"
            "- Standard is 4 spaces per level\n"
            "- Run: `python -tt script.py` to find mixed tabs/spaces\n\n"
            "**Gotcha**: Copy-pasting from the web often introduces invisible tab/space mixing."
        ),
    ),
    Pattern(
        title="Python — SyntaxError",
        regex=re.compile(r"SyntaxError: (unexpected EOF|invalid syntax|EOL while scanning)", re.IGNORECASE),
        explanation=(
            "**Python can't parse this code.** Common causes:\n"
            "- Missing closing `)`, `]`, `}`, or `\"`\n"
            "- Python 2 syntax in Python 3 (`print 'hello'`)\n"
            "- Typo in a keyword\n\n"
            "**Fix**: Look at the line *before* the one Python points to — "
            "the real mistake is often there (e.g. a missing `)` on the previous line).\n\n"
            "**Gotcha**: The reported line number is where Python gave up, not always where you made the mistake."
        ),
    ),
    Pattern(
        title="Python — ZeroDivisionError",
        regex=re.compile(r"ZeroDivisionError"),
        explanation=(
            "**Division by zero.**\n\n"
            "**Fix**: Guard the denominator:\n"
            "```python\nresult = a / b if b != 0 else 0\n```\n\n"
            "**Gotcha**: Also raised by `%` (modulo) and `//` (floor division), not just `/`."
        ),
    ),
    Pattern(
        title="Python — RecursionError",
        regex=re.compile(r"RecursionError: maximum recursion depth exceeded"),
        explanation=(
            "**A function called itself too many times** (default limit: 1000).\n\n"
            "**Fix**:\n"
            "1. Add a base case to your recursive function that stops the recursion\n"
            "2. Check for accidental circular calls\n"
            "3. Last resort: `import sys; sys.setrecursionlimit(n)` (rarely the right fix)\n\n"
            "**Gotcha**: Deep recursion on large nested data (JSON trees, file paths) commonly hits this."
        ),
    ),
    Pattern(
        title="Python — FileNotFoundError",
        regex=re.compile(r"FileNotFoundError: \[Errno 2\] No such file or directory: '([^']+)'"),
        explanation=(
            "**The file or directory `{0}` doesn't exist** at the path you specified.\n\n"
            "**Fix**: Check your working directory:\n"
            "```python\nimport os; print(os.getcwd())\n```\n"
            "Or use `pathlib` for robust path handling:\n"
            "```python\nfrom pathlib import Path\nif Path('{0}').exists(): ...\n```\n\n"
            "**Gotcha**: Relative paths are relative to where Python is *run*, not where the script lives. "
            "Use `Path(__file__).parent / 'file.txt'` for script-relative paths."
        ),
    ),
    Pattern(
        title="Python — PermissionError",
        regex=re.compile(r"PermissionError: \[Errno 13\] Permission denied: '([^']+)'"),
        explanation=(
            "**You don't have permission to access `{0}`.**\n\n"
            "**Fix**:\n```bash\nls -la {0}\nchmod 644 {0}   # for files\nchmod 755 {0}   # for directories\n```\n\n"
            "**Gotcha**: On Windows, files locked by another process also raise PermissionError."
        ),
    ),
    Pattern(
        title="Python — JSONDecodeError",
        regex=re.compile(r"json\.decoder\.JSONDecodeError|JSONDecodeError", re.IGNORECASE),
        explanation=(
            "**The input is not valid JSON.**\n\n"
            "**Fix**: Inspect what you're actually receiving before parsing:\n"
            "```python\nprint(repr(text[:200]))\n```\n"
            "Common causes: HTML error page instead of JSON, trailing comma, single quotes.\n\n"
            "**Gotcha**: Python's `json` module is strict — no comments, no trailing commas. "
            "Use `json5` or `tomllib` for more relaxed formats."
        ),
    ),
    # ── Network ──────────────────────────────────────────────────────────────
    Pattern(
        title="Network — Connection Refused",
        regex=re.compile(r"ConnectionRefusedError|ECONNREFUSED", re.IGNORECASE),
        explanation=(
            "**Nothing is listening on the port you're connecting to.**\n\n"
            "**Fix**:\n"
            "1. Check the service is running: `lsof -i :<port>` or `ss -tlnp`\n"
            "2. Verify the host and port are correct\n"
            "3. Check for firewall rules blocking the port\n\n"
            "**Gotcha**: If your server just started, give it a moment to bind. "
            "Retry with exponential backoff in production code."
        ),
    ),
    Pattern(
        title="Network — Connection Timed Out",
        regex=re.compile(r"(connection timed out|ETIMEDOUT|timed out)", re.IGNORECASE),
        explanation=(
            "**The connection attempt exceeded the timeout limit** — the remote host didn't respond in time.\n\n"
            "**Fix**:\n"
            "- Check network connectivity: `ping <host>` / `curl -v <url>`\n"
            "- The remote server may be overloaded or down\n"
            "- Increase the timeout if the operation is legitimately slow\n\n"
            "**Gotcha**: Firewalls that silently drop packets (rather than actively refusing) cause "
            "timeouts rather than connection-refused errors."
        ),
    ),
    # ── JavaScript / Node ────────────────────────────────────────────────────
    Pattern(
        title="Node.js — Cannot find module",
        regex=re.compile(r"Cannot find module '([^']+)'", re.IGNORECASE),
        explanation=(
            "**The module `{0}` is not installed or the path is wrong.**\n\n"
            "**Fix**:\n```bash\nnpm install {0}\n```\n"
            "If the install seems corrupt:\n"
            "```bash\nrm -rf node_modules && npm install\n```\n\n"
            "**Gotcha**: Package names are case-sensitive on Linux but not macOS — "
            "this causes CI failures that don't repro locally."
        ),
    ),
    Pattern(
        title="JavaScript — TypeError (not a function)",
        regex=re.compile(r"TypeError: ([\w.[\]\"']+) is not a function"),
        explanation=(
            "**`{0}` is not a function** — it's `undefined`, `null`, or a different type.\n\n"
            "**Fix**: Check what it actually is:\n```js\nconsole.log(typeof {0}, {0});\n```\n"
            "Common causes: wrong import (`import {{foo}}` vs `import foo`), "
            "async function returning a Promise instead of a value.\n\n"
            "**Gotcha**: `const log = console.log; log('hi')` loses the `this` binding — "
            "use `console.log.bind(console)` instead."
        ),
    ),
    Pattern(
        title="JavaScript — ReferenceError (not defined)",
        regex=re.compile(r"ReferenceError: (\w+) is not defined"),
        explanation=(
            "**`{0}` is used before it's declared** or doesn't exist in this scope.\n\n"
            "**Fix**:\n"
            "- Declare with `const`, `let`, or `var` before use\n"
            "- Check for typos in the variable name\n"
            "- For browser globals, confirm you're running in a browser context\n\n"
            "**Gotcha**: `let`/`const` are not hoisted — accessing them before declaration "
            "gives ReferenceError (temporal dead zone), unlike `var`."
        ),
    ),
    Pattern(
        title="JavaScript — SyntaxError (unexpected token / JSON)",
        regex=re.compile(r"SyntaxError: Unexpected token|SyntaxError: Unexpected end of JSON", re.IGNORECASE),
        explanation=(
            "**JavaScript (or JSON) can't be parsed.**\n\n"
            "For JSON: look for trailing commas, single quotes, or JS-style comments. Validate:\n"
            "```bash\nnode -e \"JSON.parse(require('fs').readFileSync('file.json','utf8'))\"\n```\n"
            "For JS: look for missing brackets, invalid arrow function syntax, or reserved word as identifier.\n\n"
            "**Gotcha**: JSON doesn't support comments or trailing commas — use JSONC or JSON5 if you need them."
        ),
    ),
    Pattern(
        title="Node.js — ENOENT (file not found)",
        regex=re.compile(r"ENOENT: no such file or directory", re.IGNORECASE),
        explanation=(
            "**A file or directory in your path doesn't exist.**\n\n"
            "**Fix**: Log the exact resolved path:\n"
            "```js\nconsole.log(require('path').resolve(filePath));\n```\n"
            "Relative paths are relative to `process.cwd()`, not the script location.\n\n"
            "**Gotcha**: Use `path.join(__dirname, 'file.txt')` to get paths relative to the current script."
        ),
    ),
    Pattern(
        title="Node.js — EADDRINUSE (port in use)",
        regex=re.compile(r"EADDRINUSE: address already in use", re.IGNORECASE),
        explanation=(
            "**The port you're trying to bind is already taken.**\n\n"
            "**Fix**: Find and kill the process using the port:\n"
            "```bash\nlsof -ti :<port> | xargs kill   # macOS/Linux\n```\n"
            "Or change your app to a different port.\n\n"
            "**Gotcha**: A crashed server process may still hold the port for a few seconds — "
            "wait briefly and retry."
        ),
    ),
    Pattern(
        title="JavaScript — TypeError (null/undefined property access)",
        regex=re.compile(r"Cannot read propert(?:y|ies) of (null|undefined)"),
        explanation=(
            "**You're accessing a property on `{0}`.** The object hasn't been initialized yet.\n\n"
            "**Fix**: Use optional chaining:\n"
            "```js\nconst value = obj?.property?.nested;\n```\n"
            "Or add an explicit guard:\n"
            "```js\nif (obj != null) {{ /* use obj */ }}\n```\n\n"
            "**Gotcha**: Async operations often return `undefined` if you forgot to `await` the Promise."
        ),
    ),
    # ── Shell / OS ───────────────────────────────────────────────────────────
    Pattern(
        title="Shell — command not found",
        regex=re.compile(r"command not found", re.IGNORECASE),
        explanation=(
            "**The command isn't in your `$PATH` or isn't installed.**\n\n"
            "**Fix**:\n"
            "```bash\nwhich <command>         # find it if installed\necho $PATH              # inspect your PATH\n"
            "brew install <tool>     # macOS\napt install <tool>     # Debian/Ubuntu\n```\n\n"
            "**Gotcha**: If you just installed something and it's not found, "
            "open a new terminal or run `source ~/.bashrc` / `source ~/.zshrc` to reload PATH."
        ),
    ),
    Pattern(
        title="Shell — Permission denied",
        regex=re.compile(r"permission denied", re.IGNORECASE),
        explanation=(
            "**You don't have permission to execute or access this file/directory.**\n\n"
            "**Fix**:\n"
            "```bash\nls -la <path>            # check current permissions\nchmod +x script.sh       # make executable\nchmod 644 file.txt       # standard file permissions\n```\n"
            "Use `sudo` only if truly necessary.\n\n"
            "**Gotcha**: On Windows (WSL), files created in Windows Explorer may not have executable bits."
        ),
    ),
    Pattern(
        title="Shell — Segmentation Fault",
        regex=re.compile(r"segmentation fault|sigsegv", re.IGNORECASE),
        explanation=(
            "**A program accessed memory it doesn't own** — null pointer, buffer overflow, or use-after-free.\n\n"
            "**Fix**: Debug with:\n"
            "```bash\ngdb ./program                            # Linux debugger\nvalgrind ./program                       # memory error detector\n"
            "# Or compile with AddressSanitizer:\ncc -fsanitize=address -g -o prog prog.c\n```\n"
            "For Python extension crashes: `python -X faulthandler script.py`\n\n"
            "**Gotcha**: Segfaults in Python `.so` extensions appear as bare 'Segmentation fault' with no traceback."
        ),
    ),
    Pattern(
        title="Shell — No Space Left on Device",
        regex=re.compile(r"No space left on device", re.IGNORECASE),
        explanation=(
            "**The disk is full.**\n\n"
            "**Fix**:\n"
            "```bash\ndf -h                                    # disk usage by partition\ndu -sh /* 2>/dev/null | sort -h | tail -20  # largest directories\n```\n"
            "Common culprits: log files, Docker images (`docker system prune`), old package caches.\n\n"
            "**Gotcha**: `df -i` shows inode usage — many small files can exhaust inodes "
            "before filling disk space."
        ),
    ),
    Pattern(
        title="Process — Killed (OOM)",
        regex=re.compile(r"\bKilled\b|out of memory|oom.killer", re.IGNORECASE),
        explanation=(
            "**The process was killed by the OS for using too much memory.**\n\n"
            "**Fix**:\n"
            "- Check available memory: `free -h` (Linux)\n"
            "- Process large data in chunks instead of loading it all at once\n"
            "- Profile peak memory: `tracemalloc` (Python), `process.memoryUsage()` (Node)\n\n"
            "**Gotcha**: In Docker containers, the container memory limit (not host RAM) is what matters. "
            "Check `docker stats`."
        ),
    ),
    # ── Git ──────────────────────────────────────────────────────────────────
    Pattern(
        title="Git — Not a repository",
        regex=re.compile(r"not a git repository", re.IGNORECASE),
        explanation=(
            "**You're running a git command outside a git repository.**\n\n"
            "**Fix**:\n"
            "```bash\ngit init              # create a new repo here\ncd /path/to/repo      # or navigate to the existing repo\n```\n\n"
            "**Gotcha**: `git` searches parent directories for `.git/` — "
            "if you're deep in a project that should be a repo, the `.git/` directory may have been deleted."
        ),
    ),
    Pattern(
        title="Git — Merge Conflict",
        regex=re.compile(r"CONFLICT \(content\): Merge conflict in", re.IGNORECASE),
        explanation=(
            "**Two branches changed the same lines differently.** Git can't decide which version to keep.\n\n"
            "**Fix**:\n"
            "1. Open each conflicted file — look for `<<<<<<<`, `=======`, `>>>>>>>`\n"
            "2. Edit to keep what you want, remove the conflict markers\n"
            "3. `git add <resolved-files>` then `git commit`\n\n"
            "Or use a visual tool: `git mergetool`\n\n"
            "**Gotcha**: `git status` shows all conflicted files. Don't commit until every one is resolved."
        ),
    ),
    Pattern(
        title="Git — Push Rejected (remote ahead)",
        regex=re.compile(r"error: failed to push some refs to", re.IGNORECASE),
        explanation=(
            "**The remote has commits that you don't have locally.** Git won't overwrite them.\n\n"
            "**Fix**:\n"
            "```bash\ngit pull --rebase origin <branch>\ngit push\n```\n"
            "Rebase replays your commits on top of the remote ones (cleaner than a merge commit).\n\n"
            "**Gotcha**: Never `git push --force` on a shared branch — it rewrites history for everyone. "
            "Use `--force-with-lease` if you absolutely must."
        ),
    ),
    Pattern(
        title="Git — Branch Behind Remote",
        regex=re.compile(r"Your branch is behind .+ by \d+ commit", re.IGNORECASE),
        explanation=(
            "**Your local branch is missing commits from the remote.**\n\n"
            "**Fix**:\n"
            "```bash\ngit pull origin <branch>           # merge remote changes in\ngit pull --rebase origin <branch>  # rebase (cleaner history)\n```\n\n"
            "**Gotcha**: If you also have local commits, you'll need to merge or rebase. "
            "`git status` tells you exactly how many commits ahead/behind you are."
        ),
    ),
    Pattern(
        title="Git — Detached HEAD",
        regex=re.compile(r"HEAD detached at", re.IGNORECASE),
        explanation=(
            "**You've checked out a specific commit rather than a branch.** "
            "New commits here won't belong to any branch and will eventually be garbage-collected.\n\n"
            "**Fix**: Create a branch from the current position to keep any work:\n"
            "```bash\ngit checkout -b my-new-branch\n```\n"
            "To return to a branch without keeping changes:\n"
            "```bash\ngit checkout main\n```\n\n"
            "**Gotcha**: `git checkout <tag>` also detaches HEAD — "
            "use `git checkout -b <branch> <tag>` if you want to commit from a tag."
        ),
    ),
]


def match_pattern(error_text: str) -> tuple[str, str] | None:
    """Return (title, explanation_markdown) for the first matching pattern, else None."""
    for p in PATTERNS:
        m = p.regex.search(error_text)
        if m:
            try:
                explanation = p.explanation.format(*m.groups())
            except (IndexError, KeyError):
                explanation = p.explanation
            return p.title, explanation
    return None


def list_patterns() -> list[str]:
    """Return the title of every built-in pattern."""
    return [p.title for p in PATTERNS]
