@echo off
cd /d "%~dp0"

echo Cleaning runtime caches...
rmdir /s /q "webui-data" 2>nul
rmdir /s /q "runtime" 2>nul
rmdir /s /q "__pycache__" 2>nul
rmdir /s /q ".pytest_cache" 2>nul
rmdir /s /q "dist" 2>nul
rmdir /s /q "build" 2>nul
del /q "preview.png" 2>nul
del /q "*.pyc" 2>nul
del /q "*.log" 2>nul

echo Done.
pause
