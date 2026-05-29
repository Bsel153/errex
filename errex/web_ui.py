"""errex web UI — run with: errex --web  →  http://localhost:7337"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

import anthropic

from . import _constants
from .patterns import match_pattern

_HISTORY_FILE = Path.home() / ".errex_history"

# ─── HTML ─────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>errex</title>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --bg: #0f1117; --panel: #1a1d27; --border: #2d3748;
      --text: #e2e8f0; --muted: #64748b; --accent: #7dd3fc;
      --green: #86efac; --red: #f87171; --r: 8px;
    }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
           background: var(--bg); color: var(--text); height: 100vh; overflow: hidden; }

    /* ── Two-column layout ── */
    .app { display: grid; grid-template-columns: 3fr 2fr; grid-template-rows: auto 1fr;
           height: 100vh; }
    .hdr { grid-column: 1/-1; padding: 0.75rem 1.25rem; border-bottom: 1px solid var(--border);
           display: flex; align-items: center; gap: 0.75rem; }
    .hdr h1 { font-size: 1.15rem; font-weight: 700; color: var(--accent); }
    .hdr .sub { color: var(--muted); font-size: 0.82rem; }
    .main { padding: 1.1rem; overflow-y: auto; border-right: 1px solid var(--border);
            display: flex; flex-direction: column; gap: 0.75rem; }
    .sidebar { padding: 0.9rem; overflow-y: auto; }

    /* ── Input ── */
    textarea {
      width: 100%; height: 140px; background: var(--panel); border: 1px solid var(--border);
      border-radius: var(--r); color: var(--text);
      font-family: "SF Mono","Fira Code",monospace; font-size: 0.8rem;
      padding: 0.7rem; resize: vertical; outline: none; transition: border-color 0.15s;
    }
    textarea:focus { border-color: var(--accent); }

    /* ── Controls ── */
    .controls { display: flex; align-items: center; gap: 0.55rem; flex-wrap: wrap; }
    select {
      background: var(--panel); border: 1px solid var(--border); border-radius: 6px;
      color: var(--text); padding: 0.38rem 0.6rem; font-size: 0.8rem; outline: none; cursor: pointer;
    }
    .tabs { display: flex; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
    .tabs button {
      background: var(--panel); border: none; color: var(--muted); padding: 0.38rem 0.75rem;
      font-size: 0.8rem; cursor: pointer; transition: background 0.15s, color 0.15s;
    }
    .tabs button.on { background: var(--accent); color: #0f1117; font-weight: 600; }
    .chk { display: flex; align-items: center; gap: 0.3rem; cursor: pointer;
           font-size: 0.8rem; color: var(--muted); user-select: none; }
    .chk input { accent-color: var(--accent); }
    #btn {
      margin-left: auto; background: #2563eb; color: white; border: none;
      border-radius: 6px; padding: 0.42rem 1.1rem; font-size: 0.88rem; font-weight: 600;
      cursor: pointer; transition: background 0.15s;
    }
    #btn:hover { background: #1d4ed8; }
    #btn:disabled { background: #334155; cursor: not-allowed; }

    /* ── Output ── */
    #out-wrap { display: none; flex-direction: column; gap: 0.45rem; }
    .out-hdr { display: flex; align-items: center; gap: 0.5rem; }
    .badge { font-size: 0.72rem; padding: 0.18rem 0.5rem; border-radius: 12px; font-weight: 600; }
    .b-local { background: #14532d; color: var(--green); }
    .b-claude { background: #1e3a5f; color: var(--accent); }
    .btn-copy {
      margin-left: auto; background: transparent; border: 1px solid var(--border);
      color: var(--muted); border-radius: 5px; padding: 0.2rem 0.55rem;
      font-size: 0.72rem; cursor: pointer; transition: border-color 0.15s, color 0.15s;
    }
    .btn-copy:hover { border-color: var(--accent); color: var(--accent); }
    #out {
      background: var(--panel); border: 1px solid var(--border); border-radius: var(--r);
      padding: 1rem 1.15rem; min-height: 72px;
    }
    #out h2, #out h3 { color: var(--accent); margin: 0.85rem 0 0.4rem; font-size: 0.97rem; }
    #out h2:first-child, #out h3:first-child { margin-top: 0; }
    #out p { line-height: 1.7; color: #cbd5e1; margin-bottom: 0.55rem; }
    #out ul, #out ol { padding-left: 1.35rem; color: #cbd5e1; margin-bottom: 0.55rem; }
    #out li { line-height: 1.6; margin-bottom: 0.18rem; }
    #out code {
      background: var(--bg); border: 1px solid var(--border); border-radius: 4px;
      padding: 0.1em 0.32em; font-family: "SF Mono","Fira Code",monospace;
      font-size: 0.8em; color: var(--green);
    }
    #out pre { background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
               padding: 0.8rem; overflow-x: auto; margin-bottom: 0.55rem; }
    #out pre code { background: none; border: none; padding: 0; }
    #out strong { color: #f1f5f9; }
    #meta { font-size: 0.72rem; color: var(--muted); }
    .spin { display: inline-block; width: 11px; height: 11px; border: 2px solid #fff3;
            border-top-color: white; border-radius: 50%;
            animation: rot 0.7s linear infinite; margin-right: 0.35rem; vertical-align: middle; }
    @keyframes rot { to { transform: rotate(360deg); } }

    /* ── History ── */
    .sidebar h2 { font-size: 0.78rem; font-weight: 600; color: var(--muted);
                  text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.65rem; }
    #hist { display: flex; flex-direction: column; gap: 0.45rem; }
    .he {
      background: var(--panel); border: 1px solid var(--border); border-radius: 6px;
      padding: 0.55rem 0.7rem; cursor: pointer; transition: border-color 0.15s;
    }
    .he:hover { border-color: var(--accent); }
    .he-err { font-size: 0.75rem; font-family: "SF Mono","Fira Code",monospace;
              color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .he-meta { font-size: 0.68rem; color: var(--muted); margin-top: 0.25rem;
               display: flex; justify-content: space-between; }
    .he-empty { font-size: 0.8rem; color: var(--muted); text-align: center; padding: 1.25rem 0; }

    /* ── Mobile ── */
    @media (max-width: 680px) {
      .app { grid-template-columns: 1fr; }
      .main { border-right: none; border-bottom: 1px solid var(--border); }
      .sidebar { max-height: 200px; }
    }
  </style>
</head>
<body>
<div class="app">
  <header class="hdr">
    <h1>errex</h1>
    <span class="sub">paste any error · get a plain-English explanation</span>
  </header>

  <main class="main">
    <textarea id="err" placeholder="Paste your error or stack trace here…" spellcheck="false"></textarea>

    <div class="controls">
      <select id="model">
        <option value="claude-sonnet-4-6">claude-sonnet-4-6</option>
        <option value="claude-opus-4-8">claude-opus-4-8</option>
        <option value="claude-haiku-4-5-20251001">claude-haiku-4-5</option>
      </select>
      <div class="tabs">
        <button class="on" id="t-full" onclick="setMode('full')">Full</button>
        <button id="t-brief" onclick="setMode('brief')">Brief</button>
      </div>
      <label class="chk"><input type="checkbox" id="no-cache"> ⚡ Skip cache</label>
      <button id="btn" onclick="explain()">Explain</button>
    </div>

    <div id="out-wrap">
      <div class="out-hdr">
        <span id="badge" class="badge"></span>
        <button class="btn-copy" onclick="copyOut()">Copy</button>
      </div>
      <div id="out"></div>
      <div id="meta"></div>
    </div>
  </main>

  <aside class="sidebar">
    <h2>History</h2>
    <div id="hist"><p class="he-empty">Loading…</p></div>
  </aside>
</div>

<script>
  let mode = 'full', md = '';

  function setMode(m) {
    mode = m;
    document.getElementById('t-full').classList.toggle('on', m === 'full');
    document.getElementById('t-brief').classList.toggle('on', m === 'brief');
  }

  function esc(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  async function explain() {
    const error = document.getElementById('err').value.trim();
    if (!error) return;
    const model = document.getElementById('model').value;
    const noCache = document.getElementById('no-cache').checked;
    const brief = (mode === 'brief');
    const btn = document.getElementById('btn');
    const wrap = document.getElementById('out-wrap');
    const out = document.getElementById('out');
    const meta = document.getElementById('meta');
    const badge = document.getElementById('badge');

    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>Explaining…';
    wrap.style.display = 'flex';
    out.innerHTML = '<span style="color:var(--muted)">Thinking…</span>';
    meta.textContent = '';
    badge.textContent = '';
    badge.className = 'badge';
    md = '';

    const t0 = performance.now();

    try {
      const resp = await fetch('/explain', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({error, model, brief, noCache}),
      });

      const ct = resp.headers.get('content-type') || '';

      if (ct.includes('application/json')) {
        // Pattern cache hit
        const data = await resp.json();
        if (data.error) {
          out.innerHTML = `<p style="color:var(--red)">${esc(data.error)}</p>`;
        } else {
          md = data.explanation;
          out.innerHTML = marked.parse(md);
          badge.textContent = '⚡ local';
          badge.className = 'badge b-local';
          meta.textContent = `instant · ${((performance.now()-t0)/1000).toFixed(2)}s`;
        }
      } else {
        // SSE stream from Claude
        const reader = resp.body.getReader();
        const dec = new TextDecoder();
        let buf = '';
        out.innerHTML = '';

        while (true) {
          const {done, value} = await reader.read();
          if (done) break;
          buf += dec.decode(value, {stream: true});
          const parts = buf.split('\n\n');
          buf = parts.pop();
          for (const part of parts) {
            if (!part.startsWith('data: ')) continue;
            let d;
            try { d = JSON.parse(part.slice(6)); } catch { continue; }
            if (d.t !== undefined) {
              md += d.t;
              out.innerHTML = marked.parse(md);
            } else if (d.done) {
              badge.textContent = '🤖 Claude';
              badge.className = 'badge b-claude';
              const secs = ((performance.now()-t0)/1000).toFixed(1);
              meta.textContent = `${d.in} in / ${d.out} out tokens · ${secs}s`;
              loadHist();
            } else if (d.error) {
              out.innerHTML = `<p style="color:var(--red)">${esc(d.error)}</p>`;
            }
          }
        }
      }
    } catch (e) {
      out.innerHTML = `<p style="color:var(--red)">Request failed: ${esc(e.message)}</p>`;
    } finally {
      btn.disabled = false;
      btn.textContent = 'Explain';
      wrap.scrollIntoView({behavior:'smooth', block:'nearest'});
    }
  }

  function copyOut() {
    if (md) navigator.clipboard.writeText(md).catch(() => {});
  }

  async function loadHist() {
    try {
      const r = await fetch('/history');
      const d = await r.json();
      renderHist(d.entries || []);
    } catch { renderHist([]); }
  }

  function renderHist(entries) {
    const el = document.getElementById('hist');
    if (!entries.length) {
      el.innerHTML = '<p class="he-empty">No history yet.</p>';
      return;
    }
    window._hist = entries;
    el.innerHTML = entries.map((e, i) => `
      <div class="he" onclick="loadEntry(${i})">
        <div class="he-err">${esc(e.error)}</div>
        <div class="he-meta"><span>${esc(e.model||'')}</span><span>${esc(e.ts||'')}</span></div>
      </div>`).join('');
  }

  function loadEntry(i) {
    const e = (window._hist||[])[i];
    if (e) { document.getElementById('err').value = e.error; }
  }

  document.getElementById('err').addEventListener('keydown', ev => {
    if ((ev.metaKey || ev.ctrlKey) && ev.key === 'Enter') explain();
  });

  loadHist();
</script>
</body>
</html>"""


