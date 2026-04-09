#Requires -Version 5.1
<#
  在 docker compose 与后端已就绪时，解析锚点 failure_id 并请求接口 3。
  用法（仓库根目录）:
    $env:UIX_ROOT = (Get-Location).Path
    $env:APP_ENV = "local"
    $env:METRIC_SOURCE_MODE = "real"
    cd src/backend; python -m uvicorn app.main:app --port 8000
  另开终端:
    .\scripts\verify_docker_e2e.ps1
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$sql = @"
SELECT id FROM lo_batch_equipment_performance
WHERE equipment='SSB8000' AND chuck_id=1 AND lot_id=101 AND wafer_index=7 AND reject_reason=6
ORDER BY id DESC LIMIT 1;
"@
$fid = docker exec uix-mysql mysql -uroot -proot datacenter -N -e $sql 2>$null
$fid = ($fid | Out-String).Trim()
if (-not $fid) {
    Write-Error "未解析到 failure_id：请确认 uix-mysql 已启动且已执行 init_docker_db.sql"
}
$rtSql = "SELECT UNIX_TIMESTAMP(wafer_product_start_time) * 1000 FROM lo_batch_equipment_performance WHERE id=$fid LIMIT 1;"
$requestTime = docker exec uix-mysql mysql -uroot -proot datacenter -N -e $rtSql 2>$null
$requestTime = ($requestTime | Out-String).Trim()
if (-not $requestTime) { $requestTime = "1768034700000" }
$base = "http://127.0.0.1:8000/api/v1/reject-errors/$fid/metrics"
$url = "${base}?requestTime=$requestTime"
Write-Host "GET $url"
try {
    $r = Invoke-RestMethod -Uri $url -Method Get
    $r.data.metrics | Format-Table name, value, status -AutoSize
} catch {
    Write-Error $_
}
