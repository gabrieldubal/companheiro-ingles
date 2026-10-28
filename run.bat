@echo off
rem Liga o companheiro de ingles no PC e abre o navegador. Deixe esta janela aberta.
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
".venv\Scripts\python.exe" -m app.server %*
pause
