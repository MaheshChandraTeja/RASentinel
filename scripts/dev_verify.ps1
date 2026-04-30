$ErrorActionPreference = "Stop"

Write-Host "==> Backend tests" -ForegroundColor Cyan
Push-Location backend
pytest
Pop-Location

Write-Host "==> Frontend build and smoke tests" -ForegroundColor Cyan
Push-Location frontend
pnpm install
pnpm test
pnpm build
Pop-Location

Write-Host "==> Release benchmark" -ForegroundColor Cyan
python .\scripts\run_backend_benchmark.py --sample-count 300 --healthy-trials 2 --no-isolation-forest

Write-Host "RASentinel release readiness checks completed." -ForegroundColor Green
