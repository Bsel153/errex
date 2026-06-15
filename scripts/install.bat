@echo off
:: errex installer — Windows
:: Run in PowerShell: iwr https://raw.githubusercontent.com/Bsel153/errex/main/scripts/install.bat -OutFile install.bat; .\install.bat

title errex Installer
echo.
echo   errex installer
echo   --------------------------------

:: ── Check Python ──────────────────────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   Python not found.
    echo.
    echo   Download and install Python from https://python.org
    echo   Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo   Python %PY_VER% found

:: ── Install errex ─────────────────────────────────────────────────────────────
echo   Installing errex...
python -m pip install --upgrade errex --quiet
if %errorlevel% neq 0 (
    echo   Install failed. Try running as Administrator.
    pause
    exit /b 1
)
echo   errex installed

:: ── API key ───────────────────────────────────────────────────────────────────
if "%ANTHROPIC_API_KEY%"=="" (
    echo.
    echo   Anthropic API key (needed to explain errors)
    echo   Get one free at https://console.anthropic.com/
    set /p API_KEY="  Paste your API key (or press Enter to skip): "
    if not "!API_KEY!"=="" (
        setx ANTHROPIC_API_KEY "!API_KEY!" >nul
        echo   API key saved.
    )
)

:: ── Desktop shortcut ──────────────────────────────────────────────────────────
echo.
set /p SHORTCUT="  Create a desktop shortcut? [Y/n]: "
if /i not "%SHORTCUT%"=="n" (
    python -m errex --create-shortcut
    if %errorlevel% equ 0 (
        echo   Desktop shortcut created.
    ) else (
        echo   Run 'errex --create-shortcut' later to create a shortcut.
    )
)

:: ── Done ──────────────────────────────────────────────────────────────────────
echo.
echo   All done!
echo.
echo   Open the dashboard:    errex --web
echo   Explain an error:      errex --explain "your error here"
echo   Run a security scan:   errex --scan
echo.
pause
