# 生成内网传阅压缩包：排除依赖与缓存，staging 在 %TEMP% 避免 robocopy 递归进自身。
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $root "docker-compose.yml"))) {
    throw "Cannot find repo root (docker-compose.yml) from $PSScriptRoot"
}
$stagingParent = Join-Path $env:TEMP ("UIX-Graph-pack-" + (Get-Date -Format "yyyyMMddHHmmss"))
$staging = Join-Path $stagingParent "UIX-Graph"
New-Item -ItemType Directory -Path $staging -Force | Out-Null

# 内网启动会直接校验 src/frontend/dist/index.html，打包前先确认产物存在。
$frontendDistIndex = Join-Path $root "src/frontend/dist/index.html"
if (-not (Test-Path $frontendDistIndex)) {
    throw "Missing prebuilt frontend dist: $frontendDistIndex`nPlease run: cd src/frontend; npm install; npm run build"
}

$excludeDirs = @(
    "node_modules", "__pycache__", ".git", ".venv", "venv", "env", "ENV",
    ".pytest_cache", ".cursor", ".vscode", ".idea", "build",
    ".vite", ".claude", "_intranet_pack_staging"
)
$xd = ($excludeDirs | ForEach-Object { "/XD"; $_ })
$xf = @(
    "/XF", "UIX-Graph-intranet-package.zip", "*.pyc", "Thumbs.db", ".DS_Store"
)
& robocopy $root $staging /E @xd @xf /NFL /NDL /NJH /NJS /NC /NS | Out-Null
$rc = $LASTEXITCODE
if ($rc -ge 8) { throw "robocopy failed with exit code $rc" }
$out = Join-Path $root "UIX-Graph-intranet-package.zip"
Remove-Item $out -Force -ErrorAction SilentlyContinue
& tar.exe -a -c -f $out -C $stagingParent "UIX-Graph"
Remove-Item $stagingParent -Recurse -Force
Get-Item $out | Format-List FullName, Length, LastWriteTime
