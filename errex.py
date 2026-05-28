"""
errex — Error Explainer
======================
Paste or pipe an error message and get a clear, plain-English explanation.

Usage:
  errex                       # interactive: paste your error, then Ctrl+D (Mac/Linux) or Ctrl+Z (Windows)
  errex traceback.txt         # read error from a file
  cat error.log | errex       # pipe error via stdin
  errex < error.log           # redirect file to stdin

Requirements: pip install anthropic
Set ANTHROPIC_API_KEY in your environment.
"""

import sys
import os
import argparse
import json
import platform
import subprocess
from datetime import datetime
import anthropic

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

HISTORY_FILE = os.path.expanduser("~/.errex_history")


def get_error_input(file: str | None) -> str:
    """Read error input from a file argument, piped stdin, or interactive paste."""
    if file:
        if not os.path.exists(file):
            print(f"errex: file not found: {file}", file=sys.stderr)
            sys.exit(1)
        with open(file, "r", encoding="utf-8", errors="replace") as f:
            return f.read().strip()

    if not sys.stdin.isatty():
        return sys.stdin.read().strip()

    print("Paste your error below. Press Ctrl+D (Mac/Linux) or Ctrl+Z+Enter (Windows) when done:\n")
    lines = []
    try:
        while True:
            line = input()
            lines.append(line)
    except EOFError:
        pass
    return "\n".join(lines).strip()


def copy_to_clipboard(text: str) -> None:
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["pbcopy"], input=text.encode(), check=True)
        elif system == "Linux":
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
        elif system == "Windows":
            subprocess.run(["clip"], input=text.encode(), check=True)
        print("(copied to clipboard)", file=sys.stderr)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("errex: could not copy to clipboard", file=sys.stderr)


def save_history(error_text: str, explanation: str, model: str, brief: bool) -> None:
    entry = {
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "brief": brief,
        "error": error_text[:200],
        "explanation": explanation,
    }
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def explain_error(
    error_text: str,
    model: str,
    brief: bool = False,
    json_output: bool = False,
    lang: str | None = None,
    copy: bool = False,
) -> None:
    """Stream an explanation of the error from Claude."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("errex: ANTHROPIC_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic()
    lang_hint = f" (language: {lang})" if lang else ""

    if json_output:
        prompt = (
            f"Explain this error{lang_hint} as JSON with keys: error_type, language, "
            f"explanation, root_cause, fix_steps (array), gotchas (array). "
            f"Return only valid JSON, no markdown fences.\n\n```\n{error_text}\n```"
        )
    elif brief:
        prompt = f"In one short paragraph, tell me: what this error{lang_hint} is, the most likely cause, and how to fix it.\n\n```\n{error_text}\n```"
    else:
        prompt = f"Please explain this error{lang_hint}:\n\n```\n{error_text}\n```"

    if not json_output:
        print("\n" + "─" * 60)
        print("  errex — Error Analysis")
        print("─" * 60 + "\n")

    collected = []

    try:
        with client.messages.stream(
            model=model,
            max_tokens=256 if brief else 2048,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                if not json_output:
                    print(text, end="", flush=True)
                collected.append(text)
    except anthropic.APIError as e:
        print(f"\nerrex: API error — {e}", file=sys.stderr)
        sys.exit(2)

    full_response = "".join(collected)

    if json_output:
        try:
            parsed = json.loads(full_response)
            print(json.dumps(parsed, indent=2))
        except json.JSONDecodeError:
            print(full_response)
    else:
        print("\n\n" + "─" * 60 + "\n")

    save_history(error_text, full_response, model, brief)

    if copy:
        copy_to_clipboard(full_response)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="errex",
        description="Paste or pipe an error message and get a plain-English explanation.",
    )
    parser.add_argument("file", nargs="?", help="path to a file containing the error")
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="Claude model to use (default: claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--brief",
        action="store_true",
        help="one-paragraph summary instead of full analysis",
    )
    parser.add_argument(
        "--lang",
        help="language or runtime hint when ambiguous (e.g. rust, go, java)",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="copy the explanation to the clipboard after printing",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="output structured JSON (error_type, root_cause, fix_steps, gotchas)",
    )
    args = parser.parse_args()

    error_text = get_error_input(args.file)

    if not error_text:
        parser.print_usage(sys.stderr)
        sys.exit(1)

    explain_error(
        error_text,
        model=args.model,
        brief=args.brief,
        json_output=args.json_output,
        lang=args.lang,
        copy=args.copy,
    )


if __name__ == "__main__":
    main()
