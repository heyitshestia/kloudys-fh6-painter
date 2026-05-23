@echo off
setlocal
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"

call :find_python
if errorlevel 1 (
    echo No usable Python was found. Install 64-bit Python 3.10 to 3.13, then run this again.
    pause
    exit /b 1
)

echo Using %PYTHON_CMD%
%PYTHON_CMD% -m pip install --upgrade pip
if errorlevel 1 goto Failed

%PYTHON_CMD% -m pip install -r requirements.txt
if errorlevel 1 goto Failed

%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info < (3, 13) else 1)" >nul 2>nul
if errorlevel 1 (
    echo.
    echo Python 3.13 or newer was detected.
    echo.
    echo This project now uses the V2 Python generator backend.
    echo V2 generation and all image/JSON previews require:
    echo   - numpy
    echo   - opencv-python
    echo   - Pillow
    echo.
    echo Those wheels are not installed by this script on Python 3.13+.
    echo Import-only features may still work, but generation and preview will be limited.
    echo For the full app, use 64-bit Python 3.12.
) else (
    echo.
    echo Installing V2 generation and preview dependencies...
    %PYTHON_CMD% -m pip install -r requirements-preview.txt
    if errorlevel 1 (
        echo V2 generation/preview dependencies failed to install.
        echo Import may still work, but generation and previews will be limited.
    )
)

echo.
echo Dependencies installed.
pause
exit /b 0

:Failed
echo.
echo Dependency installation failed. Check the Python version and network, then try again.
pause
exit /b 1

:find_python
for %%V in (3.12 3.11 3.10 3.13) do (
    py -%%V -c "import sys; raise SystemExit(0 if sys.maxsize > 2**32 else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=py -%%V"
        exit /b 0
    )
)
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) and sys.maxsize > 2**32 else 1)" >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    exit /b 0
)
exit /b 1
