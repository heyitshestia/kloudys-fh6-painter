@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "REPO_URL=https://github.com/heyitshestia/kloudys-fh6-painter.git"
set "BRANCH=main"

echo Kloudy's FH6 Painter updater
echo.
echo Use this batch file exclusively for updates.
echo Close the app before continuing.
echo This updates program files from GitHub and preserves generated/runtime data.
echo.

call :ensure_git
if errorlevel 1 goto :fail

if exist ".git\" (
    echo Git checkout detected. Pulling latest %BRANCH%...
    git fetch origin %BRANCH%
    if errorlevel 1 goto :fail
    git pull --ff-only origin %BRANCH%
    if errorlevel 1 (
        echo.
        echo Update failed because Git could not fast-forward this folder.
        echo If you edited app files manually, move your edits elsewhere and try again.
        echo Generated outputs are stored separately and are not the problem.
        goto :fail
    )
    goto :done
)

echo This folder is not a Git checkout.
echo A fresh copy will be downloaded and copied over this folder, like dragging new files over old ones.
echo Existing generated/runtime data will be preserved.
echo.

set "TMP_PARENT=%TEMP%\kloudys-fh6-painter-update"
set "TMP_REPO=%TMP_PARENT%\repo"
if exist "%TMP_PARENT%" rmdir /s /q "%TMP_PARENT%"
mkdir "%TMP_PARENT%" >nul 2>nul

git clone --depth 1 --branch %BRANCH% "%REPO_URL%" "%TMP_REPO%"
if errorlevel 1 goto :fail

robocopy "%TMP_REPO%" "%CD%" /E /XD runtime webui-data dist build __pycache__ >nul
set "ROBOCOPY_CODE=%ERRORLEVEL%"
if %ROBOCOPY_CODE% GEQ 8 (
    echo File copy failed. Robocopy exit code: %ROBOCOPY_CODE%
    goto :fail
)

set "NEW_VERSION="
for /f "delims=" %%V in ('git -C "%TMP_REPO%" rev-parse --short^=8 HEAD') do set "NEW_VERSION=%%V"
if defined NEW_VERSION (
    > "%CD%\VERSION" echo %BRANCH%@!NEW_VERSION!
)

rmdir /s /q "%TMP_PARENT%" >nul 2>nul

:done
echo.
echo Update complete.
echo Run start_app.bat when you are ready.
pause
exit /b 0

:fail
echo.
echo Update failed. No generated images or runtime output were intentionally removed.
pause
exit /b 1

:ensure_git
where git >nul 2>nul
if not errorlevel 1 exit /b 0

if exist "%ProgramFiles%\Git\cmd\git.exe" (
    set "PATH=%ProgramFiles%\Git\cmd;%PATH%"
    exit /b 0
)
if exist "%ProgramFiles(x86)%\Git\cmd\git.exe" (
    set "PATH=%ProgramFiles(x86)%\Git\cmd;%PATH%"
    exit /b 0
)

set "PORTABLE_GIT_ROOT=%LOCALAPPDATA%\KloudysFH6Painter\PortableGit"
if exist "%PORTABLE_GIT_ROOT%\cmd\git.exe" (
    set "PATH=%PORTABLE_GIT_ROOT%\cmd;%PATH%"
    exit /b 0
)

echo Git was not found. Installing PortableGit silently for this user...
set "GIT_INSTALLER=%TEMP%\PortableGit-64-bit.7z.exe"
if exist "%GIT_INSTALLER%" del /f /q "%GIT_INSTALLER%" >nul 2>nul

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $release=Invoke-RestMethod -Uri 'https://api.github.com/repos/git-for-windows/git/releases/latest'; $asset=$release.assets | Where-Object { $_.name -match '^PortableGit-.*-64-bit\.7z\.exe$' } | Select-Object -First 1; if(-not $asset){ throw 'PortableGit asset not found.' }; Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url -OutFile $env:TEMP\PortableGit-64-bit.7z.exe"
if errorlevel 1 (
    echo Failed to download PortableGit.
    exit /b 1
)
if not exist "%GIT_INSTALLER%" (
    echo PortableGit archive was not downloaded.
    exit /b 1
)

"%GIT_INSTALLER%" -y -o"%PORTABLE_GIT_ROOT%" >nul
if errorlevel 1 (
    echo PortableGit extraction failed.
    exit /b 1
)

set "PATH=%PORTABLE_GIT_ROOT%\cmd;%PATH%"

where git >nul 2>nul
if errorlevel 1 (
    echo PortableGit was extracted but is not available in this session.
    echo Close this window and run update_from_github.bat again.
    exit /b 1
)

echo PortableGit installed and ready.
exit /b 0
