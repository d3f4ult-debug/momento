@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo     Momento - Universal Desktop Workspace
echo ===================================================

set "SCRIPT_DIR=%~dp0"
set "MOMENTO_PROJECT_ROOT=%SCRIPT_DIR%"
set "PYTHONPATH=%SCRIPT_DIR%"
set "MOMENTO_BRIDGE_PORT=8000"

:: Resolve Python executable
set "PYTHON_EXE=python"
if exist "%SCRIPT_DIR%venv\Scripts\python.exe" (
    set "PYTHON_EXE=%SCRIPT_DIR%venv\Scripts\python.exe"
) else if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%SCRIPT_DIR%.venv\Scripts\python.exe"
)

:: Check if Python bridge daemon is already running on port 8000
netstat -ano | findstr /R /C:":8000 *LISTENING" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [*] Starting Momento Python Bridge Server Daemon on port 8000...
    start "Momento Bridge Server" /b "%PYTHON_EXE%" "%SCRIPT_DIR%client\bridge_server.py"
    timeout /t 2 /nobreak >nul
) else (
    echo [*] Momento Python Bridge Server is already active on port 8000.
)

:: Launch Flutter Desktop Application
set "RELEASE_EXE=%SCRIPT_DIR%flutter_client\build\windows\x64\runner\Release\momento_desktop.exe"
if exist "%RELEASE_EXE%" (
    echo [*] Launching Momento Desktop GUI...
    start "" "%RELEASE_EXE%"
) else (
    echo [!] Release executable not found at:
    echo     %RELEASE_EXE%
    echo [*] Running via Flutter tools...
    cd /d "%SCRIPT_DIR%flutter_client"
    flutter run -d windows
)

echo [*] Workspace initialized successfully.
endlocal
