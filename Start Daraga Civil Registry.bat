@echo off
setlocal EnableExtensions
title Daraga Civil Registry (PostgreSQL)

set "ROOT=%~dp0"
set "APP=%ROOT%daragacivilregistrymanagementsystem"
if not exist "%APP%\app.py" (
    echo Could not find app.py in:
    echo   %APP%
    pause
    exit /b 1
)
cd /d "%APP%"

set "PG_BIN=%USERPROFILE%\scoop\apps\postgresql\current\bin"
set "PG_DATA=%USERPROFILE%\scoop\apps\postgresql\current\data"
set "PATH=%PG_BIN%;%PATH%"

if exist "%PG_BIN%\pg_ctl.exe" (
    "%PG_BIN%\pg_ctl.exe" -D "%PG_DATA%" status >nul 2>&1
    if errorlevel 1 (
        echo Starting PostgreSQL...
        "%PG_BIN%\pg_ctl.exe" -D "%PG_DATA%" -l "%PG_DATA%\logfile" start
        timeout /t 3 /nobreak >nul
    ) else (
        echo PostgreSQL is already running.
    )
)

netstat -ano | findstr ":5001" | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo The system is already running.
    echo Opening http://127.0.0.1:5001
    start "" "http://127.0.0.1:5001"
    pause
    exit /b 0
)

set "PY="
if exist "%APP%\.venv\Scripts\python.exe" set "PY=%APP%\.venv\Scripts\python.exe"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
    echo Python was not found. Install Python or create .venv in the app folder.
    pause
    exit /b 1
)

echo.
echo Starting Daraga Civil Registry (PostgreSQL copy)...
echo   This PC:  http://127.0.0.1:5001
echo   Stop:     close this window or press Ctrl+C
echo.
"%PY%" app.py
echo.
echo The system stopped.
pause
