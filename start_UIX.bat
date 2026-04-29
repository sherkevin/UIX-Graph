@echo off
REM ============================================================
REM   UIX one-click launcher (Windows double-click entry)
REM   SXEE-LITHO-RCA - Litho reject root-cause analysis
REM
REM   IMPORTANT: This .bat file MUST stay pure ASCII.
REM   cmd.exe parses .bat with the system codepage (usually GBK on
REM   Chinese Windows). UTF-8 multi-byte chars in the file body
REM   would be misread as commands. Keep all CJK in echo strings
REM   AFTER `chcp 65001`, or just keep them out entirely.
REM
REM   Usage:
REM     start_UIX.bat               -> double-click, Tk GUI launcher
REM     start_UIX.bat --console     -> no GUI, all logs in this cmd
REM     start_UIX.bat --console --env local
REM ============================================================

setlocal
cd /d "%~dp0"

REM Switch current cmd to UTF-8 codepage so Python output is readable
chcp 65001 >nul 2>&1

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM Probe py launcher / python / python3 in order
py -3 -c "pass" >nul 2>&1
if not errorlevel 1 goto run_py

python -c "pass" >nul 2>&1
if not errorlevel 1 goto run_python

python3 -c "pass" >nul 2>&1
if not errorlevel 1 goto run_python3

echo [ERROR] Python 3 not found.
echo Install Python 3.9+ and enable "Add Python to PATH".
pause
goto end

:run_py
py -3 scripts\start.py %*
goto wait_on_console

:run_python
python scripts\start.py %*
goto wait_on_console

:run_python3
python3 scripts\start.py %*
goto wait_on_console

:wait_on_console
REM Keep window open in console mode so the user can copy logs
echo %* | findstr /I /C:"--console" >nul
if not errorlevel 1 (
    echo.
    echo ============================================================
    echo  [launcher] process exited, press any key to close window
    echo ============================================================
    pause >nul
)

:end
endlocal
