$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$BackendPython = Join-Path $Root "backend\.venv\Scripts\python.exe"

if (!(Test-Path $BackendPython)) {
  throw "Backend virtual environment Python was not found at $BackendPython. Create the backend .venv before launching desktop dev mode."
}

Write-Host "Preparing RASentinel branding assets..."
& $BackendPython (Join-Path $Root "scripts\prepare_app_assets.py")

Write-Host "Starting Vite frontend in a separate PowerShell window..."
Start-Process powershell.exe -ArgumentList @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-Command",
  "cd '$Root\frontend'; pnpm dev"
)

Write-Host "Starting RASentinel desktop shell in dev mode..."
Push-Location (Join-Path $Root "desktop")
if (!(Test-Path "node_modules")) {
  pnpm install
}
$env:RASENTINEL_PYTHON_PATH = $BackendPython
$env:RASENTINEL_DESKTOP_DEV = "1"
pnpm dev
Pop-Location
