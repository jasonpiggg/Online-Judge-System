@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Python environment missing. Cannot safely identify the OJ processes.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" "scripts\launch.py" stop
if errorlevel 1 (
    pause
    exit /b 1
)
exit /b 0
