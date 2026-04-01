# ============================================================
# UIX 前端启动脚本（Windows PowerShell）
# 使用方式（在项目根目录执行）：
#   .\scripts\start_frontend.ps1               # 开发模式
#   .\scripts\start_frontend.ps1 build         # 生产构建
# ============================================================
param(
    [string]$Mode = "dev"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$FrontendDir = Join-Path $ProjectRoot "src\frontend"

Write-Host "================================================"
Write-Host " UIX 前端（Windows）"
Write-Host " 目录: $FrontendDir"
Write-Host " 模式: $Mode"
Write-Host "================================================"

Push-Location $FrontendDir

try {
    # 检查 node_modules
    if (-not (Test-Path "node_modules")) {
        Write-Host "📦 安装依赖..."
        npm ci
    }

    if ($Mode -eq "build") {
        Write-Host "🔨 生产构建..."
        npm run build
        Write-Host "✅ 构建完成，产物在: $FrontendDir\dist\"
        Write-Host "   将 dist\ 内容复制到 Nginx 静态目录即可"
    } else {
        Write-Host "🔧 开发服务器启动（http://localhost:3000）..."
        npm run dev
    }
} finally {
    Pop-Location
}
