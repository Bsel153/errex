#!/usr/bin/env bash
# Build errex.app and errex.dmg for macOS
# Usage: bash scripts/build_mac.sh
set -e

BOLD="\033[1m"
GREEN="\033[32m"
RESET="\033[0m"

echo -e "${BOLD}  errex macOS build${RESET}"
echo "  ──────────────────────────────"

# Install build deps
echo "  Installing build dependencies…"
PIP=$(command -v pip3 || command -v pip)
$PIP install --quiet pyinstaller pywebview

# Clean previous build
rm -rf dist/errex.app dist/errex build/errex

# Run PyInstaller
echo "  Running PyInstaller…"
pyinstaller errex.spec --clean --noconfirm

APP="dist/errex.app"
DMG="dist/errex.dmg"

if [ ! -d "$APP" ]; then
    echo "  ✗ Build failed — dist/errex.app not found"
    exit 1
fi
echo -e "${GREEN}  ✓ Built: $APP${RESET}"

# Create .dmg
echo "  Creating disk image…"
rm -f "$DMG"
hdiutil create -volname errex -srcfolder "$APP" -ov -format UDZO "$DMG" >/dev/null
echo -e "${GREEN}  ✓ Built: $DMG${RESET}"

echo ""
echo "  Distribute dist/errex.dmg — users drag errex.app to /Applications"
echo ""