# ─── HTTP Handler ─────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress default access log

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/history":
            entries = []
            if _HISTORY_FILE.exists():
                with open(_HISTORY_FILE, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            try:
                                e = json.loads(line)
                                entries.append({
                                    "error": e.get("error", "")[:120],
                                    "model": e.get("model", ""),
                                    "ts": e.get("timestamp", "")[:16],
                                })
                            except Exception:
                                pass
            self._json({"entries": list(reversed(entries[-25:]))})
            return

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
        no_cache = body.get("noCache", False)

        if not error_text:
            self._json({"error": "No error text provided."}, 400)
            return

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            self._json({"error": "ANTHROPIC_API_KEY is not set."}, 500)
            return

        # Pattern cache check
        if not no_cache:
            hit = match_pattern(error_text)
            if hit:
                title, explanation = hit
                self._json({"source": "local", "title": title, "explanation": explanation})
                return

        # Stream from Claude
        if brief:
            prompt = (
                f"In one short paragraph, tell me: what this error is, "
                f"the most likely cause, and how to fix it.\n\n```\n{error_text}\n```"
            )
        else:
            prompt = f"Please explain this error:\n\n```\n{error_text}\n```"

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        try:
            client = anthropic.Anthropic(api_key=api_key, timeout=_constants.API_TIMEOUT)
            with client.messages.stream(
                model=model,
                max_tokens=256 if brief else 2048,
                system=[{
                    "type": "text",
                    "text": _constants.SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for text in stream.text_stream:
                    self._sse({"t": text})
                final = stream.get_final_message()
                self._sse({
                    "done": True,
                    "in": final.usage.input_tokens,
                    "out": final.usage.output_tokens,
                })
        except Exception as e:
            try:
                self._sse({"error": str(e)})
            except Exception:
                pass

    def _sse(self, data: dict) -> None:
        line = f"data: {json.dumps(data)}\n\n".encode()
        self.wfile.write(line)
        self.wfile.flush()

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
