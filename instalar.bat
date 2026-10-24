@echo off
cd /d "%~dp0"
python -m venv .venv
if errorlevel 1 goto erro
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto erro
echo Instalacao concluida. Abra iniciar.bat.
pause
exit /b 0
:erro
echo Nao foi possivel instalar. Verifique se o Python 3.13 esta instalado e se ha conexao com a internet.
pause
exit /b 1
