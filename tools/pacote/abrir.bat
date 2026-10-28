@echo off
rem Abre o Companheiro de ingles no navegador. Deixe esta janela aberta enquanto usa.
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo   O app ainda nao foi instalado. Rode primeiro o instalar.bat.
  pause
  exit /b 1
)
rem Os seus dados ficam fora desta pasta: atualizar o app (descompactar por cima) nao mexe neles.
if not defined COMPANHEIRO_DATA set "COMPANHEIRO_DATA=%LOCALAPPDATA%\CompanheiroIngles"
set "PYTHONUTF8=1"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"
".venv\Scripts\python.exe" -m app.server %*
pause
