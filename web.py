"""
errex web UI — run with: python web.py
Then open http://localhost:7337 in your browser.
"""

from __future__ import annotations

import os
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import anthropic

SYSTEM_PROMPT = """You are a senior software engineer with 15+ years of experience across Python, JavaScript, TypeScript, Go, Rust, Java, C, C++, shell scripting, SQL, and cloud infrastructure. You specialize in debugging and explaining errors clearly to developers at all levels.

When given an error message, stack trace, or exception, you will:

1. **Identify the error type** — State what kind of error this is and which language/runtime/tool produced it.
2. **Explain in plain English** — Describe what the error actually means in simple terms.
3. **Identify the most likely root cause** — Point to the specific line(s) or concept that is the root of the problem.
4. **Give numbered fix steps** — Provide concrete, actionable steps with code snippets where helpful.
5. **Note common gotchas** — Highlight subtle pitfalls developers often hit with this error type.

Use markdown formatting. Be direct and confident."""

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>errex — Error Explainer</title>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0f1117;
      color: #e2e8f0;
      min-height: 100vh;
      padding: 2rem 1rem;
    }
    .container { max-width: 800px; margin: 0 auto; }
    h1 { font-size: 1.75rem; font-weight: 700; color: #7dd3fc; margin-bottom: 0.25rem; }
    .subtitle { color: #64748b; font-size: 0.9rem; margin-bottom: 2rem; }
    label { display: block; font-size: 0.85rem; color: #94a3b8; margin-bottom: 0.5rem; }
    textarea {
      width: 100%;
      height: 180px;
      background: #1e2130;
      border: 1px solid #2d3748;
      border-radius: 8px;
      color: #e2e8f0;
      font-family: "SF Mono", "Fira Code", monospace;
      font-size: 0.85rem;
      padding: 0.75rem;
      resize: vertical;
      outline: none;
      transition: border-color 0.2s;
    }
    textarea:focus { border-color: #7dd3fc; }
    .controls {
      display: flex;
      gap: 0.75rem;
      margin: 1rem 0;
      align-items: center;
      flex-wrap: wrap;
    }
    select {
      background: #1e2130;
      border: 1px solid #2d3748;
      border-radius: 6px;
      color: #e2e8f0;
      padding: 0.5rem 0.75rem;
      font-size: 0.85rem;
      outline: none;
      cursor: pointer;
    }
    label.checkbox { display: flex; align-items: center; gap: 0.4rem; cursor: pointer; font-size: 0.85rem; color: #94a3b8; }
    button {
      background: #2563eb;
      color: white;
      border: none;
      border-radius: 6px;
      padding: 0.5rem 1.5rem;
      font-size: 0.9rem;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.2s;
      margin-left: auto;
    }
    button:hover { background: #1d4ed8; }
    button:disabled { background: #334155; cursor: not-allowed; }
    #output {
      display: none;
      margin-top: 1.5rem;
      background: #1e2130;
      border: 1px solid #2d3748;
      border-radius: 8px;
      padding: 1.25rem 1.5rem;
    }
    #output h2, #output h3 { color: #7dd3fc; margin: 1rem 0 0.5rem; }
    #output h2:first-child, #output h3:first-child { margin-top: 0; }
    #output p { line-height: 1.7; color: #cbd5e1; margin-bottom: 0.75rem; }
    #output ul, #output ol { padding-left: 1.5rem; color: #cbd5e1; margin-bottom: 0.75rem; }
    #output li { margin-bottom: 0.3rem; line-height: 1.6; }
    #output code {
      background: #0f1117;
      border: 1px solid #2d3748;
      border-radius: 4px;
      padding: 0.1em 0.4em;
      font-family: "SF Mono", "Fira Code", monospace;
      font-size: 0.85em;
      color: #86efac;
    }
    #output pre {
      background: #0f1117;
      border: 1px solid #2d3748;
      border-radius: 6px;
      padding: 1rem;
      overflow-x: auto;
      margin-bottom: 0.75rem;
    }
    #output pre code { background: none; border: none; padding: 0; color: #86efac; }
    #output strong { color: #f1f5f9; }
    .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid #fff3; border-top-color: white; border-radius: 50%; animation: spin 0.7s linear infinite; margin-right: 0.5rem; vertical-align: middle; }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div class="container">
    <h1>errex</h1>
    <p class="subtitle">Paste any error and get a plain-English explanation.</p>

    <label for="error">Error message or stack trace</label>
    <textarea id="error" placeholder="Paste your error here..."></textarea>

    <div class="controls">
      <select id="model">
        <option value="claude-sonnet-4-6">claude-sonnet-4-6</option>
        <option value="claude-opus-4-7">claude-opus-4-7</option>
        <option value="claude-haiku-4-5">claude-haiku-4-5</option>
      </select>
      <label class="checkbox">
        <input type="checkbox" id="brief"> Brief
      </label>
      <button id="btn" onclick="explain()">Explain</button>
    </div>

    <div id="output"></div>
  </div>

  <script>
    async function explain() {
      const error = document.getElementById('error').value.trim();
      if (!error) return;
      const model = document.getElementById('model').value;
      const brief = document.getElementById('brief').checked;
      const btn = document.getElementById('btn');
      const output = document.getElementById('output');

      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span>Explaining…';
      output.style.display = 'block';
      output.innerHTML = '<span style="color:#64748b">Thinking…</span>';

      try {
        const resp = await fetch('/explain', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ error, model, brief }),
        });
        const data = await resp.json();
        if (data.error) {
          output.innerHTML = `<p style="color:#f87171">${data.error}</p>`;
        } else {
          output.innerHTML = marked.parse(data.explanation);
        }
      } catch (e) {
        output.innerHTML = `<p style="color:#f87171">Request failed: ${e.message}</p>`;
      } finally {
        btn.disabled = false;
        btn.textContent = 'Explain';
      }
    }

    document.getElementById('error').addEventListener('keydown', e => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') explain();
    });
  </script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress default access log

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML.encode())

    def do_POST(self):
        if urlparse(self.path).path != "/explain":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        error_text = body.get("error", "").strip()
        model = body.get("model", "claude-sonnet-4-6")
        brief = body.get("brief", False)

        if not error_text:
            self._json({"error": "No error text provided."}, 400)
            return

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            self._json({"error": "ANTHROPIC_API_KEY is not set."}, 500)
            return

        try:
            client = anthropic.Anthropic(api_key=api_key)
            if brief:
                prompt = f"In one short paragraph, tell me: what this error is, the most likely cause, and how to fix it.\n\n```\n{error_text}\n```"
            else:
                prompt = f"Please explain this error:\n\n```\n{error_text}\n```"

            message = client.messages.create(
                model=model,
                max_tokens=256 if brief else 2048,
                system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": prompt}],
            )
            self._json({"explanation": message.content[0].text})
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _json(self, data: dict, status: int = 200) -> None:
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def serve(host: str = "127.0.0.1", port: int = 7337) -> None:
    server = HTTPServer((host, port), Handler)
    print(f"errex web UI → http://{host}:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    serve()
