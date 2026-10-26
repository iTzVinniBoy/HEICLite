@echo off
cd /d "%~dp0"
if exist "dist\versao-2.11\HEICLite.exe" (
    start "" "dist\versao-2.11\HEICLite.exe"
    exit /b
)
if not exist ".venv\Scripts\pythonw.exe" (
    echo Execute instalar.bat primeiro.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "app.py"
