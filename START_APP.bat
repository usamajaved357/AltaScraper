@echo off
REM ============================================================
REM  Miles / Listing Generator - one-click launcher
REM  Double-click this file to start the dashboard.
REM  A browser tab opens automatically at http://127.0.0.1:5000
REM  To STOP: just close this black window (the X in the corner).
REM ============================================================

title Listing Generator - KEEP THIS WINDOW OPEN (close it to stop the app)

REM Move into the folder this .bat lives in, whatever the drive/path.
cd /d "%~dp0"

echo ============================================================
echo   Starting Listing Generator ...
echo   Keep this window OPEN while you use the app.
echo   To STOP the app, simply CLOSE this window.
echo ============================================================
echo.

REM Open the browser to the app after a short delay, in the background.
start "" /min cmd /c "timeout /t 3 >nul & start http://127.0.0.1:5000"

REM Start the app. Try the Python launcher with 3.11 first; fall back
REM to plain python if the launcher/version isn't available.
py -3.11 dashboard.py
if errorlevel 1 (
  echo.
  echo  py -3.11 not found, trying plain python ...
  python dashboard.py
)

echo.
echo ============================================================
echo   The app has stopped. You can close this window.
echo ============================================================
pause
