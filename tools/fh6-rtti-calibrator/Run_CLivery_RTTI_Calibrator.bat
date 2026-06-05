@echo off
setlocal EnableExtensions EnableDelayedExpansion
title KFPS CLiveryGroup RTTI Calibrator
cd /d "%~dp0"

echo KFPS CLiveryGroup RTTI Calibrator
echo.
echo This is READ-ONLY. It scans FH6 memory and saves locator evidence.
echo It does not write to Forza.
echo.
echo Recommended setup:
echo   1. Open Forza Horizon 6.
echo   2. Open a simple white-circle vinyl group.
echo   3. Prefer a 3000 layer template.
echo   4. Keep the vinyl editor open while this runs.
echo.

set "PY_EXE="
set "PY_ARGS="
if exist "%~dp0python\python.exe" set "PY_EXE=%~dp0python\python.exe"
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
  echo Run this from a KFPS standalone folder or install Python 3.12.
  pause
  exit /b 1
)

"%PY_EXE%" %PY_ARGS% "%~dp0clivery_rtti_calibrator.py"
echo.
pause
