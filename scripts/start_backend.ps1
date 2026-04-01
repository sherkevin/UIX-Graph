# UIX backend helper script (Windows PowerShell)
# Usage:
#   .\scripts\start_backend.ps1
#   .\scripts\start_backend.ps1 production

param(
    [string]$Mode = "development",
    [int]$Port = 8000,
    [string]$BindHost = "0.0.0.0"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$BackendDir = Join-Path $ProjectRoot "src\backend"

Write-Host "========================================"
Write-Host "UIX backend startup"
Write-Host "Directory: $BackendDir"
Write-Host "Mode: $Mode"
Write-Host "Bind: ${BindHost}:$Port"
Write-Host "========================================"

$EnvFile = Join-Path $BackendDir ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Host "[WARN] src\\backend\\.env not found, switching to local profile..."
    Push-Location $ProjectRoot
    try {
        python scripts\switch_env.py local
    }
    catch {
        Write-Host "[WARN] switch_env.py failed, continue with defaults."
    }
    finally {
        Pop-Location
    }
}

$PortInUse = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($PortInUse) {
    Write-Host "[ERROR] Port $Port is already in use (PID: $($PortInUse.OwningProcess))."
    Write-Host "Stop the process or run with another port."
    exit 1
}

$VenvActivate = Join-Path $BackendDir ".venv\Scripts\Activate.ps1"
$VenvActivate2 = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $VenvActivate) {
    . $VenvActivate
    Write-Host "[OK] Activated venv: $VenvActivate"
}
elseif (Test-Path $VenvActivate2) {
    . $VenvActivate2
    Write-Host "[OK] Activated venv: $VenvActivate2"
}

Push-Location $BackendDir
try {
    if ($Mode -eq "production") {
        Write-Host "[INFO] Starting production backend..."
        python -m uvicorn app.main:app --host $BindHost --port $Port --workers 2
    } else {
        Write-Host "[INFO] Starting development backend with reload..."
        python -m uvicorn app.main:app --host $BindHost --port $Port --reload
    }
}
finally {
    Pop-Location
}
