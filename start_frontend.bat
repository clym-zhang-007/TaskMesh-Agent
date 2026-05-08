@echo off
echo ========================================
echo Starting Agent Loop Frontend
echo ========================================
cd /d "%~dp0frontend"
echo Working directory: %CD%
echo.
echo Installing dependencies...
call npm install
echo.
echo Starting dev server...
call npm run dev
