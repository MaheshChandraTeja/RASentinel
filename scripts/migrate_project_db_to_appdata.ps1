$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SourceDb = Join-Path $ProjectRoot "data\rasentinel.db"
$AppDataRoot = Join-Path $env:APPDATA "rasentinel-desktop"
$TargetDir = Join-Path $AppDataRoot "data"
$TargetDb = Join-Path $TargetDir "rasentinel.db"

if (-not (Test-Path $SourceDb)) {
  throw "Project database not found: $SourceDb"
}

New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null

if (Test-Path $TargetDb) {
  $Backup = Join-Path $TargetDir ("rasentinel.backup.{0}.db" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
  Copy-Item $TargetDb $Backup -Force
  Write-Host "Existing AppData DB backed up to:" -ForegroundColor Yellow
  Write-Host "  $Backup" -ForegroundColor Gray
}

Copy-Item $SourceDb $TargetDb -Force

Write-Host "Migrated project DB to AppData:" -ForegroundColor Green
Write-Host "  From: $SourceDb" -ForegroundColor Gray
Write-Host "  To:   $TargetDb" -ForegroundColor Gray
Write-Host "Close and restart Electron/backend before checking the UI." -ForegroundColor Cyan
