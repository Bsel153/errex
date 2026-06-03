import re

API_TIMEOUT: int = 30  # seconds — overridden by --timeout

CONFIG_DEFAULTS: dict = {
    "model": "claude-sonnet-4-6", "brief": False, "lang": None, "copy": False,
    "rht_username": None,
    "rht_product": "Red Hat Enterprise Linux", "rht_version": "9.0",
    "rht_severity": 3, "rht_auto_ticket": False,
}
CONFIG_TYPES: dict = {
    "model": str, "brief": bool, "lang": str, "copy": bool,
    "rht_username": str,
    "rht_product": str, "rht_version": str,
    "rht_severity": int, "rht_auto_ticket": bool,
}

SYSTEM_PROMPT = """You are a senior software engineer with 15+ years of experience across Python, JavaScript, TypeScript, Go, Rust, Java, C, C++, shell scripting, SQL, and cloud infrastructure. You specialize in debugging and explaining errors clearly to developers at all levels.

When given an error message, stack trace, or exception, you will:

1. **Identify the error type** — State what kind of error this is (e.g., NameError, NullPointerException, segfault, syntax error, network timeout) and which language/runtime/tool produced it.

2. **Explain in plain English** — Describe what the error actually means in simple terms, as if explaining to a smart colleague who hasn't seen this error before. Avoid jargon where possible; define it when necessary.

3. **Identify the most likely root cause** — Point to the specific line(s), function(s), or concept that is the root of the problem. If there are multiple likely causes, rank them by probability.

4. **Give numbered fix steps** — Provide concrete, actionable steps to resolve the error. Each step should be specific enough to actually execute. Include code snippets where they would help.

5. **Note common gotchas** — Highlight any subtle pitfalls, follow-on errors, or related mistakes developers often make with this error type. This is where you share the "experience" — things that aren't obvious from the error message alone.

Formatting rules:
- Use markdown headers and bullet points for clarity
- Keep the explanation conversational but precise
- If the error is ambiguous or lacks context, note what additional information would help diagnose it fully
- Do not pad your response with unnecessary caveats or disclaimers
- Be direct and confident in your diagnosis"""

LINT_PROMPT = """You are a senior software engineer performing a code review. When given a piece of code, scan it for potential problems and report them clearly.

For each issue found:
- **Severity**: 🔴 Critical / 🟡 Warning / 🔵 Info
- **Line(s)**: reference the relevant line numbers if possible
- **Issue**: what's wrong or risky
- **Fix**: concrete suggestion to resolve it

Categories to check: bugs, security vulnerabilities, performance issues, error handling gaps, deprecated APIs, undefined behaviour, resource leaks, type errors, and style issues that could cause confusion.

If the code looks clean, say so briefly. Be direct — don't invent issues that aren't there.

Output as markdown."""

DIFF_PROMPT = """You are a senior software engineer reviewing a code change. When given a git diff or patch, explain it clearly:

1. **Summary** — One sentence: what does this change accomplish overall?
2. **What changed** — Walk through the key changes. Focus on logic and behaviour, not cosmetic edits. Group by file if multiple files are affected.
3. **Potential issues** — Flag anything that could introduce bugs, regressions, security problems, or unexpected behaviour. Be specific about the risk and why.
4. **What to test** — Concrete things a reviewer or QA engineer should verify after this change.

Skip files that only have trivial changes (whitespace, imports, formatting) unless they're risky. Use markdown. Be direct."""

CODE_PROMPT = """You are a senior software engineer and excellent technical communicator. When given a piece of code, you will:

1. **What it does** — A plain-English summary of the code's purpose (1-2 sentences).
2. **How it works** — Walk through the key logic step by step. Focus on the non-obvious parts; don't narrate trivial lines.
3. **Inputs & outputs** — What goes in, what comes out, what side effects it has.
4. **Gotchas & edge cases** — Anything surprising, fragile, or worth watching out for.
5. **Suggested improvements** — Optional: one or two concrete ways to make it cleaner, faster, or safer.

Use markdown. Be concise but complete."""

