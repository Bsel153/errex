#!/usr/bin/env bash
# errex installer — Mac & Linux
# Usage: curl -sSL https://raw.githubusercontent.com/Bsel153/errex/main/scripts/install.sh | bash

set -e

BOLD="\033[1m"
RED="\033[31m"
GREEN="\033[32m"
CYAN="\033[36m"
RESET="\033[0m"

echo ""
echo -e "${BOLD}  errex installer${RESET}"
echo "  ──────────────────────────────"

# ── Check Python ──────────────────────────────────────────────────────────────
if command -v python3 &>/dev/null; then
    PY=python3
elif command -v python &>/dev/null; then
    PY=python
else
    echo -e "${RED}  ✗ Python not found.${RESET}"
    echo ""
    echo "  Install Python first:"
    echo "    Mac:   brew install python  (or https://python.org)"
    echo "    Linux: sudo apt install python3"
    exit 1
fi

PY_VER=$($PY -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo -e "${GREEN}  ✓ Python ${PY_VER}${RESET}"

# ── Install errex ─────────────────────────────────────────────────────────────
echo "  Installing errex…"
$PY -m pip install --upgrade errex --quiet
echo -e "${GREEN}  ✓ errex installed${RESET}"

# ── API key ───────────────────────────────────────────────────────────────────
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo ""
    echo -e "  ${BOLD}Anthropic API key${RESET} (needed to explain errors)"
    echo -e "  Get one free at ${CYAN}https://console.anthropic.com/${RESET}"
    echo -n "  Paste your API key (or press Enter to skip): "
    read -r API_KEY
    if [ -n "$API_KEY" ]; then
        SHELL_RC=""
        if [ -f "$HOME/.zshrc" ]; then SHELL_RC="$HOME/.zshrc"
        elif [ -f "$HOME/.bashrc" ]; then SHELL_RC="$HOME/.bashrc"
        elif [ -f "$HOME/.bash_profile" ]; then SHELL_RC="$HOME/.bash_profile"
        fi
        if [ -n "$SHELL_RC" ]; then
            echo "" >> "$SHELL_RC"
            echo "export ANTHROPIC_API_KEY=\"$API_KEY\"" >> "$SHELL_RC"
            export ANTHROPIC_API_KEY="$API_KEY"
            echo -e "${GREEN}  ✓ API key saved to ${SHELL_RC}${RESET}"
        else
            export ANTHROPIC_API_KEY="$API_KEY"
            echo -e "${GREEN}  ✓ API key set for this session${RESET}"
        fi
    fi
fi

# ── Desktop shortcut ──────────────────────────────────────────────────────────
echo ""
echo -n "  Create a desktop shortcut to open errex? [Y/n]: "
read -r SHORTCUT
if [[ "$SHORTCUT" =~ ^[Nn]$ ]]; then
    echo "  Skipped."
else
    $PY -m errex --create-shortcut 2>/dev/null && \
        echo -e "${GREEN}  ✓ Desktop shortcut created${RESET}" || \
        echo "  (Shortcut creation skipped — run 'errex --create-shortcut' later)"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "  ${GREEN}${BOLD}All done!${RESET}"
echo ""
echo "  Open the dashboard:    errex --web"
echo "  Explain an error:      errex --explain 'your error here'"
echo "  Run a security scan:   errex --scan"
echo ""
