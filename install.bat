@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m pip install -r requirements.txt
    pause
    exit /b
)

where python >nul 2>nul
if not errorlevel 1 (
    python -m pip install -r requirements.txt
    pause
    exit /b
)

echo Python 3 not found. Install it from https://www.python.org/downloads/
pause
