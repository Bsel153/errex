"""errex web UI — run with: errex --web  →  http://localhost:7337"""

from __future__ import annotations

import base64
import hmac
import html
import json
import os
import re
import socket
import subprocess
import time
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
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <meta name="theme-color" content="#0f1117">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
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


    /* ── Sidebar tab bar ── */
    .sbar-tabs { display: flex; gap: 0; border-bottom: 1px solid var(--border); margin-bottom: 0.65rem; }
    .sbar-tab {
      background: none; border: none; border-bottom: 2px solid transparent;
      color: var(--muted); cursor: pointer; font-size: 0.78rem; font-weight: 500;
      padding: 0.35rem 0.75rem; transition: color 0.15s, border-color 0.15s;
    }
    .sbar-tab:hover { background: none; color: var(--text); }
    .sbar-tab.active { border-bottom-color: var(--accent); color: var(--accent); }
    /* ── Stats ── */
    .stat-total { font-size: 2.2rem; font-weight: 700; color: var(--accent);
                  margin-bottom: 1rem; line-height: 1.1; }
    .stat-total span { font-size: 0.9rem; font-weight: 400; color: var(--muted); margin-left: 0.35rem; }
    .stat-section { font-size: 0.7rem; font-weight: 600; color: var(--muted);
                    letter-spacing: 0.06em; text-transform: uppercase; margin: 1rem 0 0.5rem; }
    .bar-row { display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.35rem; }
    .bar-label { font-size: 0.75rem; color: #cbd5e1; width: 130px; flex-shrink: 0;
                 overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .bar-track { flex: 1; background: var(--panel); border: 1px solid var(--border);
                 border-radius: 3px; height: 8px; overflow: hidden; }
    .bar-fill { height: 100%; background: var(--accent); border-radius: 3px; transition: width 0.4s ease; }
    .bar-count { font-size: 0.75rem; color: var(--muted); width: 24px; text-align: right; flex-shrink: 0; }
    .muted { color: var(--muted); font-size: 0.85rem; }

    /* ── Stats tab ── */
    .tab-bar { display:flex; gap:0.25rem; margin-bottom:1rem; border-bottom:1px solid var(--border); }
    .sbar-tab { background:none; border:none; border-bottom:2px solid transparent; color:var(--muted);
                cursor:pointer; font-size:0.85rem; padding:0.45rem 0.9rem; transition:color .2s,border-color .2s; }
    .sbar-tab:hover { color:var(--text); }
    .sbar-tab.active { border-bottom-color:var(--accent); color:var(--accent); }
    .stat-total { font-size:2.2rem; font-weight:700; color:var(--accent); margin-bottom:1rem; }
    .stat-total span { font-size:0.9rem; font-weight:400; color:var(--muted); margin-left:0.3rem; }
    .stat-section { font-size:0.72rem; font-weight:600; color:var(--muted); letter-spacing:.06em;
                    text-transform:uppercase; margin:1.1rem 0 0.5rem; }
    .bar-row { display:flex; align-items:center; gap:0.5rem; margin-bottom:0.35rem; }
    .bar-label { font-size:0.78rem; color:#cbd5e1; width:130px; flex-shrink:0;
                 overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .bar-track { flex:1; background:#1e2130; border:1px solid var(--border); border-radius:3px; height:9px; overflow:hidden; }
    .bar-fill { height:100%; background:var(--accent); border-radius:3px; transition:width .4s ease; }
    .bar-count { font-size:0.78rem; color:var(--muted); width:26px; text-align:right; flex-shrink:0; }

    /* ── Mobile / touch ── */
    @media (max-width: 768px) {
      body { height: auto; overflow: auto; }
      .app { grid-template-columns: 1fr; grid-template-rows: auto; height: auto; min-height: 100vh; }
      .hdr { position: sticky; top: 0; z-index: 10; background: var(--bg); }
      .hdr .sub { display: none; }
      .main { border-right: none; border-bottom: 1px solid var(--border); overflow: visible; }
      .sidebar { max-height: none; padding: 1rem; }
      textarea {
        height: 160px;
        font-size: 16px; /* prevents iOS zoom-on-focus */
      }
      .controls { flex-direction: column; align-items: stretch; gap: 0.6rem; }
      .controls > * { width: 100%; }
      select { font-size: 16px; min-height: 44px; padding: 0.55rem 0.75rem; }
      .tabs { width: 100%; }
      .tabs button { flex: 1; min-height: 44px; font-size: 0.95rem; padding: 0.55rem 0; }
      .chk { font-size: 0.9rem; padding: 0.3rem 0; }
      .chk input { width: 18px; height: 18px; flex-shrink: 0; }
      #btn { min-height: 52px; font-size: 1.05rem; padding: 0.7rem 1.5rem; margin-left: 0; }
      .btn-copy { min-height: 40px; font-size: 0.8rem; padding: 0.4rem 0.8rem; }
      .he { padding: 0.7rem 0.85rem; }
      .he-err { font-size: 0.82rem; }
      #out { font-size: 0.95rem; }
      #out h2, #out h3 { font-size: 1rem; }
      #out code { font-size: 0.85em; }
    }
  </style>
</head>
<body>
<div class="app">
  <header class="hdr">
    <h1>errex</h1>
    <span class="sub">paste any error · get a plain-English explanation</span>
    <a href="/privacy" target="_blank" style="margin-left:auto;font-size:0.72rem;color:var(--muted);text-decoration:none;border:1px solid var(--border);border-radius:5px;padding:0.18rem 0.5rem;" title="Privacy policy — what errex sees and stores">🔒 Privacy</a>
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
    <div class="sbar-tabs">
      <button class="sbar-tab active" onclick="switchTab('history')">History</button>
      <button class="sbar-tab" onclick="switchTab('stats')">Stats</button>
    </div>
    <div id="history-content">
      <div id="hist"><p class="he-empty">Loading…</p></div>
    </div>
    <div id="stats-content" style="display:none"></div>
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


  // ── Stats tab ──
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
    document.querySelectorAll('.sbar-tab').forEach(t => t.classList.toggle('active', t.textContent.toLowerCase() === name));
    if (name === 'stats') loadStats();
  }

  loadHist();
</script>
</body>
</html>"""


# ─── HTTP Handler ─────────────────────────────────────────────────────────────


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
        if not hmac.compare_digest(given.encode(), expected.encode()):
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

        if path == "/privacy":
            from .security import get_privacy_text
            text = get_privacy_text()
            body = (
                "<!DOCTYPE html><html><head>"
                "<meta charset='UTF-8'>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<title>errex — Privacy</title>"
                "<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
                "background:#0f1117;color:#e2e8f0;max-width:760px;margin:2rem auto;padding:0 1.25rem;}"
                "pre{background:#1a1d27;border:1px solid #2d3748;border-radius:8px;padding:1.25rem;"
                "white-space:pre-wrap;word-break:break-word;font-size:0.88rem;line-height:1.7;}"
                "a{color:#7dd3fc;}h1{color:#7dd3fc;margin-bottom:0.5rem;}</style></head>"
                f"<body><h1>🔒 errex Privacy</h1><pre>{html.escape(text)}</pre></body></html>"
            )
            self._html(body)
            return

        if path == "/permissions":
            from .security import get_permissions_summary
            self._json(get_permissions_summary())
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

        _MAX_BODY = 64 * 1024  # 64 KB — prevent memory exhaustion
        length = min(int(self.headers.get("Content-Length", 0)), _MAX_BODY)
        body = json.loads(self.rfile.read(length))
        error_text = body.get("error", "").strip()
        _ALLOWED_MODELS = {
            "claude-sonnet-4-6",
            "claude-opus-4-8",
            "claude-haiku-4-5-20251001",
        }
        model = body.get("model", "claude-sonnet-4-6")
        if model not in _ALLOWED_MODELS:
            self._json({"error": "Invalid model."}, 400)
            return
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

    def _html(self, body: str, status: int = 200) -> None:
        payload = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, data: dict, status: int = 200) -> None:
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _local_ip() -> str:
    """Return the machine's LAN IP address."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def _start_tunnel(port: int) -> str | None:
    """Start a cloudflared quick tunnel. Returns public URL or None."""
    try:
        proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except FileNotFoundError:
        return None

    url_pat = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
    deadline = time.time() + 30
    for line in proc.stdout:  # type: ignore[union-attr]
        m = url_pat.search(line)
        if m:
            return m.group(0)
        if time.time() > deadline:
            proc.kill()
            return None
    return None


def _print_qr(url: str) -> None:
    """Print a terminal QR code for url using qrencode if available."""
    try:
        result = subprocess.run(
            ["qrencode", "-t", "UTF8", "-o", "-", url],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            print(result.stdout)
            return
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    print("  (install qrencode for a scannable QR: brew install qrencode)")


def _print_banner(local_ip: str, port: int, tunnel_url: str | None,
                  scheme: str = "http") -> None:
    local_url = f"{scheme}://{local_ip}:{port}"
    col = 58
    def row(label: str, value: str) -> str:
        content = f"  {label:<18}{value}"
        return f"│{content:<{col}}│"

    print("┌" + "─" * col + "┐")
    print(f"│  {'errex Web UI':<{col - 2}}│")
    print("│" + " " * col + "│")
    print(row("Local network:", local_url))
    if tunnel_url:
        print(row("Public URL:", tunnel_url))
    print("│" + " " * col + "│")
    print(f"│  {'Ctrl+C to stop':<{col - 2}}│")
    print("└" + "─" * col + "┘")
    if tunnel_url:
        print()
        print(f"  Scan to open on your phone:")
        _print_qr(tunnel_url)
    print()


def serve(host: str = "127.0.0.1", port: int = 7337, auth: str | None = None,
          tunnel: bool = False, tls: bool = False,
          cert: str | None = None, key: str | None = None) -> None:
    """Start the web UI.

    tunnel=True  — start a free Cloudflare quick tunnel for public access
    tls=True     — wrap in HTTPS using an auto-generated self-signed cert
    cert/key     — paths to an existing cert/key (implies tls=True)
    """
    import ssl as _ssl
    token = base64.b64encode(auth.encode()).decode() if auth else None
    if tunnel and not auth:
        print("  ⚠  Warning: --tunnel exposes this server publicly without authentication.")
        print("     Pass --auth user:pass to require a password.\n")
    server = HTTPServer((host, port), _make_handler(token))

    scheme = "http"
    if tls or cert:
        from .security import generate_self_signed_cert
        from pathlib import Path as _Path
        if not cert:
            cert, key = generate_self_signed_cert()
        ctx = _ssl.SSLContext(_ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        scheme = "https"

    local_ip = _local_ip()
    tunnel_url = None
    if tunnel:
        print("  Starting Cloudflare tunnel…", end=" ", flush=True)
        tunnel_url = _start_tunnel(port)
        if tunnel_url:
            print("connected!")
        else:
            print("failed.\n  Install cloudflared:  brew install cloudflared  or  https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")

    _print_banner(local_ip, port, tunnel_url, scheme=scheme)
    if scheme == "https":
        print("  Note: browser will warn about self-signed cert — this is expected.")
        print(f"  Cert: {cert}\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    serve()
