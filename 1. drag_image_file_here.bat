@echo off
setlocal
color 0F
title forza-painter FH6
set "PYTHONDONTWRITEBYTECODE=1"

cd /d "%~dp0"
set "ARG1=%~1"

IF NOT "%ARG1%" == "" GOTO Dragged

set /p ARG1="[MANUAL MODE] Paste the image path: "

:Dragged
call :find_python
if errorlevel 1 (
    echo No usable Python was found. Install 64-bit Python 3.10 or newer.
    pause
    exit /b 1
)

%PYTHON_CMD% app.py "%ARG1%"
cls
color 0F
echo FINISHED!
pause
exit /b %errorlevel%

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
