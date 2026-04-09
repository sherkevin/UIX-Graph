@echo off
setlocal
cd /d "%~dp0"
set "PS_SCRIPT=scripts\package_intranet.ps1"

if not exist "%PS_SCRIPT%" (
    echo [ERROR] Packaging script not found: %PS_SCRIPT%
    pause
    exit /b 1
)

echo [INFO] Running intranet packaging...
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
if errorlevel 1 (
    echo [ERROR] Packaging failed.
    pause
    exit /b 1
)

echo [OK] Package created: UIX-Graph-intranet-package.zip
endlocal
