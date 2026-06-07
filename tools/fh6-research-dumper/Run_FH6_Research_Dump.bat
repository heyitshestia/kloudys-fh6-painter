@echo off
setlocal EnableExtensions EnableDelayedExpansion
title KFPS FH6 Research Dumper
cd /d "%~dp0"

echo KFPS FH6 Research Dumper
echo.
echo This is READ-ONLY. It does not write to Forza.
echo Purpose: collect evidence for reliable locked-vs-unlocked export locating.
echo Open FH6, open the vinyl/group you want to capture, then enter its visible layer count.
echo Current test assumption: unlocked means fully ungrouped, locked means one grouped vinyl.
echo If the state is unclear, choose Unknown rather than guessing.
echo.

set "PY_EXE="
set "PY_ARGS="
call :find_python
if not defined PY_EXE (
  echo No usable Python runtime was found.
  echo Put this dumper next to KFPS, use the KFPS standalone with bundled Python, or install Python 3.10+.
  pause
  exit /b 1
)
echo Using Python: %PY_EXE% %PY_ARGS%

echo.
echo Select the opened vinyl state:
echo   1. Unlocked / ungrouped
echo   2. Locked / one group
echo   3. Unknown / not sure
echo.
set "ACCESS_STATE=unknown"
set "GROUPING_STATE=unknown"
choice /C 123 /N /M "Press 1, 2, or 3: "
if errorlevel 3 goto :state_unknown
if errorlevel 2 goto :state_locked
goto :state_unlocked

:state_unlocked
set "ACCESS_STATE=editable_allowed"
set "GROUPING_STATE=ungrouped"
goto :layer_prompt

:state_locked
set "ACCESS_STATE=locked_community"
set "GROUPING_STATE=grouped"
goto :layer_prompt

:state_unknown
set "ACCESS_STATE=unknown"
set "GROUPING_STATE=unknown"

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
set "STATE_NAME=%LAYER_COUNT%_%ACCESS_STATE%_%GROUPING_STATE%"

echo.
echo Selected access state: %ACCESS_STATE%
echo Assumed grouping state: %GROUPING_STATE%
echo Selected layer count: %LAYER_COUNT%
echo Capturing research dump and raw candidate region chunks...
"%PY_EXE%" %PY_ARGS% "%~dp0fh6_research_capture.py" --count "%LAYER_COUNT%" --state-name "%STATE_NAME%" --grouping-state "%GROUPING_STATE%" --access-state "%ACCESS_STATE%" --out-root "%~dp0captures"
if errorlevel 1 (
  echo.
  echo Capture failed. Check the messages above.
  pause
  exit /b 1
)

echo.
echo Updating grouped/ungrouped research comparison report from all captures...
"%PY_EXE%" %PY_ARGS% "%~dp0analyze_lock_research.py" "%~dp0captures"

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
echo If you are collecting several dumps, run this once per opened vinyl.
echo After several unlocked and locked dumps exist, lock-research-analysis.md will summarize graph/orphan behavior.
echo.
pause
exit /b 0

:find_python
if exist "%~dp0python\python.exe" call :try_python "%~dp0python\python.exe"
if not defined PY_EXE if exist "%~dp0..\python\python.exe" call :try_python "%~dp0..\python\python.exe"
if not defined PY_EXE if exist "%~dp0..\KloudysFH6Painter\python\python.exe" call :try_python "%~dp0..\KloudysFH6Painter\python\python.exe"
if not defined PY_EXE if exist "%USERPROFILE%\Desktop\Kloudys Painter Standalone\KloudysFH6Painter\python\python.exe" call :try_python "%USERPROFILE%\Desktop\Kloudys Painter Standalone\KloudysFH6Painter\python\python.exe"
if not defined PY_EXE if exist "%USERPROFILE%\Desktop\KFPS\KloudysFH6Painter\python\python.exe" call :try_python "%USERPROFILE%\Desktop\KFPS\KloudysFH6Painter\python\python.exe"
if not defined PY_EXE for /d %%D in ("%USERPROFILE%\Desktop\*") do if not defined PY_EXE if exist "%%~fD\KloudysFH6Painter\python\python.exe" call :try_python "%%~fD\KloudysFH6Painter\python\python.exe"
if not defined PY_EXE for /d %%D in ("%USERPROFILE%\Desktop\*") do if not defined PY_EXE if exist "%%~fD\python\python.exe" call :try_python "%%~fD\python\python.exe"
if not defined PY_EXE (
  where py >nul 2>nul
  if not errorlevel 1 call :try_python "py" "-3.12"
)
if not defined PY_EXE (
  where py >nul 2>nul
  if not errorlevel 1 call :try_python "py" "-3"
)
if not defined PY_EXE (
  where python >nul 2>nul
  if not errorlevel 1 call :try_python "python"
)
exit /b 0

:try_python
set "TRY_EXE=%~1"
set "TRY_ARGS=%~2"
"%TRY_EXE%" %TRY_ARGS% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 exit /b 0
set "PY_EXE=%TRY_EXE%"
set "PY_ARGS=%TRY_ARGS%"
exit /b 0
