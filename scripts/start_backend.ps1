# ============================================================
# UIX 后端启动脚本（Windows PowerShell）
# 使用方式（在项目根目录执行）：
#   .\scripts\start_backend.ps1               # 开发模式
#   .\scripts\start_backend.ps1 production    # 生产模式
# ============================================================
param(
    [string]$Mode = "development",
    [int]$Port = 8000,
    [string]$Host = "0.0.0.0"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$BackendDir = Join-Path $ProjectRoot "src\backend"

Write-Host "================================================"
Write-Host " UIX 后端启动（Windows）"
Write-Host " 后端目录: $BackendDir"
Write-Host " 模式: $Mode"
Write-Host "================================================"

# 检查 .env 文件
$EnvFile = Join-Path $BackendDir ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Host "⚠️  未找到 src\backend\.env，正在切换到 local 环境..."
    Push-Location $ProjectRoot
    try {
        python scripts\switch_env.py local
    } catch {
        Write-Host "switch_env.py 执行失败，将使用默认值"
    }
    Pop-Location
}

# 检查端口是否占用
$PortInUse = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($PortInUse) {
    Write-Host "⚠️  端口 $Port 已被占用（PID: $($PortInUse.OwningProcess)）"
    Write-Host "请先终止占用进程或修改 Port 参数：.\scripts\start_backend.ps1 -Port 8001"
    exit 1
}

# 激活虚拟环境（若存在）
$VenvActivate = Join-Path $BackendDir ".venv\Scripts\Activate.ps1"
if (Test-Path $VenvActivate) {
    . $VenvActivate
    Write-Host "✅ 已激活虚拟环境: $VenvActivate"
} else {
    $VenvActivate2 = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"
    if (Test-Path $VenvActivate2) {
        . $VenvActivate2
        Write-Host "✅ 已激活虚拟环境: $VenvActivate2"
    }
}

Push-Location $BackendDir

try {
    if ($Mode -eq "production") {
        Write-Host "🚀 生产模式启动 (${Host}:${Port})..."
        python -m uvicorn app.main:app --host $Host --port $Port --workers 2
    } else {
        Write-Host "🔧 开发模式启动 (${Host}:${Port}, --reload)..."
        python -m uvicorn app.main:app --host $Host --port $Port --reload
    }
} finally {
    Pop-Location
}
