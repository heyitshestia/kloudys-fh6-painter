@echo off
setlocal
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
call :find_python
if errorlevel 1 (
    echo No usable Python 3.12 was found.
    echo Run 01_add_python312_to_path.bat first.
    pause
    exit /b 1
)
%PYTHON_CMD% -c "import PySide6" >nul 2>nul
if errorlevel 1 (
    echo PySide6 is missing. Running dependency setup first...
    call "%~dp002_install_dependencies.bat"
    if errorlevel 1 exit /b 1
)
%PYTHON_CMD% launcher_qt.py
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
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32 else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD="%LOCALAPPDATA%\Programs\Python\Python312\python.exe""
        exit /b 0
    )
)
exit /b 1
