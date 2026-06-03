import * as vscode from 'vscode';
import * as cp from 'child_process';

export function activate(context: vscode.ExtensionContext) {
    // Register: explain selected text
    context.subscriptions.push(
        vscode.commands.registerCommand('errex.explainSelection', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) return;
            const selection = editor.selection;
            const text = editor.document.getText(selection);
            if (!text.trim()) {
                vscode.window.showWarningMessage('Select an error message first.');
                return;
            }
            await explainText(text);
        })
    );

    // Register: explain from clipboard
    context.subscriptions.push(
        vscode.commands.registerCommand('errex.explainFromClipboard', async () => {
            const text = await vscode.env.clipboard.readText();
            if (!text.trim()) {
                vscode.window.showWarningMessage('Clipboard is empty.');
                return;
            }
            await explainText(text);
        })
    );
}

async function explainText(errorText: string): Promise<void> {
    const config = vscode.workspace.getConfiguration('errex');
    const useWebUi = config.get<boolean>('useWebUi', false);
    const webUiUrl = config.get<string>('webUiUrl', 'http://localhost:7337');

    await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: 'errex: explaining...', cancellable: false },
        async () => {
            try {
                let explanation: string;
                if (useWebUi) {
                    explanation = await explainViaWebUi(errorText, webUiUrl);
                } else {
                    explanation = await explainViaCli(errorText, config);
                }
                showExplanation(explanation);
            } catch (err: unknown) {
                const msg = err instanceof Error ? err.message : String(err);
                vscode.window.showErrorMessage(`errex failed: ${msg}`);
            }
        }
    );
}

async function explainViaCli(errorText: string, config: vscode.WorkspaceConfiguration): Promise<string> {
    const cliPath = config.get<string>('cliPath', 'errex');
    const apiKey = config.get<string>('anthropicApiKey', '');

    return new Promise((resolve, reject) => {
        const env: NodeJS.ProcessEnv = { ...process.env };
        if (apiKey) {
            env['ANTHROPIC_API_KEY'] = apiKey;
        }

        const proc = cp.spawn(cliPath, ['--no-history', '--terse', '-'], {
            env,
            stdio: ['pipe', 'pipe', 'pipe']
        });

        let stdout = '';
        let stderr = '';
        proc.stdout.on('data', (d: Buffer) => { stdout += d.toString(); });
        proc.stderr.on('data', (d: Buffer) => { stderr += d.toString(); });
        proc.on('close', (code) => {
            if (code !== 0 && !stdout.trim()) {
                reject(new Error(stderr || `errex exited with code ${code}`));
            } else {
                resolve(stdout.trim() || stderr.trim());
            }
        });
        proc.on('error', (err) => {
            reject(new Error(`Could not start errex: ${err.message}. Install with: pip install errex`));
        });

        proc.stdin.write(errorText);
        proc.stdin.end();
    });
}

async function explainViaWebUi(errorText: string, baseUrl: string): Promise<string> {
    // Use built-in fetch (Node 18+) or https module
    const url = `${baseUrl}/explain`;
    const body = JSON.stringify({ error: errorText });

    return new Promise((resolve, reject) => {
        const https = require('https');
        const http = require('http');
        const parsed = new URL(url);
        const mod = parsed.protocol === 'https:' ? https : http;

        const req = mod.request({
            hostname: parsed.hostname,
            port: parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
            path: parsed.pathname,
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) }
        }, (res: any) => {
            let data = '';
            res.on('data', (chunk: Buffer) => { data += chunk; });
            res.on('end', () => {
                try {
                    const json = JSON.parse(data);
                    resolve(json.explanation || data);
                } catch {
                    resolve(data);
                }
            });
        });
        req.on('error', reject);
        req.write(body);
        req.end();
    });
}

function showExplanation(text: string): void {
    // Show in a webview panel for rich rendering
    const panel = vscode.window.createWebviewPanel(
        'errexExplanation',
        'errex Explanation',
        vscode.ViewColumn.Beside,
        { enableScripts: false }
    );

    // Convert markdown-ish output to simple HTML
    const escaped = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); background: var(--vscode-editor-background); padding: 1em 1.5em; line-height: 1.6; }
    pre { background: var(--vscode-textBlockQuote-background); padding: 0.8em; border-radius: 4px; overflow-x: auto; white-space: pre-wrap; }
    h2 { border-bottom: 1px solid var(--vscode-panel-border); padding-bottom: 0.3em; }
  </style>
</head>
<body>
  <h2>errex Explanation</h2>
  <pre>${escaped}</pre>
</body>
</html>`;

    panel.webview.html = html;
}

export function deactivate() {}
