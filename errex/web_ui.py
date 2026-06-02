# Web UI server — serves the browser interface at http://localhost:7337
"""
errex web UI — run with: python -m errex.web_ui
Then open http://localhost:7337 in your browser.
"""

from __future__ import annotations

import base64
import os
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import anthropic

from ._paths import HISTORY_FILE as _HISTORY_FILE

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
    /* Tab bar */
    .tab-bar {
      display: flex;
      gap: 0.25rem;
      margin-bottom: 1rem;
      border-bottom: 1px solid #2d3748;
      padding-bottom: 0;
    }
    .tab {
      background: none;
      border: none;
      border-bottom: 2px solid transparent;
      border-radius: 0;
      color: #94a3b8;
      cursor: pointer;
      font-size: 0.85rem;
      font-weight: 500;
      margin-left: 0;
      padding: 0.5rem 1rem;
      transition: color 0.2s, border-color 0.2s;
    }
    .tab:hover { background: none; color: #e2e8f0; }
    .tab.active { border-bottom-color: #7dd3fc; color: #7dd3fc; }
    /* Stats styles */
    .stat-total {
      font-size: 2.5rem;
      font-weight: 700;
      color: #7dd3fc;
      margin-bottom: 1.25rem;
      line-height: 1.1;
    }
    .stat-total span {
      font-size: 1rem;
      font-weight: 400;
      color: #64748b;
      margin-left: 0.4rem;
    }
    .stat-section {
      font-size: 0.75rem;
      font-weight: 600;
      color: #64748b;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      margin: 1.25rem 0 0.6rem;
    }
    .bar-row {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin-bottom: 0.4rem;
    }
    .bar-label {
      font-size: 0.8rem;
      color: #cbd5e1;
      width: 140px;
      flex-shrink: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .bar-track {
      flex: 1;
      background: #1e2130;
      border: 1px solid #2d3748;
      border-radius: 3px;
      height: 10px;
      overflow: hidden;
    }
    .bar-fill {
      height: 100%;
      background: #7dd3fc;
      border-radius: 3px;
      transition: width 0.4s ease;
    }
    .bar-count {
      font-size: 0.8rem;
      color: #64748b;
      width: 28px;
      text-align: right;
      flex-shrink: 0;
    }
    .muted { color: #64748b; font-size: 0.9rem; }
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

    <div style="margin-top:2rem;">
      <div class="tab-bar">
        <button class="tab active" onclick="switchTab('history')">History</button>
        <button class="tab" onclick="switchTab('stats')">Stats</button>
      </div>
      <div id="history-content"><!-- existing history list --></div>
      <div id="stats-content" style="display:none"></div>
    </div>
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

    // Stats tab
    async function loadStats() {
      const r = await fetch('/stats');
      const d = await r.json();
      const el = document.getElementById('stats-content');
      if (!d.total) { el.innerHTML = '<p class="muted">No history yet.</p>'; return; }

      let html = `<div class="stat-total">${d.total} <span>explanations</span></div>`;

      if (Object.keys(d.error_types).length) {
        html += '<div class="stat-section">Top error types</div>';
        const max = Math.max(...Object.values(d.error_types));
        for (const [k, v] of Object.entries(d.error_types).slice(0, 8)) {
          const pct = Math.round(v / max * 100);
          html += `<div class="bar-row"><span class="bar-label">${k}</span>
            <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
            <span class="bar-count">${v}</span></div>`;
        }
      }

      if (Object.keys(d.models).length) {
        html += '<div class="stat-section">Models</div>';
        const maxM = Math.max(...Object.values(d.models));
        for (const [k, v] of Object.entries(d.models)) {
          const pct = Math.round(v / maxM * 100);
          html += `<div class="bar-row"><span class="bar-label">${k}</span>
            <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
            <span class="bar-count">${v}</span></div>`;
        }
      }

      if (Object.keys(d.daily).length) {
        html += '<div class="stat-section">Activity (last 14 days)</div>';
        for (const [day, cnt] of Object.entries(d.daily)) {
          html += `<div class="bar-row"><span class="bar-label">${day}</span><span class="bar-count">${cnt}</span></div>`;
        }
      }

      el.innerHTML = html;
    }

    function switchTab(name) {
      document.getElementById('history-content').style.display = name === 'history' ? '' : 'none';
      document.getElementById('stats-content').style.display = name === 'stats' ? '' : 'none';
      document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.textContent.toLowerCase() === name));
      if (name === 'stats') loadStats();
    }
  </script>
</body>
</html>"""


def _compute_stats() -> dict:
    from collections import Counter
    entries = []
    if _HISTORY_FILE.exists():
        with open(_HISTORY_FILE) as f:
            for line in f:
                if line.strip():
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
    if not entries:
        return {"total": 0, "error_types": {}, "models": {}, "daily": {}}
    from .utils import extract_error_type
    error_types = Counter(extract_error_type(e.get("error", "")) for e in entries)
    models = Counter(e.get("model", "unknown") for e in entries)
    daily = Counter(e["timestamp"][:10] for e in entries if "timestamp" in e)
    return {
        "total": len(entries),
        "error_types": dict(error_types.most_common(10)),
        "models": dict(models),
        "daily": dict(sorted(daily.items())[-14:]),  # last 14 days
    }


def _make_handler(auth_token: str | None):
    class _H(Handler):
        _auth = auth_token  # base64-encoded "user:pass", or None
    return _H


class Handler(BaseHTTPRequestHandler):
    _auth: str | None = None

    def log_message(self, fmt, *args):
        pass  # suppress default access log

    def _check_auth(self) -> bool:
        """Return True if auth passes (or auth is disabled). Send 401 and return False otherwise."""
        if not self._auth:
            return True
        given = self.headers.get("Authorization", "")
        expected = "Basic " + self._auth
        if given != expected:
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="errex"')
            self.end_headers()
            return False
        return True

    def do_GET(self):
        if not self._check_auth():
            return

        path = urlparse(self.path).path

        if path == "/stats":
            self._json(_compute_stats())
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML.encode())

    def do_POST(self):
        if not self._check_auth():
            return

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


def serve(host: str = "127.0.0.1", port: int = 7337, auth: str | None = None) -> None:
    """auth format: 'user:password'"""
    token = base64.b64encode(auth.encode()).decode() if auth else None
    server = HTTPServer((host, port), _make_handler(token))
    print(f"errex web UI → http://{host}:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    serve()
