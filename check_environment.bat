@echo off
setlocal
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"

call :find_python
if errorlevel 1 (
    echo No usable Python was found. Install 64-bit Python 3.10 or newer.
    pause
    exit /b 1
)

echo Using %PYTHON_CMD%
%PYTHON_CMD% -c "import sys, psutil, win32api; print('Core OK:', sys.version.split()[0])"
if errorlevel 1 (
    echo Core dependencies are missing. Run install_dependencies.bat.
    pause
    exit /b 1
)

%PYTHON_CMD% -c "import cv2, numpy; print('Preview OK:', numpy.__version__, cv2.__version__)"
if errorlevel 1 (
    echo Preview is unavailable. This does not block JSON generation or FH6 import.
)

pause
exit /b 0

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
