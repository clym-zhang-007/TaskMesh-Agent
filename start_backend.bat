@echo off
echo ========================================
echo Starting Agent Loop Backend
echo ========================================
cd /d "%~dp0"
echo Working directory: %CD%
echo.
echo Installing dependencies...
pip install -q -r backend\requirements.txt
echo.
echo Starting server...
python backend\main.py
