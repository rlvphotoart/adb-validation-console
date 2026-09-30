@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m PyInstaller --noconfirm --clean --onefile --windowed --name AdbValidationConsole adb_validation_console.py
) else (
    python -m PyInstaller --noconfirm --clean --onefile --windowed --name AdbValidationConsole adb_validation_console.py
)
if errorlevel 1 (
    echo Build failed. Install PyInstaller with: py -3 -m pip install pyinstaller
    pause
    exit /b 1
)
echo Built dist\AdbValidationConsole.exe
pause
