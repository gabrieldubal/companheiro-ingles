@echo off
rem Instala o Companheiro de ingles: Python, bibliotecas e os modelos de voz. Nao precisa ser administrador.
rem Para atualizar: descompacte a versao nova por cima desta pasta e rode este arquivo de novo.
chcp 65001 >nul
cd /d "%~dp0"
setlocal
if not defined COMPANHEIRO_DATA set "COMPANHEIRO_DATA=%LOCALAPPDATA%\CompanheiroIngles"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"
set "PYTHONUTF8=1"

echo.
echo   Companheiro de ingles: instalacao
echo   Na primeira vez leva de 10 a 30 minutos e baixa uns 2 GB. Deixe esta janela aberta.
echo.

where uv >nul 2>nul
if errorlevel 1 (
  echo   [1/4] Baixando o uv, que instala o Python sem mexer no resto do computador...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)
where uv >nul 2>nul || goto erro

echo   [2/4] Preparando o Python...
if not exist ".venv\Scripts\python.exe" (
  uv venv --python 3.12 .venv || goto erro
)

echo   [3/4] Instalando as bibliotecas (a maior e o PyTorch, uns 200 MB)...
uv pip install --python .venv\Scripts\python.exe torch --index-url https://download.pytorch.org/whl/cpu || goto erro
uv pip install --python .venv\Scripts\python.exe -r requirements.txt || goto erro

echo   [4/4] Baixando os modelos de voz...
.venv\Scripts\python.exe -m app.preparar || goto erro

echo.
echo   Pronto! Para abrir o app: dois cliques em abrir.bat
echo.
pause
exit /b 0

:erro
echo.
echo   Algo deu errado na instalacao. Tire um print desta janela inteira e mande para quem te passou o app.
echo.
pause
exit /b 1
