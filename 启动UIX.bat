@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

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
py -3 scripts\start.py
goto end

:run_python
python scripts\start.py
goto end

:run_python3
python3 scripts\start.py
goto end

:end
endlocal
