@echo off
echo ============================================
echo   EMERGENCY: CLOSE ALL OPEN POSITIONS NOW
echo ============================================
echo.
echo WARNING: This will immediately close ALL open trades.
echo Press any key to proceed or close this window to cancel.
pause
python main.py --squareoff
pause
