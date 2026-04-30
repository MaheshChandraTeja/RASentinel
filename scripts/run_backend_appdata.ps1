param(
  [int]$Port = 8000,
  [string]$HostName = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot "backend"
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$AppDataRoot = Join-Path $env:APPDATA "rasentinel-desktop"
$DataDir = Join-Path $AppDataRoot "data"

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

$env:RASENTINEL_DATA_DIR = $AppDataRoot
$env:RASENTINEL_DATABASE_URL = "sqlite:///$(($DataDir -replace '\\','/'))/rasentinel.db"
$env:RASENTINEL_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"

Write-Host "RASentinel backend using app data:" -ForegroundColor Cyan
Write-Host "  $DataDir" -ForegroundColor Gray

Push-Location $BackendDir
try {
  if (-not (Test-Path $VenvPython)) {
    throw "Backend virtual environment not found at $VenvPython"
  }

  & $VenvPython -m uvicorn app.main:app --host $HostName --port $Port --reload
}
finally {
  Pop-Location
}
