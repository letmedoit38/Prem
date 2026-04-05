@echo off
title Stock Alert Bot - Installation
color 0A
cd /d "%~dp0"

echo.
echo ============================================================
echo   STOCK ALERT BOT - ONE-TIME SETUP
echo ============================================================
echo.

REM ── Check Python ─────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python is not installed or not in PATH.
    echo.
    echo  Please install Python 3.10 or higher from:
    echo    https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: During install, tick "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

echo  Python found:
python --version
echo.

REM ── Upgrade pip ──────────────────────────────────────────────
echo  Upgrading pip...
python -m pip install --upgrade pip --quiet
echo.

REM ── Install dependencies ─────────────────────────────────────
echo  Installing dependencies (this may take 1-2 minutes)...
echo.
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  ERROR: Dependency installation failed.
    echo  Check your internet connection and try again.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   INSTALLATION COMPLETE
echo ============================================================
echo.
echo  Next step: Configure your credentials
echo.
echo  1. In this folder, COPY ".env.example" and RENAME it ".env"
echo  2. Open ".env" in Notepad and fill in:
echo       - TWILIO_ACCOUNT_SID   (from twilio.com)
echo       - TWILIO_AUTH_TOKEN    (from twilio.com)
echo       - WHATSAPP_TO          (your number: whatsapp:+919486196299)
echo       - NGROK_AUTH_TOKEN     (from ngrok.com - free account)
echo.
echo  3. Then double-click START_BOT.bat to run the bot.
echo.
echo  See SETUP_GUIDE.txt for detailed step-by-step instructions.
echo.
pause
