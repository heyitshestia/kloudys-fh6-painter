@echo off
setlocal
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
call :find_python
if errorlevel 1 (
    echo No usable Python 3.12 was found. Install 64-bit Python 3.12 first.
    echo Then run 01_add_python312_to_path.bat and 02_install_dependencies.bat.
    pause
    exit /b 1
)
%PYTHON_CMD% app.py
pause
exit /b %errorlevel%

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
