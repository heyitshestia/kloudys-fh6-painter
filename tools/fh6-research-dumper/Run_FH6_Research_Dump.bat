@echo off
setlocal EnableExtensions EnableDelayedExpansion
title KFPS FH6 Research Dumper
cd /d "%~dp0"

echo KFPS FH6 Research Dumper
echo.
echo This is READ-ONLY. It does not write to Forza.
echo Open FH6, open the vinyl/group you want to capture, then enter its visible layer count.
echo.

set "PY_EXE="
set "PY_ARGS="
if exist "%~dp0python\python.exe" set "PY_EXE=%~dp0python\python.exe"
if not defined PY_EXE if exist "%USERPROFILE%\Desktop\KFPS Importer Consolidation Prototype\python\python.exe" set "PY_EXE=%USERPROFILE%\Desktop\KFPS Importer Consolidation Prototype\python\python.exe"
if not defined PY_EXE if exist "%USERPROFILE%\Desktop\Kloudys Painter Standalone\KloudysFH6Painter\python\python.exe" set "PY_EXE=%USERPROFILE%\Desktop\Kloudys Painter Standalone\KloudysFH6Painter\python\python.exe"
if not defined PY_EXE (
  where py >nul 2>nul
  if not errorlevel 1 (
    set "PY_EXE=py"
    set "PY_ARGS=-3.12"
  )
)
if not defined PY_EXE (
  where python >nul 2>nul
  if not errorlevel 1 set "PY_EXE=python"
)
if not defined PY_EXE (
  echo Python was not found.
  echo Install/use the KFPS standalone or install Python 3.12, then run this again.
  pause
  exit /b 1
)

echo Select the current vinyl state:
echo   1. Ungrouped shapes
echo   2. One grouped vinyl
echo   3. Grouped groups / nested groups
echo.
choice /C 123 /N /M "Press 1, 2, or 3: "
if errorlevel 3 set "STATE_KIND=grouped_groups"
if errorlevel 2 if not defined STATE_KIND set "STATE_KIND=grouped"
if errorlevel 1 if not defined STATE_KIND set "STATE_KIND=ungrouped"

:layer_prompt
set "LAYER_COUNT="
set /p "LAYER_COUNT=Visible layer count in FH6: "
if not defined LAYER_COUNT (
  echo Layer count is required.
  goto :layer_prompt
)
for /f "delims=0123456789" %%A in ("%LAYER_COUNT%") do (
  echo Please enter numbers only, for example 3000.
  goto :layer_prompt
)
set "STATE_NAME=%LAYER_COUNT%_%STATE_KIND%"

echo.
echo Selected state: %STATE_KIND%
echo Selected layer count: %LAYER_COUNT%
echo Capturing research dump and raw candidate region chunks...
"%PY_EXE%" %PY_ARGS% "%~dp0fh6_research_capture.py" --count "%LAYER_COUNT%" --state-name "%STATE_NAME%" --out-root "%~dp0captures"
if errorlevel 1 (
  echo.
  echo Capture failed. Check the messages above.
  pause
  exit /b 1
)

for /f "delims=" %%D in ('dir /b /ad /o-d "%~dp0captures" 2^>nul') do (
  set "LATEST=%%D"
  goto :zip_latest
)

:zip_latest
if defined LATEST (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$src = Join-Path '%~dp0captures' '%LATEST%'; $zip = $src + '.zip'; if (Test-Path $zip) { Remove-Item $zip -Force }; Compress-Archive -Path $src -DestinationPath $zip -Force; Write-Host 'ZIP ready:' $zip"
)

echo.
echo Done. Send the newest .zip from:
echo %~dp0captures
echo.
pause
