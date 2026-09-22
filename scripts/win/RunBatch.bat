@echo off
REM TTS Toolkit (CLI) batch: synthesize every line in a JSON file.
REM Usage: scripts\win\RunBatch.bat -e qwen sample.ja.json

set SCRIPT_DIR=%~dp0
set ROOT_DIR=%SCRIPT_DIR%..\..

set PYTHON_EXE=%ROOT_DIR%\.venvs\common\Scripts\python.exe
if not exist "%PYTHON_EXE%" (
    echo Not found python env. Please execute 'scripts\win\SetupEngines.ps1'.
    pause
    exit /b 1
)

set PYTHONDONTWRITEBYTECODE=1

"%PYTHON_EXE%" -m ttstoolkit.cli batch %*
exit /b %ERRORLEVEL%
