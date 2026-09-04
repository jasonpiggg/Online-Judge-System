@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Python environment missing. Run: uv sync --frozen --extra dev --extra report
    echo Then double-click Open-OJ.cmd again.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" "scripts\launch.py" start
if errorlevel 1 (
    echo.
    echo Startup failed. Logs: var\launcher\backend.log and frontend.log
    pause
    exit /b 1
)
exit /b 0
