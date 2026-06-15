# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for errex standalone app
# Mac:     pyinstaller errex.spec --clean  → dist/errex.app + dist/errex.dmg
# Windows: pyinstaller errex.spec --clean  → dist/errex/errex.exe

import sys
_is_mac = sys.platform == "darwin"
_is_win = sys.platform == "win32"

a = Analysis(
    ["errex_app.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=[
        # errex package
        "errex",
        "errex.cli",
        "errex.web_ui",
        "errex.app_window",
        "errex.core",
        "errex.history",
        "errex.config",
        "errex.output",
        "errex.scan",
        "errex.tickets",
        "errex.ticketing",
        "errex.cache",
        "errex.code_tools",
        "errex.explainers",
        "errex.patterns",
        "errex.watch",
        "errex.utils",
        "errex.setup_tools",
        "errex.security",
        "errex.verify",
        "errex.email_report",
        "errex.github_sync",
        "errex.discord_notify",
        "errex.digest",
        "errex.mcp_server",
        "errex.launcher",
        "errex._constants",
        "errex._paths",
        "errex._first_run",
        "errex._scan_scheduler",
        "errex.init_cmd",
        # scanners
        "errex.scanners",
        "errex.scanners._base",
        "errex.scanners.malware",
        "errex.scanners.clamav",
        "errex.scanners.cve",
        "errex.scanners.virustotal",
        "errex.scanners.linux",
        "errex.scanners.macos",
        "errex.scanners.windows",
        "errex.scanners.network",
        # dependencies
        "anthropic",
        "rich",
        "rich.console",
        "rich.panel",
        "rich.table",
        "rich.progress",
        # webview backends — PyInstaller needs all candidates at collect time
        "webview",
        "webview.platforms",
        "webview.platforms.cocoa",
        "webview.platforms.winforms",
        "webview.platforms.edgechromium",
        "webview.platforms.gtk",
        # stdlib that PyInstaller sometimes misses
        "http.server",
        "ssl",
        "email.mime.multipart",
        "email.mime.text",
        "smtplib",
        "xml.etree.ElementTree",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="errex",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="errex",
)

if _is_mac:
    app = BUNDLE(
        coll,
        name="errex.app",
        icon=None,
        bundle_identifier="com.errex.app",
        info_plist={
            "CFBundleName": "errex",
            "CFBundleDisplayName": "errex",
            "CFBundleVersion": "0.23.0",
            "CFBundleShortVersionString": "0.23.0",
            "CFBundleExecutable": "errex",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            "NSHumanReadableCopyright": "MIT License",
        },
    )
