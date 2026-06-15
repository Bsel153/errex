@echo off
:: Build errex.exe for Windows
:: Usage: scripts\build_win.bat
title errex Windows Build
echo.
echo   errex Windows build
echo   ──────────────────────────────

echo   Installing build dependencies...
pip install --quiet pyinstaller pywebview
if %errorlevel% neq 0 (echo   Install failed & exit /b 1)

echo   Running PyInstaller...
pyinstaller errex.spec --clean --noconfirm
if %errorlevel% neq 0 (echo   PyInstaller failed & exit /b 1)

if not exist "dist\errex\errex.exe" (
    echo   Build failed — dist\errex\errex.exe not found
    exit /b 1
)

echo   Built: dist\errex\errex.exe
echo.
echo   Zip dist\errex\ to distribute — users extract and double-click errex.exe
echo.
