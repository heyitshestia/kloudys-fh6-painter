@echo off
setlocal
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHON312_URL=https://www.python.org/downloads/release/python-31210/"

echo.
echo ============================================================
echo Kloudy's FH6 Painter - Python PATH setup
echo ============================================================
echo.
echo This script only adds Python 3.12 to your user PATH.
echo Run 02_install_dependencies.bat after this.
echo.

call :find_python
if errorlevel 1 (
    echo No usable Python 3.12 installation was found.
    echo.
    echo Install 64-bit Python 3.12 first:
    echo   %PYTHON312_URL%
    echo.
    pause
    exit /b 1
)

echo Using %PYTHON_CMD%
call :add_python_to_path

echo.
echo Python 3.12 and Scripts folders were added to the user PATH.
echo Close and reopen terminals before running 02_install_dependencies.bat.
pause
exit /b 0

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

:add_python_to_path
set "PYTHON_EXE="
for /f "usebackq delims=" %%I in (`%PYTHON_CMD% -c "import sys; print(sys.executable)"`) do set "PYTHON_EXE=%%I"
if not defined PYTHON_EXE exit /b 1
for %%I in ("%PYTHON_EXE%") do set "PYTHON_DIR=%%~dpI"
if not defined PYTHON_DIR exit /b 1
set "PYTHON_DIR=%PYTHON_DIR:~0,-1%"
set "SCRIPTS_DIR=%PYTHON_DIR%\Scripts"
echo.
echo Ensuring Python is on PATH...
setx PATH "%PATH%;%PYTHON_DIR%;%SCRIPTS_DIR%" >nul
exit /b 0
