$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$BackendPython = Join-Path $Root "backend\.venv\Scripts\python.exe"

if (!(Test-Path $BackendPython)) {
  throw "Backend virtual environment Python was not found at $BackendPython. Create the backend .venv before launching desktop mode."
}

Write-Host "Preparing RASentinel branding assets..."
& $BackendPython (Join-Path $Root "scripts\prepare_app_assets.py")

Write-Host "Building frontend..."
Push-Location (Join-Path $Root "frontend")
pnpm build
Pop-Location

Write-Host "Starting RASentinel desktop shell..."
Push-Location (Join-Path $Root "desktop")
if (!(Test-Path "node_modules")) {
  pnpm install
}
$env:RASENTINEL_PYTHON_PATH = $BackendPython
pnpm start
Pop-Location
