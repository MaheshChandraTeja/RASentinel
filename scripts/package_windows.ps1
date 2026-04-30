$ErrorActionPreference = "Stop"

$Root = Resolve-Path "$PSScriptRoot\.."
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Desktop = Join-Path $Root "desktop"

$BackendPython = Join-Path $Backend ".venv\Scripts\python.exe"
$BackendEntry = Join-Path $Backend "desktop_entry.py"
$BackendBundle = Join-Path $Desktop "resources\backend"
$BackendBuildTemp = Join-Path $Desktop "resources\backend-build"
$PyInstallerWork = Join-Path $Root "build\pyinstaller"
$Release = Join-Path $Root "release"

function Invoke-NativeStep {
  param(
    [Parameter(Mandatory = $true)]
    [string] $Label,

    [Parameter(Mandatory = $true)]
    [scriptblock] $Command
  )

  Write-Host $Label -ForegroundColor Cyan
  & $Command

  if ($LASTEXITCODE -ne 0) {
    throw "$Label failed with exit code $LASTEXITCODE"
  }
}

Write-Host "RASentinel Windows packaging started" -ForegroundColor Cyan

if (!(Test-Path $BackendPython)) {
  throw "Backend virtual environment Python was not found: $BackendPython"
}

if (!(Test-Path $BackendEntry)) {
  throw "Backend desktop entrypoint was not found: $BackendEntry"
}

Write-Host "Cleaning old packaging outputs..." -ForegroundColor Cyan
Remove-Item -Recurse -Force $PyInstallerWork -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $BackendBundle -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $BackendBuildTemp -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $Release -ErrorAction SilentlyContinue

New-Item -ItemType Directory -Force $BackendBundle | Out-Null
New-Item -ItemType Directory -Force $Release | Out-Null

Push-Location $Frontend
Invoke-NativeStep "Installing frontend dependencies..." { pnpm install }
Invoke-NativeStep "Building frontend..." { pnpm build }
Pop-Location

Push-Location $Backend
Invoke-NativeStep "Installing backend packaging dependency..." { & $BackendPython -m pip install pyinstaller }

Invoke-NativeStep "Building backend executable..." {
  & $BackendPython -m PyInstaller .\desktop_entry.py `
    --name rasentinel-backend `
    --onedir `
    --console `
    --clean `
    --noconfirm `
    --paths "$Backend" `
    --distpath "$BackendBuildTemp" `
    --workpath "$PyInstallerWork" `
    --specpath "$PyInstallerWork" `
    --collect-submodules app `
    --collect-submodules fastapi `
    --collect-submodules starlette `
    --collect-submodules uvicorn `
    --collect-submodules pydantic `
    --collect-submodules pydantic_settings `
    --collect-submodules sqlalchemy `
    --collect-submodules sklearn `
    --collect-submodules scipy `
    --collect-submodules numpy `
    --exclude-module torch `
    --hidden-import app.main `
    --hidden-import uvicorn.loops.auto `
    --hidden-import uvicorn.protocols.http.auto `
    --hidden-import uvicorn.protocols.websockets.auto
}
Pop-Location

$BuiltBackendDir = Join-Path $BackendBuildTemp "rasentinel-backend"
if (!(Test-Path $BuiltBackendDir)) {
  throw "PyInstaller backend output folder was not created: $BuiltBackendDir"
}

Write-Host "Copying backend bundle into Electron resources..." -ForegroundColor Cyan
Copy-Item -Recurse (Join-Path $BuiltBackendDir "*") $BackendBundle

$BackendExe = Join-Path $BackendBundle "rasentinel-backend.exe"
if ($env:CSC_LINK -and $env:CSC_KEY_PASSWORD) {
  Write-Host "Signing bundled backend executable..." -ForegroundColor Cyan

  $SignTool = Get-ChildItem `
    "C:\Program Files (x86)\Windows Kits\10\bin" `
    -Recurse `
    -Filter signtool.exe `
    -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -like "*\x64\signtool.exe" } |
    Select-Object -First 1

  if ($null -eq $SignTool) {
    Write-Warning "signtool.exe was not found. Backend sidecar will not be signed manually."
  } else {
    & $SignTool.FullName sign `
      /f $env:CSC_LINK `
      /p $env:CSC_KEY_PASSWORD `
      /fd SHA256 `
      /tr http://timestamp.digicert.com `
      /td SHA256 `
      "$BackendExe"

    if ($LASTEXITCODE -ne 0) {
      throw "Failed to sign backend executable."
    }
  }
}
if (!(Test-Path $BackendExe)) {
  throw "Backend executable was not created: $BackendExe"
}

Remove-Item -Recurse -Force $BackendBuildTemp -ErrorAction SilentlyContinue

Push-Location $Desktop
Invoke-NativeStep "Installing Electron dependencies..." { pnpm install }
Invoke-NativeStep "Building Electron Windows artifacts..." { pnpm dist }
Pop-Location

Write-Host ""
Write-Host "Packaging complete." -ForegroundColor Green
Write-Host "Release artifacts:" -ForegroundColor Green
Get-ChildItem $Release | Select-Object Name, Length, LastWriteTime
