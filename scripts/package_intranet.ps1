param(
    [string]$OutputZip = "",
    [switch]$BuildFrontend,
    [switch]$KeepStaging
)

# Build intranet delivery zip. Stage in %TEMP% to avoid recursive copy.
$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
    Write-Host "[package_intranet] $Message"
}

function Resolve-OutputZip([string]$Root, [string]$RequestedPath) {
    if ([string]::IsNullOrWhiteSpace($RequestedPath)) {
        $name = "UIX-Graph-intranet-package-" + (Get-Date -Format "yyyy-MM-dd-HHmmss") + ".zip"
        return Join-Path $Root $name
    }

    if ([System.IO.Path]::IsPathRooted($RequestedPath)) {
        return $RequestedPath
    }

    return Join-Path $Root $RequestedPath
}

function Ensure-FrontendDist([string]$Root, [bool]$ShouldBuild) {
    $frontendDir = Join-Path $Root "src/frontend"
    $distIndex = Join-Path $frontendDir "dist/index.html"

    if ((Test-Path $distIndex) -and (-not $ShouldBuild)) {
        Write-Step "Existing dist found, skip frontend build"
        return
    }

    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) {
        throw "npm not found. Install Node.js first or provide src/frontend/dist manually."
    }

    Write-Step "Building frontend dist"
    Push-Location $frontendDir
    try {
        if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
            Write-Step "Installing frontend dependencies"
            & $npm.Source install --prefer-offline
            if ($LASTEXITCODE -ne 0) {
                throw "npm install failed, exit code=$LASTEXITCODE"
            }
        }

        Write-Step "Running npm run build"
        & $npm.Source run build
        if ($LASTEXITCODE -ne 0) {
            throw "npm run build failed, exit code=$LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }

    if (-not (Test-Path $distIndex)) {
        throw "Frontend build finished but dist/index.html is still missing."
    }
}

$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $root "docker-compose.yml"))) {
    throw "Cannot find repo root (docker-compose.yml) from $PSScriptRoot"
}

$outputZipPath = Resolve-OutputZip -Root $root -RequestedPath $OutputZip
$outputDir = Split-Path -Parent $outputZipPath
if (-not [string]::IsNullOrWhiteSpace($outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

Write-Step "Repo root: $root"
Write-Step "Output zip: $outputZipPath"
Write-Step "BuildFrontend: $BuildFrontend"

Ensure-FrontendDist -Root $root -ShouldBuild $BuildFrontend

$stagingParent = Join-Path $env:TEMP ("UIX-Graph-pack-" + (Get-Date -Format "yyyyMMddHHmmss"))
$staging = Join-Path $stagingParent "UIX-Graph"
New-Item -ItemType Directory -Path $staging -Force | Out-Null

$excludeDirs = @(
    # 运行时垃圾 / 虚拟环境
    "node_modules", "__pycache__", ".git", ".venv", "venv", "env", "ENV",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "htmlcov",
    # IDE / 工具私有
    ".cursor", ".vscode", ".idea", ".fleet",
    # Vite / 构建临时
    ".vite", "build",
    # 插件本地状态
    ".claude", ".codex", ".specstory",
    # 老 UI 归档(不在运行路径上,内网不需要)
    "archive",
    # 日志目录(运行时产物)
    "logs",
    # 打包历史 / 临时 staging
    "_intranet_pack_staging"
)
$xd = ($excludeDirs | ForEach-Object { "/XD"; $_ })
$xf = @(
    "/XF",
    # Python / 编译产物
    "*.pyc", "*.pyo",
    # OS 噪音
    "Thumbs.db", ".DS_Store", "desktop.ini",
    # 历史打包 zip(避免打包到上一轮 zip)
    "*.zip",
    # Cursor 聊天导出(防御性)
    "cursor_*.md",
    # 备份 / 草稿
    "*.bak", "*.tmp", "*.orig", "*.rej",
    # 本地 log；本机 .env 不打包(防密钥泄露) — 打包后改为由 .env.example 注入无密钥默认 .env
    "*.log", ".env", ".env.local"
)

try {
    Write-Step "Copying files into temporary staging directory"
    & robocopy $root $staging /E @xd @xf /NFL /NDL /NJH /NJS /NC /NS | Out-Null
    $rc = $LASTEXITCODE
    if ($rc -ge 8) {
        throw "robocopy failed with exit code $rc"
    }

    # 不把开发者本机 src/**/.env 打入 zip ；内网需有默认 .env：从 .env.example 覆写到 staging
    $backendEx = Join-Path $root "src\backend\.env.example"
    $backendOut = Join-Path $staging "src\backend\.env"
    if (Test-Path $backendEx) {
        Copy-Item -LiteralPath $backendEx -Destination $backendOut -Force
        Write-Step "Injected src/backend/.env (copied from .env.example, not your local .env)"
    } else {
        Write-Warning "[package_intranet] Missing $backendEx — package will not contain backend .env"
    }
    $frontendEx = Join-Path $root "src\frontend\.env.example"
    $frontendOut = Join-Path $staging "src\frontend\.env"
    if (Test-Path $frontendEx) {
        Copy-Item -LiteralPath $frontendEx -Destination $frontendOut -Force
        Write-Step "Injected src/frontend/.env (from .env.example)"
    }

    if (Test-Path $outputZipPath) {
        Remove-Item $outputZipPath -Force
    }

    Write-Step "Creating zip archive"
    & tar.exe -a -c -f $outputZipPath -C $stagingParent "UIX-Graph"
    if ($LASTEXITCODE -ne 0) {
        throw "tar.exe packaging failed, exit code=$LASTEXITCODE"
    }

    $item = Get-Item $outputZipPath
    Write-Step ("Packaging completed: " + $item.FullName)
    Write-Step ("Size: " + [Math]::Round($item.Length / 1MB, 2) + " MB")
    $item | Format-List FullName, Length, LastWriteTime
}
finally {
    if ($KeepStaging) {
        Write-Step "Keeping staging directory: $stagingParent"
    }
    elseif (Test-Path $stagingParent) {
        Remove-Item $stagingParent -Recurse -Force
    }
}
