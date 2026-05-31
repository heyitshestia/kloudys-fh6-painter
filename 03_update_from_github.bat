@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "REPO_URL=https://github.com/heyitshestia/kloudys-fh6-painter.git"
set "BRANCH=main"

call :init_update_log
call :capture_current_version OLD_VERSION

call :log "Kloudy's Painter Launcher updater"
call :log ""
call :log "Use this batch file exclusively for updates."
call :log "Close the app before continuing."
call :log "This updates program files from GitHub and preserves generated/runtime data."
call :log "Current version: !OLD_VERSION!"
call :log "Log file: !UPDATE_LOG!"
call :log ""

call :ensure_git
if errorlevel 1 goto :fail
call :check_update_locks
if errorlevel 1 goto :fail_quiet

if exist ".git\" (
    call :log "Git checkout detected. Syncing tracked app files to latest %BRANCH%..."
    git fetch origin %BRANCH%
    if errorlevel 1 goto :fail
    call :backup_existing_files
    if errorlevel 1 goto :fail
    git reset --hard origin/%BRANCH%
    if errorlevel 1 (
        call :log ""
        call :log "Update failed because Git could not reset this folder to the latest version."
        call :log "Generated outputs are stored separately and are not intentionally removed."
        goto :fail
    )
    call :write_build_commit "%CD%"
    call :cleanup_retired_files
    goto :done
)

call :log "This folder is not a Git checkout."
call :log "A fresh copy will be downloaded and copied over this folder, like dragging new files over old ones."
call :log "Existing generated/runtime data will be preserved."
call :log ""

set "TMP_PARENT=%TEMP%\kloudys-fh6-painter-update"
set "TMP_REPO=%TMP_PARENT%\repo"
if exist "%TMP_PARENT%" rmdir /s /q "%TMP_PARENT%"
mkdir "%TMP_PARENT%" >nul 2>nul

git clone --depth 1 --branch %BRANCH% "%REPO_URL%" "%TMP_REPO%"
if errorlevel 1 goto :fail

call :backup_existing_files
if errorlevel 1 goto :fail
call :check_update_locks
if errorlevel 1 goto :fail_quiet

robocopy "%TMP_REPO%" "%CD%" /E /R:2 /W:1 /XD runtime webui-data dist build __pycache__ >nul
if errorlevel 8 (
    call :log "File copy failed during robocopy update copy. Robocopy exit code: %ERRORLEVEL%"
    goto :fail
)

call :cleanup_retired_files
call :write_build_commit "%TMP_REPO%"

rmdir /s /q "%TMP_PARENT%" >nul 2>nul

:done
call :capture_current_version FINAL_VERSION
call :log ""
call :log "Update complete."
call :log "Version: !OLD_VERSION! -> !FINAL_VERSION!"
call :log "Backup folder: !BACKUP_DIR!"
call :log "Run 04_start_app.bat when you are ready."
if not "%FORZA_PAINTER_NO_PAUSE%"=="1" pause
exit /b 0

:fail_quiet
if not "%FORZA_PAINTER_NO_PAUSE%"=="1" pause
exit /b 1

:fail
call :log ""
call :log "Update failed. No generated images or runtime output were intentionally removed."
call :log "If program files were partially changed, check backup folder: !BACKUP_DIR!"
if not "%FORZA_PAINTER_NO_PAUSE%"=="1" pause
exit /b 1

:init_update_log
set "UPDATE_STAMP=manual"
for /f "delims=" %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss" 2^>nul') do set "UPDATE_STAMP=%%T"
set "UPDATE_LOG_DIR=%CD%\runtime\update-logs"
if not exist "%UPDATE_LOG_DIR%" mkdir "%UPDATE_LOG_DIR%" >nul 2>nul
set "UPDATE_LOG=%UPDATE_LOG_DIR%\update-%UPDATE_STAMP%.log"
> "%UPDATE_LOG%" echo Kloudy's Painter Launcher update log
set "BACKUP_ROOT=%LOCALAPPDATA%\KloudysFH6Painter\update-backups"
if "%LOCALAPPDATA%"=="" set "BACKUP_ROOT=%TEMP%\KloudysFH6Painter\update-backups"
set "BACKUP_DIR=%BACKUP_ROOT%\%UPDATE_STAMP%"
exit /b 0

:log
if "%~1"=="" (
    echo.
    if defined UPDATE_LOG (
        >> "%UPDATE_LOG%" echo.
    )
) else (
    echo %~1
    if defined UPDATE_LOG (
        >> "%UPDATE_LOG%" echo [%DATE% %TIME%] %~1
    )
)
exit /b 0

:capture_current_version
set "%~1=unknown"
if exist "VERSION" (
    for /f "usebackq delims=" %%V in ("VERSION") do (
        set "%~1=%%V"
        goto :capture_current_version_done
    )
)
if exist ".git\" (
    for /f "delims=" %%V in ('git rev-parse --short^=8 HEAD 2^>nul') do set "%~1=git:%%V"
)
:capture_current_version_done
exit /b 0

:backup_existing_files
call :log "Backing up current app files before overwrite..."
if not exist "!BACKUP_DIR!" mkdir "!BACKUP_DIR!" >nul 2>nul
robocopy "%CD%" "!BACKUP_DIR!" /E /R:1 /W:1 /XD ".git" "runtime" "imgs" "webui-data" "dist" "build" "__pycache__" "python" /XF "*.pyc" >nul
if errorlevel 8 (
    call :log "Backup warning. Robocopy exit code: %ERRORLEVEL%"
    call :log "Continuing update without blocking because generated/runtime data is preserved separately."
)
call :log "Backup folder: !BACKUP_DIR!"
exit /b 0

