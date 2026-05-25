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
    echo Git checkout detected. Syncing tracked app files to latest %BRANCH%...
    git fetch origin %BRANCH%
    if errorlevel 1 goto :fail
    git reset --hard origin/%BRANCH%
    if errorlevel 1 (
        echo.
        echo Update failed because Git could not reset this folder to the latest version.
        echo Generated outputs are stored separately and are not intentionally removed.
        goto :fail
    )
    call :cleanup_retired_files
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

robocopy "%TMP_REPO%" "%CD%" /E /R:2 /W:1 /XD runtime webui-data dist build __pycache__ >nul
if errorlevel 8 (
    echo File copy failed during robocopy update copy. Robocopy exit code: %ERRORLEVEL%
    goto :fail
)

set "NEW_VERSION="
for /f "delims=" %%V in ('git -C "%TMP_REPO%" rev-parse --short^=8 HEAD') do set "NEW_VERSION=%%V"
if defined NEW_VERSION (
    > "%CD%\VERSION" echo %BRANCH%@!NEW_VERSION!
)

call :cleanup_retired_files

rmdir /s /q "%TMP_PARENT%" >nul 2>nul

:done
echo.
echo Update complete.
echo Run 04_start_app.bat when you are ready.
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
    echo Close this window and run 03_update_from_github.bat again.
    exit /b 1
)

echo PortableGit installed and ready.
exit /b 0

:cleanup_retired_files
if exist "settings\_archive_legacy_2026-05-22" rmdir /s /q "settings\_archive_legacy_2026-05-22" >nul 2>nul
if exist "settings\_default.ini" del /f /q "settings\_default.ini" >nul 2>nul
for %%F in (
    "settings\a.3000-ultra-sharp.ini"
    "settings\a2.2000-ultra-sharp.ini"
    "settings\a2b.2000-ultra-sharp + Luma Bands.ini"
    "settings\ab.3000-ultra-sharp + Luma Bands.ini"
    "settings\b.1000-ultra-sharp.ini"
    "settings\bb.1000-ultra-sharp + Luma Bands.ini"
    "settings\c.3000-soft-detail.ini"
    "settings\c2.2000-soft-detail.ini"
    "settings\c2b.2000-soft-detail + Luma Bands.ini"
    "settings\cb.3000-soft-detail + Luma Bands.ini"
    "settings\d.1000-soft-detail.ini"
    "settings\db.1000-soft-detail + Luma Bands.ini"
    "settings\e.3000-smart-detail.ini"
    "settings\e2.2000-smart-detail.ini"
    "settings\e2b.2000-smart-detail + Luma Bands.ini"
    "settings\eb.3000-smart-detail + Luma Bands.ini"
    "settings\f.3000-anime-livery.ini"
    "settings\f2.2000-anime-livery.ini"
    "settings\f2b.2000-anime-livery + Luma Bands.ini"
    "settings\fb.3000-anime-livery + Luma Bands.ini"
    "settings\g.1000-smart-detail.ini"
    "settings\gb.1000-smart-detail + Luma Bands.ini"
    "settings\h.1000-anime-livery.ini"
    "settings\hb.1000-anime-livery + Luma Bands.ini"
) do (
    if exist %%~F del /f /q %%~F >nul 2>nul
)
exit /b 0
