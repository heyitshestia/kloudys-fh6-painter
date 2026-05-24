@echo off
setlocal
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHON312_URL=https://www.python.org/downloads/release/python-31210/"
set "PYTHON312_INSTALLER_URL=https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
set "PYTHON312_INSTALLER=%TEMP%\python-3.12.10-amd64.exe"

echo.
echo ============================================================
echo Kloudy's FH6 Painter - Python PATH setup
echo ============================================================
echo.
echo This script finds Python 3.12, or downloads and installs it if missing.
echo Run 02_install_dependencies.bat after this.
echo.

call :find_python
if errorlevel 1 (
    echo No usable Python 3.12 installation was found.
    echo.
    echo Downloading and installing 64-bit Python 3.12 for this Windows user...
    echo Source:
    echo   %PYTHON312_INSTALLER_URL%
    echo.
    call :install_python
    if errorlevel 1 goto Failed
    call :find_python
    if errorlevel 1 goto Failed
)

echo Using %PYTHON_CMD%
call :add_python_to_path

echo.
echo Python 3.12 and Scripts folders were added to the user PATH.
echo Close and reopen terminals before running 02_install_dependencies.bat.
if not "%FORZA_PAINTER_NO_PAUSE%"=="1" pause
exit /b 0

:Failed
echo.
echo Python 3.12 setup failed.
echo You can install it manually from:
echo   %PYTHON312_URL%
echo.
echo Then run this file again.
if not "%FORZA_PAINTER_NO_PAUSE%"=="1" pause
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
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32 else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD="%LOCALAPPDATA%\Programs\Python\Python312\python.exe""
        exit /b 0
    )
)
exit /b 1

:install_python
if exist "%PYTHON312_INSTALLER%" del /f /q "%PYTHON312_INSTALLER%" >nul 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; Invoke-WebRequest -UseBasicParsing -Uri '%PYTHON312_INSTALLER_URL%' -OutFile '%PYTHON312_INSTALLER%'"
if errorlevel 1 (
    echo Failed to download Python installer.
    exit /b 1
)
if not exist "%PYTHON312_INSTALLER%" (
    echo Python installer was not downloaded.
    exit /b 1
)
"%PYTHON312_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1 Include_test=0 Shortcuts=0
if errorlevel 1 (
    echo Python installer failed.
    exit /b 1
)
exit /b 0

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
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $add=@('%PYTHON_DIR%','%SCRIPTS_DIR%'); $user=[Environment]::GetEnvironmentVariable('Path','User'); $parts=@(); if($user){ $parts=$user -split ';' | Where-Object { $_ } }; foreach($item in $add){ if($parts -notcontains $item){ $parts += $item } }; [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User')"
if errorlevel 1 exit /b 1
set "PATH=%PYTHON_DIR%;%SCRIPTS_DIR%;%PATH%"
exit /b 0
