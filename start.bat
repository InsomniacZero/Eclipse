@echo off
setlocal enabledelayedexpansion
title Eclipse Unified AI Gateway

:: Resolve root and eclipse directories (always quoted)
set "ROOT_DIR=%~dp0"
set "ECLIPSE_DIR=%ROOT_DIR%eclipse"

:: 0. Auto-Updater [Pulls latest updates automatically on startup]
if not "%ECLIPSE_NO_UPDATE%"=="1" (
    if not "%~1"=="--no-update" (
        where git >nul 2>&1
        if !errorlevel! equ 0 (
            if exist "%ROOT_DIR%.git" (
                pushd "%ROOT_DIR%"
                echo   [*] Checking for updates...
                git fetch --quiet origin main >nul 2>&1
                for /f "delims=" %%i in ('git rev-parse HEAD 2^>nul') do set "LOCAL_HASH=%%i"
                for /f "delims=" %%i in ('git rev-parse FETCH_HEAD 2^>nul') do set "REMOTE_HASH=%%i"
                if not defined REMOTE_HASH (
                    for /f "delims=" %%i in ('git rev-parse origin/main 2^>nul') do set "REMOTE_HASH=%%i"
                )
                if defined LOCAL_HASH if defined REMOTE_HASH (
                    if not "!LOCAL_HASH!"=="!REMOTE_HASH!" (
                        echo   [+] Updating Eclipse to latest version...
                        git pull --ff-only origin main >nul 2>&1 || git pull origin main >nul 2>&1
                        echo   [*] Successfully updated Eclipse!
                    ) else (
                        echo   [✓] Eclipse is up to date!
                    )
                )
                popd
            )
        )
    )
)

:: 1. Detect Python Executable
set "PYTHON_EXE="
set "PYTHON_ARGS="

:: Check if local virtualenv python already exists
if exist "%ECLIPSE_DIR%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ECLIPSE_DIR%\.venv\Scripts\python.exe"
    goto :PYTHON_FOUND
)

:: Check for 'py -3' Windows launcher
py -3 --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=py"
    set "PYTHON_ARGS=-3"
    goto :PYTHON_FOUND
)

:: Check for system 'python'
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=python"
    goto :PYTHON_FOUND
)

:: Check standard Windows user installation directories
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" (
        set "PYTHON_EXE=%%D\python.exe"
        goto :PYTHON_FOUND
    )
)

:: Check Program Files installation directories
for /d %%D in ("%ProgramFiles%\Python3*") do (
    if exist "%%D\python.exe" (
        set "PYTHON_EXE=%%D\python.exe"
        goto :PYTHON_FOUND
    )
)

:PYTHON_NOT_FOUND
echo ======================================================================
echo  [ERROR] Python 3.10+ was not found on your Windows system!
echo ======================================================================
echo.
echo  Eclipse requires Python to run.
echo  1. Download Python from: https://www.python.org/downloads/
echo  2. IMPORTANT: During setup, check the box:
echo     [x] "Add python.exe to PATH"
echo  3. Restart Command Prompt or double-click start.bat again.
echo.
echo ======================================================================
pause
exit /b 1

:PYTHON_FOUND
cd /d "%ECLIPSE_DIR%"
set "PYTHONPATH=%ROOT_DIR%;%ECLIPSE_DIR%;%PYTHONPATH%"

:: 2. Check / Setup Virtual Environment
if not exist "%ECLIPSE_DIR%\.venv\Scripts\python.exe" (
    echo [*] Initializing virtual environment in eclipse\.venv...
    "%PYTHON_EXE%" %PYTHON_ARGS% -m venv "%ECLIPSE_DIR%\.venv"
    if exist "%ECLIPSE_DIR%\.venv\Scripts\python.exe" (
        set "PYTHON_EXE=%ECLIPSE_DIR%\.venv\Scripts\python.exe"
        set "PYTHON_ARGS="
    )
) else (
    set "PYTHON_EXE=%ECLIPSE_DIR%\.venv\Scripts\python.exe"
    set "PYTHON_ARGS="
)

