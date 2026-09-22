@echo off
REM Build TTS Toolkit into build_env\scripts\win\dist.

set SCRIPT_DIR=%~dp0
set BUILD_ENV_DIR=%SCRIPT_DIR%..\..
set ROOT_DIR=%BUILD_ENV_DIR%\..
pushd "%BUILD_ENV_DIR%"

set VENV_DIR=%BUILD_ENV_DIR%\.venv
set PYTHON_EXE=%VENV_DIR%\Scripts\python.exe
if not exist "%PYTHON_EXE%" (
    echo Not found python env. Please execute 'build_env\scripts\win\Setup.bat'.
    pause
    exit /b 1
)

set PYTHONDONTWRITEBYTECODE=1
set PYTHON_SRC_DIR=%ROOT_DIR%\python
set RESOURCES_DIR=%ROOT_DIR%\resources

call "%VENV_DIR%\Scripts\activate"

set BUILD_TMP_DIR=%SCRIPT_DIR%build
set BUILD_DIST_DIR=%SCRIPT_DIR%dist

set EXE_NAME=TTSToolkit
set ICON_PATH=%RESOURCES_DIR%\icon\tool_icon_rect.ico

REM References: https://pyinstaller.org/en/stable/usage.html
REM
REM --add-data "%PYTHON_SRC_DIR%;.\python" bundles the raw .py sources
REM (not just compiled into the exe). Each engine runs as a subprocess
REM in its own venv and imports "ttstoolkit.engine.*" from that source
REM via PYTHONPATH, so it needs real files on disk (see PYTHON_DIR in
REM core/paths.py).
pyinstaller --noconsole --onedir --name %EXE_NAME% ^
    --paths "%PYTHON_SRC_DIR%" ^
    --hidden-import "PySide6" ^
    --add-data "%RESOURCES_DIR%;.\resources" ^
    --add-data "%PYTHON_SRC_DIR%;.\python" ^
    --icon "%ICON_PATH%" ^
    --distpath "%BUILD_DIST_DIR%" --workpath "%BUILD_TMP_DIR%" ^
    "%BUILD_ENV_DIR%\python\run.py"

popd

REM Clean up.
powershell -Command "Remove-Item -Recurse -Force '%BUILD_TMP_DIR%' -ErrorAction SilentlyContinue"
powershell -Command "Get-ChildItem -Recurse -Filter '__pycache__' '%PYTHON_SRC_DIR%' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue"

echo Complete build app.
pause
