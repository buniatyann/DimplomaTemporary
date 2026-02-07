@echo off
REM ──────────────────────────────────────────────────────────────
REM run_gui.bat — Launch the PySide6 GUI for Hardware Trojan Detector (Windows)
REM ──────────────────────────────────────────────────────────────

cd /d "%~dp0\.."

echo ================================================
echo   Hardware Trojan Detector - GUI Launcher
echo ================================================
echo.

REM Check if virtual environment exists
if not exist ".venv\" (
    echo [ERROR] Virtual environment not found!
    echo Please run windows\setup.ps1 first to set up the project.
    echo.
    pause
    exit /b 1
)

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Check if PySide6 is installed
python -c "import PySide6" 2>nul
if errorlevel 1 (
    echo [ERROR] PySide6 not found!
    echo Install GUI dependencies with: pip install trojan-detector[gui]
    echo.
    pause
    exit /b 1
)

echo [INFO] Launching GUI...
echo.
python -m main

pause
