# One command (Windows PowerShell): install the locked Python environment and start NetCoop AI
# (API + three A2A specialist agents + the React app) at http://127.0.0.1:8000/
# Needs uv (https://docs.astral.sh/uv/); uv fetches Python 3.12 if it is missing.
#   powershell -ExecutionPolicy Bypass -File start.ps1 [--port 8000]
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
uv sync --locked
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not (Test-Path 'frontend/dist/index.html') -and (Get-Command npm -ErrorAction SilentlyContinue)) {
  Push-Location frontend
  npm ci --no-audit --no-fund
  if ($LASTEXITCODE -eq 0) { npm run build }
  Pop-Location
}
uv run python scripts/run_local.py @args
exit $LASTEXITCODE
