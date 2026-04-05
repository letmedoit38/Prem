@echo off
title Stock Alert Bot - Running
color 0A
cd /d "%~dp0"

echo.
echo ============================================================
echo   STOCK ALERT BOT - STARTING
echo ============================================================
echo.

REM ── Check .env exists ────────────────────────────────────────
if not exist ".env" (
    echo  ERROR: .env file not found!
    echo.
    echo  Please copy .env.example to .env and fill in your credentials.
    echo  See SETUP_GUIDE.txt for instructions.
    echo.
    pause
    exit /b 1
)

REM ── Check Python ─────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found. Run INSTALL.bat first.
    pause
    exit /b 1
)

echo  Starting bot...
echo  Press Ctrl+C to stop.
echo.
echo  Watch this window for activity logs.
echo  You will receive a WhatsApp message on +91 9486196299 shortly.
echo.
echo ============================================================
echo.

python bot.py

echo.
echo  Bot stopped.
pause
