@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -c "import app; import PyInstaller.__main__; PyInstaller.__main__.run(['--noconfirm', '--clean', '--onefile', '--windowed', '--name', 'Conversor HEIC JPEG', '--distpath', 'dist/versao-1.2', 'app.py'])"
if errorlevel 1 (
    echo Falha ao gerar o executavel.
) else (
    echo Executavel disponivel na pasta dist.
)
pause
