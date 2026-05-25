@echo off
setlocal
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"

call :find_python
if errorlevel 1 (
    echo No usable Python 3.12 installation was found.
    echo Install 64-bit Python 3.12 first, then run 01_add_python312_to_path.bat, then 02_install_dependencies.bat.
    pause
    exit /b 1
)

echo Using %PYTHON_CMD%
%PYTHON_CMD% -c "import sys, psutil, win32api, PySide6; print('Core OK:', sys.version.split()[0], 'PySide6', PySide6.__version__)"
if errorlevel 1 (
    echo Core dependencies are missing.
    echo Run 01_add_python312_to_path.bat first if Python is not on PATH, then run 02_install_dependencies.bat.
    pause
    exit /b 1
)

%PYTHON_CMD% -c "import cv2, numpy; print('Preview OK:', numpy.__version__, cv2.__version__)"
if errorlevel 1 (
    echo Preview is unavailable. This does not block JSON generation or FH6 import.
)

if not "%FORZA_PAINTER_NO_PAUSE%"=="1" pause
exit /b 0

:find_python
if exist "%~dp0python\python.exe" (
    "%~dp0python\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32 else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD="%~dp0python\python.exe""
        exit /b 0
    )
)
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
