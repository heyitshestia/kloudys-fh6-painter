@echo off
setlocal
cd /d "%~dp0"
if exist "python\python.exe" (
    "python\python.exe" "KFPS.UI\app.py"
) else (
    py -3.12 "KFPS.UI\app.py"
)
