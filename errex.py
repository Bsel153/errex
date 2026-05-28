"""
errex — Error Explainer
======================
Paste or pipe an error message and get a clear, plain-English explanation.

Usage:
  errex.py                    # interactive: paste your error, then Ctrl+D (Mac/Linux) or Ctrl+Z (Windows)
  errex.py traceback.txt      # read error from a file
  cat error.log | errex.py    # pipe error via stdin
  errex.py < error.log        # redirect file to stdin

Requirements: pip install anthropic
Set ANTHROPIC_API_KEY in your environment.
"""

import sys
import os
import argparse
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


def explain_error(error_text: str, model: str, brief: bool = False) -> None:
    """Stream an explanation of the error from Claude."""
    client = anthropic.Anthropic()

    print("\n" + "─" * 60)
    print("  errex — Error Analysis")
    print("─" * 60 + "\n")

    if brief:
        prompt = f"In one short paragraph, tell me: what this error is, the most likely cause, and how to fix it.\n\n```\n{error_text}\n```"
    else:
        prompt = f"Please explain this error:\n\n```\n{error_text}\n```"

    with client.messages.stream(
        model=model,
        max_tokens=2048 if not brief else 256,
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
            print(text, end="", flush=True)

    print("\n\n" + "─" * 60 + "\n")


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
    args = parser.parse_args()

    error_text = get_error_input(args.file)

    if not error_text:
        parser.print_usage(sys.stderr)
        sys.exit(1)

    explain_error(error_text, args.model, args.brief)


if __name__ == "__main__":
    main()
