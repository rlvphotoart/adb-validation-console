@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if not errorlevel 1 (
    python adb_validation_console.py
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 adb_validation_console.py
    ) else (
        echo Python 3 was not found. Install Python 3 with tkinter or use AdbValidationConsole.exe.
    )
)
if errorlevel 1 pause
