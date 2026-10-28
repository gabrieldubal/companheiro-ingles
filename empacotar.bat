@echo off
rem Lança uma versão para os amigos (sem nada seu) na pasta dist.
rem   empacotar.bat 2.2.0      fecha a versão no CHANGELOG.md, sobe o VERSION e gera o zip
rem   empacotar.bat            refaz o zip da versão atual, se ele não estiver em dist
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
".venv\Scripts\python.exe" tools\empacotar.py %*
pause