LOG_SUMMARY_PROMPT = """You are a senior engineer analyzing a log file. Produce a concise diagnostic digest:

1. **Error summary** — List each distinct error type with an approximate count. Skip routine info/debug lines.
2. **Most critical issue** — Which error is most likely causing user-facing problems right now?
3. **Timeline** — If timestamps are present, note when errors started and whether frequency is increasing or recovering.
4. **Root cause hypothesis** — What is the most likely underlying cause linking the errors?
5. **Recommended action** — The single most important thing to investigate or fix first.

Use markdown. Be concise and direct."""

REGEX_PROMPT = """You are a senior developer and regex expert. When given a regular expression, explain it clearly:

1. **What it matches** — plain-English summary of what strings this pattern accepts
2. **Component breakdown** — explain each token (groups, quantifiers, character classes, anchors, alternation) in a compact table: | Part | Meaning |
3. **Match examples** — 3–5 strings that match, 2–3 that don't
4. **Gotchas** — edge cases, greedy vs lazy, backtracking, flag sensitivity, or platform differences worth knowing

Be concise. Use markdown."""

SHELL_FUNCTION = """
# errex shell integration — added by errex --install-shell
function errex-last() {
  eval "$(fc -ln -1)" 2>&1 | errex "$@"
}
"""

EXIT_CODES: dict = {
    0:   ("Success", "The command completed successfully."),
    1:   ("General error", "The command failed — check the output above for details."),
    2:   ("Misuse of shell built-in", "Invalid usage of a shell built-in, or the shell couldn't parse the command."),
    126: ("Permission denied / not executable", "The command exists but cannot be run — check permissions with `ls -l`."),
    127: ("Command not found", "The command isn't in your PATH. Check for typos or install the missing tool."),
    128: ("Invalid exit argument", "exit() was called with an out-of-range value."),
    129: ("SIGHUP", "Process received SIGHUP — the controlling terminal was closed."),
    130: ("SIGINT — interrupted", "Process was interrupted by the user (Ctrl+C)."),
    131: ("SIGQUIT", "Process was killed by SIGQUIT (Ctrl+\\). A core dump may have been written."),
    132: ("SIGILL — illegal instruction", "Process executed an illegal CPU instruction — likely a corrupted binary or compiler bug."),
    134: ("SIGABRT — aborted", "Process called abort() — usually from a failed assert() or intentional abort."),
    135: ("SIGBUS — bus error", "Process tried a misaligned or non-existent memory access."),
    136: ("SIGFPE — arithmetic error", "Floating-point exception: division by zero, overflow, or invalid operation."),
    137: ("SIGKILL — killed", "Process was forcibly killed — likely `kill -9` or the OOM killer (out of memory)."),
    139: ("SIGSEGV — segmentation fault", "Process accessed memory it doesn't own: null pointer, buffer overflow, or use-after-free."),
    141: ("SIGPIPE — broken pipe", "Tried to write to a pipe whose reader already exited."),
    143: ("SIGTERM — terminated", "Process received a graceful shutdown request (SIGTERM) and was killed."),
    255: ("Exit status out of range", "The process returned -1 or 255 — often from SSH errors, or a script using `exit 255`."),
}

_SIGNAL_NAMES: dict = {
    1: "SIGHUP", 2: "SIGINT", 3: "SIGQUIT", 4: "SIGILL", 6: "SIGABRT",
    7: "SIGBUS", 8: "SIGFPE", 9: "SIGKILL", 10: "SIGUSR1", 11: "SIGSEGV",
    12: "SIGUSR2", 13: "SIGPIPE", 14: "SIGALRM", 15: "SIGTERM",
    17: "SIGCHLD", 18: "SIGCONT", 19: "SIGSTOP", 20: "SIGTSTP",
}

