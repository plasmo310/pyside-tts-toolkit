@echo off
REM TTS Toolkit (CLI) doctor: check that the environment is ready.
REM Usage: scripts\win\RunDoctor.bat

set SCRIPT_DIR=%~dp0
set ROOT_DIR=%SCRIPT_DIR%..\..

set PYTHON_EXE=%ROOT_DIR%\.venvs\common\Scripts\python.exe
if not exist "%PYTHON_EXE%" (
    echo Not found python env. Please execute 'scripts\win\SetupEngines.ps1'.
    pause
    exit /b 1
)

set PYTHONDONTWRITEBYTECODE=1

"%PYTHON_EXE%" -m ttstoolkit.cli doctor %*
exit /b %ERRORLEVEL%
