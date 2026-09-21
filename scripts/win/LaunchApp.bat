@echo off
REM TTS Toolkit (GUI) launcher.

set SCRIPT_DIR=%~dp0
set ROOT_DIR=%SCRIPT_DIR%..\..

set PYTHON_EXE=%ROOT_DIR%\.venvs\common\Scripts\pythonw.exe
if not exist "%PYTHON_EXE%" (
    echo Not found python env. Please execute 'scripts\win\setup_engines.ps1'.
    pause
    exit /b 1
)

set PYTHONDONTWRITEBYTECODE=1

start "" /b "%PYTHON_EXE%" -m ttstoolkit.main
