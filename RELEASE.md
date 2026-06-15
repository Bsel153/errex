# Release Guide

## Bump versions

1. Update `version` in `pyproject.toml`:
   ```toml
   [project]
   version = "X.Y.Z"
   ```

2. If the VS Code extension exists, update `version` in `extensions/vscode/package.json`:
   ```json
   { "version": "X.Y.Z" }
   ```

## Publish via GitHub Release (recommended)

Creating a GitHub Release automatically triggers both publishing workflows:

- **PyPI** (`publish-pypi.yml`) — builds and publishes the Python package
- **VS Code** (`publish-vscode.yml`) — packages and publishes the extension

Steps:
1. Commit and push version bumps.
2. Go to **GitHub → Releases → Draft a new release**.
3. Create a tag (e.g. `v0.20.0`), fill in the release notes, and click **Publish release**.
4. Both workflows start automatically. Monitor them under **Actions**.

## First-time setup: PyPI Trusted Publishing (OIDC — no token needed)

1. Log in to [pypi.org](https://pypi.org) and go to **Account settings → Publishing**.
   Direct link: <https://pypi.org/manage/account/publishing/>
2. Add a new trusted publisher with:
   - **Owner**: `Bsel153`
   - **Repository**: `errex`
   - **Workflow filename**: `publish-pypi.yml`
   - **Environment**: `pypi`
3. Create the `pypi` environment in **GitHub → Settings → Environments**.
   No secrets required — authentication uses OIDC.

## First-time setup: VS Code Marketplace

1. Get a Personal Access Token (PAT) from
   <https://marketplace.visualstudio.com/manage>.
   Scope: **Marketplace → Manage**.
2. Add the PAT as a GitHub repository secret named `VSCE_PAT`:
   **GitHub → Settings → Secrets and variables → Actions → New repository secret**.

## Manual fallback commands

**PyPI:**
```bash
pip install build twine
python -m build
twine upload dist/*
# Prompted for username (__token__) and API token, or set TWINE_USERNAME / TWINE_PASSWORD.
```

**VS Code Extension:**
```bash
cd extensions/vscode
npm install
npm run compile
npx vsce package --no-dependencies
npx vsce publish --packagePath *.vsix
# Requires VSCE_PAT env var or interactive login.
```