:check_update_locks
set "LOCK_REPORT=%TEMP%\kloudys-update-locks-%RANDOM%.txt"
if exist "!LOCK_REPORT!" del /f /q "!LOCK_REPORT!" >nul 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "$root=(Resolve-Path '.').Path; $names=@('KloudysGeneratorV7.exe','KloudysGeneratorV6.exe','KloudysGeneratorV6-Go.exe','KloudysGeneratorV5.exe','KloudysGeneratorV5DetailLock.exe','KloudysGeneratorV4.exe','KloudysGeneratorV2.exe','KloudysGeneratorV2Fast.exe','KloudysGeneratorV2Speed.exe','ForzaVinylStudio.exe'); $match={ ($names -contains $_.Name) -or (($_.Name -match '^python') -and ($_.CommandLine -like ('*' + $root + '*')) -and ($_.CommandLine -match 'app_qt.py|start_fabric_editor.py|forza_generator_v2.py|benchmark_generator_settings.py')) }; $locks=Get-CimInstance Win32_Process | Where-Object $match; if($locks){ $locks | ForEach-Object { ('PID ' + $_.ProcessId + ' - ' + $_.Name) } | Set-Content -LiteralPath '%LOCK_REPORT%' -Encoding ASCII; $locks | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Start-Sleep -Milliseconds 800; $remaining=Get-CimInstance Win32_Process | Where-Object $match; if($remaining){ 'Still running after termination attempt:' | Add-Content -LiteralPath '%LOCK_REPORT%' -Encoding ASCII; $remaining | ForEach-Object { ('PID ' + $_.ProcessId + ' - ' + $_.Name) } | Add-Content -LiteralPath '%LOCK_REPORT%' -Encoding ASCII; exit 2 } }; exit 0"
if errorlevel 1 (
    call :log ""
    call :log "Update tried to stop Kloudy's Painter processes, but Windows reports that one is still running."
    call :log "Close the listed process manually or restart Windows, then run this updater again."
    if exist "!LOCK_REPORT!" (
        call :log "Running process details:"
        for /f "usebackq delims=" %%L in ("!LOCK_REPORT!") do call :log "%%L"
        del /f /q "!LOCK_REPORT!" >nul 2>nul
    )
    exit /b 1
)
if exist "!LOCK_REPORT!" (
    call :log ""
    call :log "Stopped running Kloudy's Painter processes before updating:"
    for /f "usebackq delims=" %%L in ("!LOCK_REPORT!") do call :log "%%L"
    del /f /q "!LOCK_REPORT!" >nul 2>nul
)
exit /b 0

:write_build_commit
set "COMMIT_SHA="
for /f "delims=" %%V in ('git -C "%~1" rev-parse HEAD 2^>nul') do set "COMMIT_SHA=%%V"
if defined COMMIT_SHA (
    > "%CD%\BUILD_COMMIT" echo !COMMIT_SHA!
)
exit /b 0

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

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Continue'; $out=Join-Path $env:TEMP 'PortableGit-64-bit.7z.exe'; $urls=@('https://github.com/git-for-windows/git/releases/download/v2.54.0.windows.1/PortableGit-2.54.0-64-bit.7z.exe','https://sourceforge.net/projects/git-for-windows.mirror/files/v2.54.0.windows.1/PortableGit-2.54.0-64-bit.7z.exe/download'); foreach($url in $urls){ try { Write-Host ('Downloading PortableGit from ' + $url); Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $out -Headers @{'User-Agent'='KloudysFH6Painter'}; if((Test-Path $out) -and ((Get-Item $out).Length -gt 1000000)){ exit 0 } } catch { Write-Host ('PortableGit download failed from ' + $url + ': ' + $_.Exception.Message) } }; exit 1"
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
call :sync_launcher_exe
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
    "settings\a.fast-ugly.ini"
    "settings\b.okay-draft.ini"
    "settings\c.pretty-good.ini"
    "settings\d.slow-beautiful.ini"
    "KloudysGeneratorV2.exe"
    "KloudysGeneratorV2Fast.exe"
    "KloudysGeneratorV2Speed.exe"
    "KloudysGeneratorV4.exe"
    "KloudysGeneratorV5DetailLock.exe"
    "KloudysGeneratorV5.exe"
    "KloudysGeneratorV6-Go.exe"
    "KloudysGeneratorV6.exe"
    "kloudys-fh6-generator.exe"
    "forza-painter-geometrize-go.exe"
    "docs\GENERATOR_BENCHMARK_PLAN.md"
    "tools\benchmark_generator_settings.py"
) do (
    if exist %%~F del /f /q %%~F >nul 2>nul
)
if exist "tools\__pycache__" rmdir /s /q "tools\__pycache__" >nul 2>nul
set "TOOLS_HAS_CONTENT="
if exist "tools\" (
    for /f "delims=" %%A in ('dir /a /b "tools" 2^>nul') do set "TOOLS_HAS_CONTENT=1"
    if not defined TOOLS_HAS_CONTENT rmdir /q "tools" >nul 2>nul
)
exit /b 0

:sync_launcher_exe
if exist "Kloudys Painter.exe" del /f /q "Kloudys Painter.exe" >nul 2>nul
for %%I in ("%CD%") do set "CURRENT_FOLDER=%%~nxI"
if /I not "%CURRENT_FOLDER%"=="KloudysFH6Painter" exit /b 0
if exist "Kloudys Painter Launcher.exe" (
    copy /y "Kloudys Painter Launcher.exe" "..\Kloudys Painter Launcher.exe" >nul 2>nul
    del /f /q "Kloudys Painter Launcher.exe" >nul 2>nul
)
if exist "..\Kloudys Painter.exe" del /f /q "..\Kloudys Painter.exe" >nul 2>nul
exit /b 0
