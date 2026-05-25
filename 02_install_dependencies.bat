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
echo   2. Run 01_add_python312_to_path.bat
echo   3. Run 02_install_dependencies.bat
echo   4. Only then run 04_start_app.bat
echo ============================================================
echo.

call :find_python
if errorlevel 1 (
    echo No usable Python 3.12 installation was found.
    echo.
    echo Download 64-bit Python 3.12 from:
    echo   %PYTHON312_URL%
    echo.
    echo Then run 01_add_python312_to_path.bat, then 02_install_dependencies.bat.
    pause
    exit /b 1
)

echo Using %PYTHON_CMD%
%PYTHON_CMD% -c "import PySide6, psutil, win32api, cv2, numpy, PIL; print('Bundled dependencies already available.')" >nul 2>nul
if not errorlevel 1 (
    echo Dependencies are already installed.
    if not "%FORZA_PAINTER_NO_PAUSE%"=="1" pause
    exit /b 0
)

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
echo You can now run 04_start_app.bat
if not "%FORZA_PAINTER_NO_PAUSE%"=="1" pause
exit /b 0

:Failed
echo.
echo Dependency installation failed.
echo This project expects 64-bit Python 3.12:
echo   %PYTHON312_URL%
echo If Python is installed but still not found, run 01_add_python312_to_path.bat first.
if not "%FORZA_PAINTER_NO_PAUSE%"=="1" pause
exit /b 1

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