:: Verify dependencies
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import starlette, uvicorn, httpx, curl_cffi" >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Installing required Eclipse dependencies from requirements.txt...
    "%PYTHON_EXE%" %PYTHON_ARGS% -m pip install -r "%ROOT_DIR%requirements.txt"
    if %errorlevel% neq 0 (
        echo.
        echo ======================================================================
        echo  [!] Dependency installation failed.
        echo  Please verify your internet connection or run:
        echo  pip install -r requirements.txt
        echo ======================================================================
        echo.
        pause
        exit /b 1
    )
)

:: 3. Route CLI subcommands vs Gateway Server
set "ARG1=%~1"

if "%ARG1%"=="restart" goto :RESTART_SERVER
if "%ARG1%"=="status" goto :RUN_CLI
if "%ARG1%"=="limits" goto :RUN_CLI
if "%ARG1%"=="accounts" goto :RUN_CLI
if "%ARG1%"=="login" goto :RUN_CLI
if "%ARG1%"=="autofetch" goto :RUN_CLI
if "%ARG1%"=="import" goto :RUN_CLI
if "%ARG1%"=="export" goto :RUN_CLI
if "%ARG1%"=="simulate" goto :RUN_CLI
if "%ARG1%"=="host" goto :RUN_CLI
if "%ARG1%"=="chat" goto :RUN_CLI
if "%ARG1%"=="thinking" goto :RUN_CLI
if "%ARG1%"=="service" goto :RUN_CLI
if "%ARG1%"=="tunnel" goto :RUN_CLI
if "%ARG1%"=="claudecode" goto :RUN_CLI
if "%ARG1%"=="key" goto :RUN_CLI
if "%ARG1%"=="bench" goto :RUN_CLI
if "%ARG1%"=="update" goto :RUN_CLI
if "%ARG1%"=="upgrade" goto :RUN_CLI
if "%ARG1%"=="-h" goto :RUN_CLI
if "%ARG1%"=="--help" goto :RUN_CLI
if "%ARG1%"=="help" goto :RUN_CLI
goto :LAUNCH_GATEWAY

:RESTART_SERVER
shift
echo.
echo   [🔄] Restarting Eclipse [clearing port 5000]...
for %%P in (5000) do (
    for /f "tokens=5" %%A in ('netstat -ano ^| findstr /R /C:":%%P .*LISTENING"') do (
        taskkill /F /PID %%A >nul 2>&1
    )
)
timeout /t 1 /nobreak >nul 2>&1

:LAUNCH_GATEWAY
:: Terminate any stale processes holding port 5000
for %%P in (5000) do (
    for /f "tokens=5" %%A in ('netstat -ano ^| findstr /R /C:":%%P .*LISTENING"') do (
        taskkill /F /PID %%A >nul 2>&1
    )
)

:: Launch Gateway Server
:: --lan listens on all interfaces so phones / other PCs can connect with the gateway key.
:: --no-update skips the automatic startup git pull.
:: Default is this machine only.
set "ECLIPSE_LAN="
for %%A in (%*) do if /I "%%~A"=="--lan" set "ECLIPSE_LAN=1"
for %%A in (%*) do if /I "%%~A"=="--no-update" set "ECLIPSE_NO_UPDATE=1"
set "API_HOST=127.0.0.1"
if defined ECLIPSE_LAN set "API_HOST=0.0.0.0"
set "RP_ALLOWED_ORIGINS="

echo.
echo   [*] Initializing Eclipse Gateway [Windows]...
echo.

"%PYTHON_EXE%" %PYTHON_ARGS% server.py %*
goto :AFTER_RUN

:RUN_CLI
"%PYTHON_EXE%" %PYTHON_ARGS% cli.py %*

:AFTER_RUN
set "EXIT_CODE=%errorlevel%"
if %EXIT_CODE% neq 0 (
    echo.
    echo [!] Eclipse process ended with exit code %EXIT_CODE%.
    pause
)
exit /b %EXIT_CODE%
