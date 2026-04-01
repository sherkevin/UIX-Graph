# UIX frontend helper script (Windows PowerShell)
# Usage:
#   .\scripts\start_frontend.ps1
#   .\scripts\start_frontend.ps1 build

param(
    [string]$Mode = "dev"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$FrontendDir = Join-Path $ProjectRoot "src\frontend"

Write-Host "========================================"
Write-Host "UIX frontend startup"
Write-Host "Directory: $FrontendDir"
Write-Host "Mode: $Mode"
Write-Host "========================================"

Push-Location $FrontendDir
try {
    if (-not (Test-Path "node_modules")) {
        Write-Host "[INFO] node_modules not found, running npm ci..."
        npm ci
    }

    if ($Mode -eq "build") {
        Write-Host "[INFO] Running production build..."
        npm run build
        Write-Host "[OK] Build completed. Output: $FrontendDir\dist"
    } else {
        Write-Host "[INFO] Starting dev server at http://localhost:3000 ..."
        npm run dev
    }
}
finally {
    Pop-Location
}
