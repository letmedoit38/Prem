@echo off
echo ============================================
echo   PREM BOT - Step 1: Install Dependencies
echo ============================================
echo.

echo [1/4] Upgrading pip...
python.exe -m pip install --upgrade pip

echo.
echo [2/4] Installing numpy (pre-built binary)...
pip install "numpy>=1.24.0,<2.0.0" --only-binary :all:

echo.
echo [3/4] Installing pandas (pre-built binary)...
pip install "pandas>=2.0.0,<3.0.0" --only-binary :all:

echo.
echo [4/4] Installing remaining dependencies...
pip install kiteconnect==5.0.1 pandas-ta==0.3.14b0 APScheduler==3.10.4 python-dotenv==1.0.1 pyotp==2.9.0 requests==2.31.0 pytz==2024.1 holidays==0.46 websocket-client==1.8.0 loguru==0.7.2 colorama==0.4.6

echo.
echo ============================================
echo   Done! Now run: 2_CONFIGURE.bat
echo ============================================
pause
