@echo off
rem Roda um comando com as credenciais do .env da pasta do app carregadas so para ele.
rem Nada e gravado em perfil do AWS CLI, e o .env nao sai da sua maquina.
rem Uso:
rem   infra\com-env.bat aws sts get-caller-identity
rem   infra\com-env.bat terraform -chdir=infra\terraform plan
rem   infra\com-env.bat python infra\chaves.py listar
setlocal
set "ENVFILE=%~dp0..\.env"
if not exist "%ENVFILE%" (
  echo Nao achei o .env em "%ENVFILE%".
  exit /b 1
)
rem Linhas KEY=valor; linhas com # sao comentario; aspas em volta do valor sao tiradas.
for /f "usebackq eol=# tokens=1,* delims==" %%a in ("%ENVFILE%") do set "%%a=%%~b"
if not defined AWS_DEFAULT_REGION if defined AWS_REGION set "AWS_DEFAULT_REGION=%AWS_REGION%"
if not defined AWS_DEFAULT_REGION set "AWS_DEFAULT_REGION=us-east-1"
rem Garante que um perfil antigo do AWS CLI nao passe na frente das credenciais do .env.
set "AWS_PROFILE="
%*
