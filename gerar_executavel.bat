@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" build_app.py
if errorlevel 1 (
    echo Falha ao gerar o executavel.
) else (
    echo Executavel disponivel na pasta dist.
)
pause
