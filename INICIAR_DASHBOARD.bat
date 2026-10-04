@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PYTHON=py -3"
) else (
  set "PYTHON=python"
)

if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente Python...
  %PYTHON% -m venv .venv
  if errorlevel 1 goto :python_error
)

call .venv\Scripts\activate.bat
echo Instalando/verificando dependencias...
python -m pip install -r requirements.txt
if errorlevel 1 goto :install_error

set "DATABASE_BACKEND="
echo.
echo Iniciando camera e dashboard.
echo Neste computador: http://127.0.0.1:5000
echo Em outro PC/monitor na mesma rede Wi-Fi, use um destes enderecos:
for /f "tokens=2 delims=:" %%A in ('ipconfig ^| findstr /c:"IPv4"') do (
  echo   http://%%A:5000
)
echo (remova espacos do inicio do endereco acima, se houver)
python scripts\dashboard.py --host 0.0.0.0
goto :end

:python_error
echo.
echo Nao foi possivel criar o ambiente. Instale Python 3.10 ou superior e tente novamente.
pause
goto :end

:install_error
echo.
echo Nao foi possivel instalar as dependencias. Verifique a internet e tente novamente.
pause

:end
endlocal
