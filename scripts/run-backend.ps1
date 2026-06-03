$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "backend")

$venvPython = Join-Path $root "backend\venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Backend virtual environment not found. Run npm run setup from the project root first."
}

Write-Host "Running database migrations..."
& $venvPython -m alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    throw "Database migration failed. Run npm run db:setup from the project root, then start the backend again."
}

Write-Host "Starting backend on http://localhost:8000"
& $venvPython -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