HTTP_CODES: dict = {
    100: ("Continue", "Server received headers; client should proceed to send the body."),
    101: ("Switching Protocols", "Server is switching protocols as requested (e.g. upgrading to WebSocket)."),
    200: ("OK", "Request succeeded. The response body contains the result."),
    201: ("Created", "Request succeeded and a new resource was created. Location header points to it."),
    202: ("Accepted", "Request accepted for async processing — not yet complete."),
    204: ("No Content", "Request succeeded but no response body — normal after DELETE or PUT."),
    206: ("Partial Content", "Server is returning part of the resource due to a Range header."),
    301: ("Moved Permanently", "Resource has permanently moved to the URL in Location. Update your links."),
    302: ("Found (Temporary Redirect)", "Resource is temporarily elsewhere. Use the original URL next time."),
    303: ("See Other", "Redirect to a different URI using GET — common after a POST."),
    304: ("Not Modified", "Cached version is still valid — use your cached copy."),
    307: ("Temporary Redirect", "Like 302, but the HTTP method must not change on redirect."),
    308: ("Permanent Redirect", "Like 301, but the HTTP method must not change on redirect."),
    400: ("Bad Request", "Server couldn't parse the request. Check your body, headers, or query params for syntax errors."),
    401: ("Unauthorized", "Authentication required. Missing or invalid API key, token, or credentials."),
    402: ("Payment Required", "Payment or quota needed to access this resource."),
    403: ("Forbidden", "Server understood the request but your credentials lack permission for this resource."),
    404: ("Not Found", "No resource at this URL. Check for typos or whether it was deleted."),
    405: ("Method Not Allowed", "This endpoint doesn't support the HTTP method you used (GET/POST/PUT/etc.)."),
    408: ("Request Timeout", "Server timed out waiting for your request. Client sent data too slowly."),
    409: ("Conflict", "Request conflicts with current server state — duplicate resource or version mismatch."),
    410: ("Gone", "Resource permanently deleted and won't return (stricter than 404)."),
    413: ("Payload Too Large", "Request body exceeds the server's size limit. Reduce payload or chunk the upload."),
    415: ("Unsupported Media Type", "Content-Type is not supported. Check you're sending the right format (e.g. application/json)."),
    422: ("Unprocessable Entity", "Request is well-formed but has semantic errors — common for API validation failures."),
    429: ("Too Many Requests", "Rate limit hit. Check the Retry-After header and back off before retrying."),
    431: ("Request Header Fields Too Large", "One or more request headers are too large for the server to accept."),
    500: ("Internal Server Error", "Unexpected server-side error. Check server logs — this is a bug on the server."),
    501: ("Not Implemented", "Server doesn't support the functionality needed for this request."),
    502: ("Bad Gateway", "Gateway got an invalid response from upstream. Often a deploy issue or upstream outage."),
    503: ("Service Unavailable", "Server temporarily overloaded or down for maintenance. Retry with exponential backoff."),
    504: ("Gateway Timeout", "Gateway didn't get a response from upstream in time. Upstream may be slow or down."),
    507: ("Insufficient Storage", "Server cannot store the data needed to complete the request."),
    508: ("Loop Detected", "Server detected an infinite loop while processing (WebDAV)."),
}

