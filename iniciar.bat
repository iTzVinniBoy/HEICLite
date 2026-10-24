@echo off
cd /d "%~dp0"
if exist "dist\versao-1.2\Conversor HEIC JPEG.exe" (
    start "" "dist\versao-1.2\Conversor HEIC JPEG.exe"
    exit /b
)
if exist "dist\Conversor HEIC JPEG.exe" (
    start "" "dist\Conversor HEIC JPEG.exe"
    exit /b
)
if not exist ".venv\Scripts\pythonw.exe" (
    echo Execute instalar.bat primeiro.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "app.py"
