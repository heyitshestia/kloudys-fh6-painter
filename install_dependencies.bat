@echo off
setlocal
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHON312_URL=https://www.python.org/downloads/release/python-31210/"

echo.
echo ============================================================
echo Kloudy's FH6 Painter setup
echo.
echo BEFORE doing anything else:
echo   1. Install 64-bit Python 3.12
echo   2. Run add_python312_to_path.bat
echo   3. Run install_dependencies.bat
echo   4. Only then run start_app.bat
echo ============================================================
echo.

call :find_python
if errorlevel 1 (
    echo No usable Python 3.12 installation was found.
    echo.
    echo Download 64-bit Python 3.12 from:
    echo   %PYTHON312_URL%
    echo.
    echo Then run add_python312_to_path.bat, then install_dependencies.bat.
    pause
    exit /b 1
)

echo Using %PYTHON_CMD%
%PYTHON_CMD% -m pip install --upgrade pip
if errorlevel 1 goto Failed

%PYTHON_CMD% -m pip install "psutil>=5.9.0"
if errorlevel 1 goto Failed

%PYTHON_CMD% -m pip install -r requirements.txt
if errorlevel 1 goto Failed

echo.
echo Installing V2 generation and preview dependencies...
%PYTHON_CMD% -m pip install -r requirements-preview.txt
if errorlevel 1 (
    echo V2 generation/preview dependencies failed to install.
    echo Check the Python version and network, then try again.
    goto Failed
)

echo.
echo Dependencies installed.
echo You can now run start_app.bat
pause
exit /b 0

:Failed
echo.
echo Dependency installation failed.
echo This project expects 64-bit Python 3.12:
echo   %PYTHON312_URL%
echo If Python is installed but still not found, run add_python312_to_path.bat first.
pause
exit /b 1

:find_python
py -3.12 -c "import sys; raise SystemExit(0 if sys.maxsize > 2**32 else 1)" >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=py -3.12"
    exit /b 0
)
python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32 else 1)" >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    exit /b 0
)
exit /b 1
