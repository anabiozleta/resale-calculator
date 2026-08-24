@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
    py -3 calculator_reselling.py
    if errorlevel 1 pause
    exit /b
)

where python >nul 2>nul
if not errorlevel 1 (
    python calculator_reselling.py
    if errorlevel 1 pause
    exit /b
)

echo Python 3 not found. Install it from https://www.python.org/downloads/
pause