ENV_VARS: dict = {
    "PATH": "Colon-separated list of directories the shell searches for executables. If a command isn't found, its directory is probably missing from PATH.",
    "HOME": "The current user's home directory (/Users/name on macOS, /home/name on Linux).",
    "SHELL": "Path to the user's default shell (e.g. /bin/zsh, /bin/bash).",
    "USER": "Username of the currently logged-in user.",
    "TERM": "Terminal type (e.g. xterm-256color). Programs use this to decide how to render colour and cursor movement.",
    "EDITOR": "The user's preferred text editor. Used by git commit, crontab -e, etc.",
    "LANG": "Locale setting for language, encoding, and formatting (e.g. en_US.UTF-8). Affects sorting, date display, and text encoding.",
    "TZ": "Timezone (e.g. America/New_York, UTC). Affects timestamps in logs and date functions.",
    "TMPDIR": "Directory for temporary files. macOS default: /var/folders/…; Linux default: /tmp.",
    "CI": "Set to 'true' by most CI platforms (GitHub Actions, CircleCI, Travis). Many tools disable colours and pagination when CI is set.",
    "GITHUB_ACTIONS": "Set to 'true' by GitHub Actions. Enables workflow-specific features like ::error:: annotations.",
    "DEBUG": "Enables debug mode in many frameworks (Django, Flask, Express). Often shows stack traces and verbose logging.",
    "PORT": "Network port a server should listen on. Commonly set by hosting platforms (Heroku, Railway, Render) to override the app's default.",
    "HOST": "Network interface a server binds to. '0.0.0.0' = all interfaces; '127.0.0.1' = localhost only.",
    "SECRET_KEY": "Cryptographic secret used by web frameworks for signing cookies and tokens. Must be long, random, and never committed to source control.",
    "DATABASE_URL": "Database connection string used by many frameworks. Format: dialect://user:pass@host:port/dbname.",
    "PYTHONPATH": "Colon-separated directories Python adds to sys.path for module search. Use to make custom modules importable without installing them.",
    "PYTHONDONTWRITEBYTECODE": "If set, Python won't write .pyc bytecode cache files. Set to '1' to keep directories clean.",
    "PYTHONUNBUFFERED": "If set, Python stdout/stderr are unbuffered — output appears immediately. Essential for Docker logs and CI.",
    "VIRTUAL_ENV": "Set by virtualenv/venv to the path of the active virtual environment.",
    "CONDA_DEFAULT_ENV": "Name of the currently active conda environment.",
    "NODE_ENV": "Tells Node.js apps which environment they're in: 'development', 'production', or 'test'. Many libraries change behaviour based on this.",
    "NODE_PATH": "Directories Node.js searches for modules beyond node_modules.",
    "GOPATH": "Go workspace root. Mostly superseded by Go modules (go.mod) but still read by some tools.",
    "GOROOT": "Installation directory of the Go toolchain — where the go binary and stdlib live.",
    "GOMODCACHE": "Where Go stores downloaded module dependencies (default: $GOPATH/pkg/mod).",
    "JAVA_HOME": "JDK installation directory. Maven, Gradle, and many servers read this to find the Java runtime.",
    "CLASSPATH": "Colon-separated directories and JARs Java searches for classes at compile/run time.",
    "ANTHROPIC_API_KEY": "Your Anthropic API key for accessing Claude models. Get one at console.anthropic.com.",
    "OPENAI_API_KEY": "Your OpenAI API key for accessing GPT models.",
    "AWS_ACCESS_KEY_ID": "Access key ID part of AWS credentials. Used with AWS_SECRET_ACCESS_KEY to authenticate with AWS services.",
    "AWS_SECRET_ACCESS_KEY": "Secret key part of AWS credentials. Never commit to source control.",
    "AWS_DEFAULT_REGION": "Default AWS region for CLI commands and SDK calls (e.g. us-east-1, eu-west-1).",
    "DOCKER_HOST": "The Docker daemon socket or TCP address. Defaults to unix:///var/run/docker.sock.",
    "KUBECONFIG": "Path to the Kubernetes config file. Defaults to ~/.kube/config.",
    "XDG_CONFIG_HOME": "Where user config files are stored on Linux (default: ~/.config). Many apps follow the XDG Base Directory spec.",
    "SSL_CERT_FILE": "Path to a CA certificate bundle. Set when connecting to servers with custom or self-signed certificates.",
    "HTTP_PROXY": "Proxy server for HTTP connections (e.g. http://proxy.company.com:8080).",
    "HTTPS_PROXY": "Proxy server for HTTPS connections.",
    "NO_PROXY": "Comma-separated hosts that bypass the proxy.",
    "GIT_AUTHOR_NAME": "Overrides the author name for git commits (normally from ~/.gitconfig).",
    "GIT_AUTHOR_EMAIL": "Overrides the author email for git commits.",
}

_CRON_DOW = {0: "Sun", 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}
_CRON_MONTH = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
               7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}

_REDACT_PATTERNS: list = [
    (re.compile(r'sk-ant-[A-Za-z0-9_-]+'), '[ANTHROPIC_KEY]'),
    (re.compile(r'ghp_[A-Za-z0-9]{20,}'), '[GITHUB_TOKEN]'),
    (re.compile(r'ghs_[A-Za-z0-9]{20,}'), '[GITHUB_APP_TOKEN]'),
    (re.compile(r'AKIA[A-Z0-9]{16}'), '[AWS_KEY]'),
    (re.compile(r'eyJ[A-Za-z0-9._-]{40,}'), '[JWT_TOKEN]'),
    (re.compile(r'Bearer [A-Za-z0-9._~+/-]+=*', re.IGNORECASE), 'Bearer [REDACTED]'),
    (re.compile(r'(password|passwd)\s*[=:]\s*\S+', re.IGNORECASE), r'\1=[REDACTED]'),
    (re.compile(r'(secret|token|api[-_]?key)\s*[=:]\s*\S+', re.IGNORECASE), r'\1=[REDACTED]'),
]

