@echo off
setlocal
cd /d "%~dp0\..\.."
set "PYTHON_EXE=py -3.12"
if exist "python\python.exe" set "PYTHON_EXE=python\python.exe"
%PYTHON_EXE% -m pip install -r requirements.txt || exit /b 1
%PYTHON_EXE% -m unittest discover -s KFPS.UI\tests -v || exit /b 1
%PYTHON_EXE% -m PyInstaller --noconfirm --clean KFPS.UI\packaging\KFPS.spec || exit /b 1
echo Built dist\KFPS.exe
