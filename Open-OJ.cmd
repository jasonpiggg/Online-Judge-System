@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Python environment missing. Run: uv sync --frozen --extra dev --extra report
    echo Then double-click Open-OJ.cmd again.
    pause
    exit /b 1
)
set "OJ_ARGS=start"
if /I "%~1"=="-React" set "OJ_ARGS=start --react"
if /I "%~1"=="--react" set "OJ_ARGS=start --react"
if /I "%~1"=="-Legacy" set "OJ_ARGS=start --legacy"
if /I "%~1"=="--legacy" set "OJ_ARGS=start --legacy"
if not "%~2"=="" (
    echo Conflicting or unsupported startup arguments.
    exit /b 2
)
".venv\Scripts\python.exe" "scripts\launch.py" %OJ_ARGS%
if errorlevel 1 (
    echo.
    echo Startup failed. Logs: var\launcher\backend.log and frontend.log
    pause
    exit /b 1
)
exit /b 0