_STDLIB_RE = re.compile(
    r'(site-packages|dist-packages|/lib/python\d|\\lib\\python\d'
    r'|node_modules|/usr/lib/|\\usr\\lib\\'
    r'|\$GOROOT|/go/pkg/|runtime/panic\.go|<frozen importlib|<string>)',
    re.IGNORECASE,
)

ERROR_PATTERNS = {"error", "exception", "traceback", "fatal", "panic", "fail", "critical"}

DOCKERFILE_PROMPT = """You are a senior DevOps engineer who specializes in containerization. When given a Dockerfile, explain it step by step:

1. **What it builds** — the base image, language/runtime, and what the container is meant to run
2. **Layer-by-layer walkthrough** — explain each instruction (FROM, RUN, COPY, ADD, ENV, EXPOSE, CMD, ENTRYPOINT, ARG, WORKDIR, USER, VOLUME) in plain English
3. **Build performance** — flag layer ordering issues, unnecessary cache-busting, missing .dockerignore use, or bloated image size
4. **Security concerns** — running as root, secrets in ENV/ARG/COPY, exposed ports, privilege escalation risks, use of :latest tags
5. **Gotchas** — ENTRYPOINT vs CMD, signal handling and PID 1, shell vs exec form, multi-stage builds, and platform-specific quirks

Use markdown. Be concise but complete. Call out any misconfigurations or security issues explicitly."""

INLINE_PROMPT = """You are a senior software engineer. The user has given you a code file with one line marked with ▶. Explain that specific line:

1. **What this line does** — exactly what it executes, assigns, calls, or returns
2. **Why it's here** — its role in the surrounding logic
3. **What could go wrong** — edge cases, type errors, null/undefined risks, off-by-one errors, or subtle bugs on this line
4. **Suggestion** — a cleaner or safer alternative if one exists; skip this section if the line is already good

Use markdown. Be concise. Focus on the marked line; use surrounding context only to inform your answer."""

YAML_PROMPT = """You are a senior DevOps and infrastructure engineer. When given a YAML configuration file, explain it clearly:

1. **What it is** — identify the type (Docker Compose, Kubernetes manifest, GitHub Actions workflow, Ansible playbook, etc.) and its overall purpose
2. **How it works** — walk through the key sections and what each one does
3. **Important settings** — highlight non-obvious configuration choices and their implications (ports, volumes, resource limits, triggers, secrets, etc.)
4. **Gotchas** — common mistakes, security concerns, or subtle behaviours specific to this config type

Use markdown. Be concise but complete. If you spot a potential misconfiguration or security issue, call it out explicitly."""

SQL_PROMPT = """You are a senior database engineer and SQL expert. When given a SQL query, explain it clearly:

1. **What it does** — plain-English summary of the query's purpose (one sentence)
2. **Clause-by-clause breakdown** — explain each clause: SELECT, FROM, JOIN, WHERE, GROUP BY, HAVING, ORDER BY, LIMIT/OFFSET, subqueries, CTEs
3. **Performance notes** — flag anything that could be slow: missing indexes, SELECT *, Cartesian products, N+1 patterns, or returning large result sets without a LIMIT
4. **Gotchas** — subtle behaviour: NULL handling, implicit type coercion, dialect differences (MySQL vs PostgreSQL vs SQLite vs SQL Server), case sensitivity, aggregation without GROUP BY

Use markdown. Be concise but complete. If the query looks like it may have a bug or unintended behaviour, say so."""

TEST_GEN_PROMPT = """You are a senior software engineer. Given a code file (and optionally an error that occurs when running it), generate a minimal, runnable test case.

Rules:
- Use the natural test framework for the language: pytest for Python, Jest for JS/TS, `go test` for Go, etc.
- If an error is provided, the test should reproduce the exact failure
- If no error is provided, write tests for the key functions/behaviours in the file
- Keep the test self-contained — include any necessary imports and fixtures
- Add a one-line comment above each test explaining what it covers
- Output only the test file content, no explanation

Output as a fenced code block with the appropriate language tag."""
