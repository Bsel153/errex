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
    # ── Rust ─────────────────────────────────────────────────────────────────
    Pattern(
        title="Rust — E0308 (mismatched types)",
        regex=re.compile(r"error\[E0308\]: mismatched types", re.IGNORECASE),
        explanation=(
            "**Type mismatch: Rust expected one type but found another.**\n\n"
            "**Fix**: Check the types on both sides of the assignment or function call. "
            "Use an explicit cast or conversion:\n"
            "```rust\nlet x: i64 = my_i32 as i64;     // cast\nlet x: String = my_str.into();  // From/Into trait\n```\n\n"
            "**Gotcha**: Rust **never** implicitly converts numeric types — "
            "even `i32` to `i64` requires an explicit `as` cast or `.into()`."
        ),
    ),
    Pattern(
        title="Rust — E0382 (use of moved value)",
        regex=re.compile(r"error\[E0382\]: (borrow of|use of) moved value", re.IGNORECASE),
        explanation=(
            "**Ownership was moved — you can't use the value again after it was moved.**\n\n"
            "**Fix**: Clone before moving if you need to keep using the original:\n"
            "```rust\nlet s2 = s1.clone();\nsome_fn(s1);   // s1 is moved here\nprintln!(\"{}\", s2);  // s2 is a clone, still valid\n```\n"
            "Or restructure to avoid the move entirely.\n\n"
            "**Gotcha**: This is Rust's ownership system at work — "
            "understand the difference between a *move* and a *borrow* (`&T`)."
        ),
    ),
    Pattern(
        title="Rust — E0106 (missing lifetime)",
        regex=re.compile(r"error\[E0106\]: missing lifetime specifier", re.IGNORECASE),
        explanation=(
            "**A reference inside a struct or function signature needs a lifetime annotation.**\n\n"
            "**Fix**: Add a `'a` lifetime parameter:\n"
            "```rust\nstruct Foo<'a> {\n    data: &'a str,\n}\n```\n\n"
            "**Gotcha**: Start with `'_` (anonymous lifetime) and let the compiler guide you — "
            "it often suggests the exact fix needed."
        ),
    ),
    Pattern(
        title="Rust — E0502 (borrow conflict)",
        regex=re.compile(r"error\[E0502\]: cannot borrow .+ as mutable because it is also borrowed as immutable", re.IGNORECASE),
        explanation=(
            "**You can't have a mutable borrow and an immutable borrow of the same value at the same time.**\n\n"
            "**Fix**: End the immutable borrow before mutating:\n"
            "```rust\nlet r = &v[0];         // immutable borrow\nprintln!(\"{}\", r);    // last use of r — borrow ends here\nv.push(4);            // mutable borrow OK now\n```\n\n"
            "**Gotcha**: The borrow checker tracks lexical scopes — "
            "restructure code so immutable and mutable borrows don't overlap."
        ),
    ),
    Pattern(
        title="Rust — E0277 (trait not implemented)",
        regex=re.compile(r"error\[E0277\]: .+ is not implemented for", re.IGNORECASE),
        explanation=(
            "**A type doesn't implement a trait that's required.**\n\n"
            "**Fix**: Derive the trait if possible:\n"
            "```rust\n#[derive(Debug, Clone, PartialEq)]\nstruct MyStruct { ... }\n```\n"
            "Or implement it manually:\n"
            "```rust\nimpl std::fmt::Display for MyStruct { ... }\n```\n\n"
            "**Gotcha**: Some traits (like `serde::Serialize`) require a feature flag — "
            "make sure the right crate and feature are in your `Cargo.toml`."
        ),
    ),
    Pattern(
        title="Rust — E0369 (operator not supported)",
        regex=re.compile(r"error\[E0369\]: binary operation .+ cannot be applied to type", re.IGNORECASE),
        explanation=(
            "**This type doesn't implement the operator's underlying trait.**\n\n"
            "**Fix**: Derive or implement the relevant trait:\n"
            "```rust\n#[derive(PartialEq, PartialOrd)]  // for == < > etc.\nstruct MyNum(f64);\n\nuse std::ops::Add;\nimpl Add for MyNum { ... }         // for +\n```\n\n"
            "**Gotcha**: Rust operators are just syntactic sugar for traits — "
            "`a + b` calls `Add::add(a, b)`."
        ),
    ),
    Pattern(
        title="Rust — Thread Panicked",
        regex=re.compile(r"thread '(?:main|.+)' panicked at", re.IGNORECASE),
        explanation=(
            "**The Rust program panicked** — an unrecoverable error occurred at runtime.\n\n"
            "Common causes: index out of bounds, `unwrap()` on `None`/`Err`, explicit `panic!()`.\n\n"
            "**Fix**: Replace panicking code with proper error handling:\n"
            "```rust\n// Instead of: vec[idx]\nif let Some(v) = vec.get(idx) { ... }\n\n// Instead of: result.unwrap()\nresult?   // propagate error with the ? operator\n\n// Instead of: option.unwrap()\nif let Some(v) = option { ... }\n```\n\n"
            "**Gotcha**: `unwrap()` and `expect()` panic on `None`/`Err` — "
            "use `?` operator or `match`/`if let` for proper error handling."
        ),
    ),
    # ── Java ─────────────────────────────────────────────────────────────────
    Pattern(
        title="Java — NullPointerException",
        regex=re.compile(r"java\.lang\.NullPointerException", re.IGNORECASE),
        explanation=(
            "**Accessing a method or field on a `null` reference.**\n\n"
            "**Fix**: Add a null check before the access:\n"
            "```java\nif (obj != null) {\n    obj.doSomething();\n}\n// or use Optional:\nOptional.ofNullable(obj).ifPresent(o -> o.doSomething());\n```\n\n"
            "**Gotcha**: Java 14+ NPEs include helpful messages like "
            "\"Cannot invoke X because Y is null\" — read them carefully to pinpoint the null."
        ),
    ),
    Pattern(
        title="Java — ClassCastException",
        regex=re.compile(r"java\.lang\.ClassCastException", re.IGNORECASE),
        explanation=(
            "**Trying to cast an object to a type it isn't.**\n\n"
            "**Fix**: Check the type with `instanceof` before casting:\n"
            "```java\nif (obj instanceof String s) {  // Java 16+ pattern matching\n    System.out.println(s.length());\n}\n```\n\n"
            "**Gotcha**: Generics use type erasure at runtime — "
            "`List<String>` and `List<Integer>` are both just `List` at runtime, "
            "so a bad cast can slip through compile time."
        ),
    ),
    Pattern(
        title="Java — StackOverflowError",
        regex=re.compile(r"java\.lang\.StackOverflowError", re.IGNORECASE),
        explanation=(
            "**Infinite recursion — the call stack exceeded its limit.**\n\n"
            "**Fix**: Add a base case to your recursive method:\n"
            "```java\nint factorial(int n) {\n    if (n <= 1) return 1;  // base case\n    return n * factorial(n - 1);\n}\n```\n\n"
            "**Gotcha**: The default Java stack is 512KB–1MB. You can increase it with `-Xss` "
            "but that's rarely the right fix — fix the recursion instead."
        ),
    ),
    Pattern(
        title="Java — ClassNotFoundException",
        regex=re.compile(r"java\.lang\.ClassNotFoundException: (.+)", re.IGNORECASE),
        explanation=(
            "**Class `{0}` was not found on the classpath.**\n\n"
            "**Fix**: Check your dependencies:\n"
            "```xml\n<!-- Maven pom.xml -->\n<dependency>\n    <groupId>...</groupId>\n    <artifactId>...</artifactId>\n</dependency>\n```\n"
            "Or for Gradle: add the dependency to `build.gradle`.\n\n"
            "**Gotcha**: Common when a JAR is missing, the fully-qualified class name has a typo, "
            "or you're loading a class dynamically with `Class.forName()`."
        ),
    ),
    Pattern(
        title="Java — OutOfMemoryError (heap)",
        regex=re.compile(r"java\.lang\.OutOfMemoryError: Java heap space", re.IGNORECASE),
        explanation=(
            "**The JVM heap is full.**\n\n"
            "**Fix**: Increase the heap size:\n"
            "```bash\njava -Xmx512m -jar app.jar   # set max heap to 512MB\n```\n"
            "But first, find and fix any memory leaks.\n\n"
            "**Gotcha**: Profile with VisualVM or JProfiler to find what's consuming memory — "
            "simply increasing `-Xmx` without fixing leaks is only a temporary fix."
        ),
    ),
    Pattern(
        title="Java — Uncaught Exception",
        regex=re.compile(r"Exception in thread \"(?:main|.+)\" java\.lang\.(\w+Exception)", re.IGNORECASE),
        explanation=(
            "**An unhandled `{0}` exception terminated the thread.**\n\n"
            "**Fix**: Wrap the call in a try/catch and handle it appropriately:\n"
            "```java\ntry {\n    riskyOperation();\n} catch ({0} e) {{\n    // log or handle the exception\n    e.printStackTrace();\n}}\n```\n\n"
            "**Gotcha**: Catching `Exception` is too broad — "
            "catch the most specific type you can handle to avoid hiding bugs."
        ),
    ),
    # ── Go ───────────────────────────────────────────────────────────────────
    Pattern(
        title="Go — Index Out of Range",
        regex=re.compile(r"panic: runtime error: index out of range \[(\d+)\] with length (\d+)", re.IGNORECASE),
        explanation=(
            "**Accessing index {0} in a slice/array of length {1}.**\n\n"
            "**Fix**: Check the length before accessing:\n"
            "```go\nif len(slice) > {0} {{\n    val := slice[{0}]\n}}\n```\n\n"
            "**Gotcha**: Go doesn't panic on a nil map *read* (returns the zero value), "
            "but it *does* panic on a nil map *write* — always initialize maps with `make(map[K]V)`."
        ),
    ),
    Pattern(
        title="Go — Nil Pointer Dereference",
        regex=re.compile(r"panic: runtime error: invalid memory address or nil pointer dereference", re.IGNORECASE),
        explanation=(
            "**Dereferencing a nil pointer.**\n\n"
            "**Fix**: Check the pointer for nil before dereferencing:\n"
            "```go\nif p != nil {\n    fmt.Println(p.Field)\n}\n```\n\n"
            "**Gotcha**: Interface values can be non-nil but hold a nil concrete pointer — "
            "use `reflect` to detect this edge case, or design APIs to avoid nil interface values."
        ),
    ),
    Pattern(
        title="Go — Type Assertion Failed",
        regex=re.compile(r"panic: interface conversion: interface \{\} is (.+), not (.+)", re.IGNORECASE),
        explanation=(
            "**Type assertion `.(T)` failed** — the interface holds a `{0}`, not a `{1}`.\n\n"
            "**Fix**: Always use the two-value form for type assertions:\n"
            "```go\nv, ok := x.({1})\nif ok {{\n    // safe to use v as {1}\n}}\n```\n\n"
            "**Gotcha**: The single-value form `v := x.({1})` panics if the assertion fails — "
            "never use it on an interface that might hold a different type."
        ),
    ),
    Pattern(
        title="Go — Missing Module",
        regex=re.compile(r"go: .*: no required module provides package (.+)", re.IGNORECASE),
        explanation=(
            "**Package `{0}` is not in `go.mod`.**\n\n"
            "**Fix**:\n"
            "```bash\ngo get {0}\ngo mod tidy\n```\n\n"
            "**Gotcha**: If you're using a Go workspace (`go.work`), "
            "also run `go work sync` to keep module dependencies in sync."
        ),
    ),
    # ── Python (additional) ──────────────────────────────────────────────────
    Pattern(
        title="Python — RuntimeError (dict changed during iteration)",
        regex=re.compile(r"RuntimeError: dictionary changed size during iteration", re.IGNORECASE),
        explanation=(
            "**A dictionary was modified while iterating over it.**\n\n"
            "**Fix**: Iterate over a copy of the keys or items:\n"
            "```python\nfor k in list(d.keys()):\n    if should_remove(k):\n        del d[k]\n# or\nfor k, v in list(d.items()):\n    ...\n```\n\n"
            "**Gotcha**: The same issue occurs with lists — if you remove items from a list "
            "while iterating, iterate `list(original)` instead."
        ),
    ),
    Pattern(
        title="Python — UnicodeDecodeError",
        regex=re.compile(r"UnicodeDecodeError: '([^']+)' codec can't decode", re.IGNORECASE),
        explanation=(
            "**Bytes couldn't be decoded using the `{0}` codec.**\n\n"
            "**Fix**: Specify the correct encoding when opening files:\n"
            "```python\nwith open(path, encoding='utf-8') as f:\n    ...\n# or be lenient:\nwith open(path, encoding='utf-8', errors='replace') as f:\n    ...\n```\n\n"
            "**Gotcha**: Files from Windows often use `cp1252` instead of `utf-8`. "
            "Use the `chardet` library (`pip install chardet`) to auto-detect encoding."
        ),
    ),
    Pattern(
        title="Python — StopIteration",
        regex=re.compile(r"\bStopIteration\b", re.IGNORECASE),
        explanation=(
            "**`next()` was called on an exhausted iterator.**\n\n"
            "**Fix**: Use `next()` with a default value:\n"
            "```python\nvalue = next(iterator, None)  # returns None instead of raising\n```\n"
            "Or use a `for` loop, which handles `StopIteration` automatically.\n\n"
            "**Gotcha**: In Python 3.7+, raising `StopIteration` inside a generator "
            "causes it to silently return — use `return` instead."
        ),
    ),
    Pattern(
        title="Python — CalledProcessError",
        regex=re.compile(r"subprocess\.CalledProcessError: Command '(.+)' returned non-zero exit status (\d+)", re.IGNORECASE),
        explanation=(
            "**Command `{0}` failed with exit code {1}.**\n\n"
            "**Fix**: Inspect stderr to see what went wrong:\n"
            "```python\nresult = subprocess.run(\n    cmd, capture_output=True, text=True, check=False\n)\nprint(result.stderr)\n```\n\n"
            "**Gotcha**: Use `capture_output=True` (Python 3.7+) to capture both stdout and stderr — "
            "without it you won't see the error output."
        ),
    ),
    Pattern(
        title="Python — SSL Certificate Error",
        regex=re.compile(r"ssl\.SSLCertVerificationError|certificate verify failed", re.IGNORECASE),
        explanation=(
            "**TLS certificate verification failed.**\n\n"
            "**Fix**:\n"
            "```bash\npip install --upgrade certifi\n```\n"
            "On macOS, also run:\n"
            "```bash\n/Applications/Python*/Install\\ Certificates.command\n```\n\n"
            "**Gotcha**: Never use `verify=False` in production — "
            "it disables HTTPS security entirely and exposes you to man-in-the-middle attacks."
        ),
    ),
    Pattern(
        title="Python — OverflowError",
        regex=re.compile(r"OverflowError: Python int too large to convert to C (long|int)", re.IGNORECASE),
        explanation=(
            "**A Python integer is too large for the C `{0}` type.**\n\n"
            "**Fix**: Use NumPy's 64-bit integers or restructure to avoid the conversion:\n"
            "```python\nimport numpy as np\nvalue = np.int64(large_number)\n```\n\n"
            "**Gotcha**: Python integers are unbounded, but C types have fixed sizes — "
            "this error is common when interfacing with C extensions or system calls."
        ),
    ),
    # ── Docker / containers ──────────────────────────────────────────────────
    Pattern(
        title="Docker — COPY failed (file not found)",
        regex=re.compile(r"COPY failed: file not found in build context or excluded by \.dockerignore: (.+)", re.IGNORECASE),
        explanation=(
            "**The file/directory `{0}` doesn't exist in the Docker build context.**\n\n"
            "**Fix**:\n"
            "1. Check the path is relative to the directory you pass to `docker build`\n"
            "2. Check your `.dockerignore` — the file may be excluded\n"
            "3. Verify the file actually exists: `ls -la <path>`\n\n"
            "**Gotcha**: The build context is the directory you pass to `docker build .` — "
            "not the directory where the Dockerfile lives."
        ),
    ),
    Pattern(
        title="Docker — Daemon Error",
        regex=re.compile(r"Error response from daemon: .*(no space left|no such file or directory|manifest unknown|pull access denied)", re.IGNORECASE),
        explanation=(
            "**Docker daemon reported an error.**\n\n"
            "**Fix** (depends on the message):\n"
            "- **no space left**: `docker system prune` to free disk space\n"
            "- **no such file or directory**: check image name and tag spelling\n"
            "- **manifest unknown**: the tag doesn't exist — check the registry for available tags\n"
            "- **pull access denied**: run `docker login` for private registries\n\n"
            "**Gotcha**: `manifest unknown` often means a typo in the tag name — "
            "check the registry (Docker Hub, ECR, etc.) for the exact available tags."
        ),
    ),
    Pattern(
        title="Docker — Exec Format Error",
        regex=re.compile(r"standard_init_linux\.go:\d+: exec user process caused: exec format error", re.IGNORECASE),
        explanation=(
            "**The binary inside the container was built for a different CPU architecture.**\n\n"
            "**Fix**: Build for the target platform explicitly:\n"
            "```bash\ndocker buildx build --platform linux/amd64 -t myimage .\n```\n\n"
            "**Gotcha**: Apple Silicon Macs build `arm64` images by default — "
            "these won't run on `x86_64` hosts (like most cloud VMs) unless you specify `--platform linux/amd64`."
        ),
    ),
    # ── pip / npm ─────────────────────────────────────────────────────────────
    Pattern(
        title="pip — Dependency Resolution Failed",
        regex=re.compile(r"ERROR: ResolutionImpossible", re.IGNORECASE),
        explanation=(
            "**pip can't find a set of package versions that satisfies all constraints.**\n\n"
            "**Fix**:\n"
            "```bash\npip install --upgrade pip   # ensure pip is up to date\n# Use a fresh virtualenv:\npython -m venv .venv && source .venv/bin/activate\n```\n"
            "Consider using `pip-tools` or `poetry` for better dependency management.\n\n"
            "**Gotcha**: Use `pip show <package>` to see which packages are causing the constraint conflict — "
            "look for overlapping version requirements."
        ),
    ),
    Pattern(
        title="pip — Python Version Mismatch",
        regex=re.compile(r"ERROR: Package '([^']+)' requires a different Python", re.IGNORECASE),
        explanation=(
            "**Package `{0}` doesn't support your current Python version.**\n\n"
            "**Fix**:\n"
            "1. Check the package's supported Python versions on PyPI\n"
            "2. Upgrade Python to a supported version, or pin to an older package version\n\n"
            "**Gotcha**: Run `python --version` and `pip --version` to confirm which Python pip is using — "
            "you may have multiple Python installations."
        ),
    ),
    Pattern(
        title="npm — Peer Dependency Conflict",
        regex=re.compile(r"npm warn peer dep missing|npm error peer dep|Could not resolve dependency", re.IGNORECASE),
        explanation=(
            "**A package requires a peer dependency version you don't have installed.**\n\n"
            "**Fix**: Install the required peer dependency:\n"
            "```bash\nnpm install <peer-package>@<required-version>\n```\n"
            "Check what version is needed:\n"
            "```bash\nnpm info <package> peerDependencies\n```\n\n"
            "**Gotcha**: npm 7+ installs peer deps automatically but fails on version conflicts. "
            "Use `--legacy-peer-deps` as a last resort (it ignores peer dep checks)."
        ),
    ),
    # ── Python requests ───────────────────────────────────────────────────────
    Pattern(
        title="Python requests — ConnectionError",
        regex=re.compile(r"requests\.exceptions\.ConnectionError", re.IGNORECASE),
        explanation=(
            "**Network is unreachable or DNS lookup failed.**\n\n"
            "**Fix**:\n"
            "1. Check network connectivity\n"
            "2. Verify the URL hostname is correct\n"
            "3. Test with curl first: `curl -v <url>`\n\n"
            "**Gotcha**: Firewalls and VPNs can silently block connections — "
            "a successful `curl` doesn't guarantee your Python process has the same network access "
            "(e.g. if it's running in a container or different network namespace)."
        ),
    ),
    Pattern(
        title="Python requests — Timeout",
        regex=re.compile(r"requests\.exceptions\.Timeout|ReadTimeout|ConnectTimeout", re.IGNORECASE),
        explanation=(
            "**The HTTP request took longer than the timeout.**\n\n"
            "**Fix**: Set an explicit timeout and implement retry with backoff:\n"
            "```python\nimport requests\nfrom urllib3.util.retry import Retry\nfrom requests.adapters import HTTPAdapter\n\nsession = requests.Session()\nretry = Retry(total=3, backoff_factor=1)\nsession.mount('https://', HTTPAdapter(max_retries=retry))\nresponse = session.get(url, timeout=30)\n```\n\n"
            "**Gotcha**: The default timeout is `None` (wait forever) — "
            "always set an explicit timeout to prevent your program hanging indefinitely."
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
