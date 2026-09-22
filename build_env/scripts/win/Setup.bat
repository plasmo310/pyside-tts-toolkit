@echo off
REM Create the build venv (app dependencies + PyInstaller).

set SCRIPT_DIR=%~dp0
set BUILD_ENV_DIR=%SCRIPT_DIR%..\..
set VENV_DIR=%BUILD_ENV_DIR%\.venv

set PYVER=3.12

REM Find Python.
set PYTHON_CMD=
py -%PYVER% -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=py -%PYVER%
) else (
    call python --version 2>nul | findstr /r "^Python %PYVER%\." >nul
    if not errorlevel 1 set PYTHON_CMD=python
)
if "%PYTHON_CMD%"=="" (
    echo Python %PYVER% not found. Please install Python %PYVER%.
    pause
    exit /b 1
)

%PYTHON_CMD% -m venv "%VENV_DIR%"
call "%VENV_DIR%\Scripts\Activate"
python -m pip install --upgrade pip

REM `-e ..` in requirements.txt is resolved relative to the current
REM directory, so install from inside build_env\.
pushd "%BUILD_ENV_DIR%"
pip install -r requirements.txt
popd

echo Complete setup build env.
pause
