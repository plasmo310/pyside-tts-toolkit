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
set IRODORI_PYTHON=%ROOT_DIR%\.venvs\engine-irodori\Scripts\python.exe
set IRODORI_VENDOR=%ROOT_DIR%\engine_env\irodori\vendor\Irodori-TTS

for /f "delims=" %%I in ('where uv 2^>nul') do if not defined UV_EXE set "UV_EXE=%%I"
if not defined UV_EXE (
    echo Not found uv. Install uv and run this build again.
    pause
    exit /b 1
)

REM Irodori is not importable from PyPI. The built GUI starts it from a
REM separate venv and needs the checked-out upstream source at runtime.
REM Fail before building rather than producing an app that cannot run Irodori.
if not exist "%IRODORI_PYTHON%" (
    echo Not found Irodori environment: %IRODORI_PYTHON%
    echo Please execute scripts\win\SetupEngines.ps1 -Targets irodori first.
    pause
    exit /b 1
)
if not exist "%IRODORI_VENDOR%\irodori_tts" (
    echo Not found Irodori source: %IRODORI_VENDOR%
    echo Please execute scripts\win\SetupEngines.ps1 -Targets irodori first.
    pause
    exit /b 1
)

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
if errorlevel 1 goto :error

REM Include all engines and the locked sources used to restore an engine from
REM the GUI if its environment is removed after distribution.
for %%E in (qwen chatterbox irodori) do (
    if not exist "%ROOT_DIR%\.venvs\engine-%%E\Scripts\python.exe" (
        echo Not found %%E environment. Run SetupEngines.ps1 -Targets %%E first.
        goto :error
    )
    robocopy "%ROOT_DIR%\.venvs\engine-%%E" "%BUILD_DIST_DIR%\%EXE_NAME%\.venvs\engine-%%E" /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /NFL /NDL
    if errorlevel 8 goto :error
)
robocopy "%ROOT_DIR%\engine_env" "%BUILD_DIST_DIR%\%EXE_NAME%\engine_env" /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /NFL /NDL
if errorlevel 8 goto :error
if not exist "%BUILD_DIST_DIR%\%EXE_NAME%\tools" mkdir "%BUILD_DIST_DIR%\%EXE_NAME%\tools"
copy /Y "%UV_EXE%" "%BUILD_DIST_DIR%\%EXE_NAME%\tools\uv.exe" >nul
if errorlevel 1 goto :error

popd

REM Clean up.
powershell -Command "Remove-Item -Recurse -Force '%BUILD_TMP_DIR%' -ErrorAction SilentlyContinue"
powershell -Command "Get-ChildItem -Recurse -Filter '__pycache__' '%PYTHON_SRC_DIR%' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue"

echo Complete build app.
pause
exit /b 0

:error
popd
echo Build failed.
pause
exit /b 1
