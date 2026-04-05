@echo off
title Stock Alert Bot - Dashboard
color 0B
cd /d "%~dp0"

echo.
echo ============================================================
echo   STOCK ALERT BOT - WEB DASHBOARD
echo ============================================================
echo.

if not exist ".env" (
    echo  WARNING: .env not found. WhatsApp features will not work.
    echo  Copy .env.example to .env and fill in your credentials.
    echo.
)

python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found. Run INSTALL.bat first.
    pause
    exit /b 1
)

echo  Starting dashboard...
echo  Opening browser at http://localhost:5001
echo  Press Ctrl+C to stop.
echo.
echo ============================================================
echo.

REM Open browser after a short delay
start "" timeout /t 2 >nul && start "" "http://localhost:5001"

python dashboard.py

echo.
echo  Dashboard stopped.
pause
