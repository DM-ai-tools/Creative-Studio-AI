$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "backend")

$pythonCandidates = @(
    (Join-Path $root "backend\venv313\Scripts\python.exe"),
    (Join-Path $root "backend\venv\Scripts\python.exe")
)
$venvPython = $null
foreach ($candidate in $pythonCandidates) {
    if (-not (Test-Path $candidate)) {
        continue
    }
    & $candidate --version *> $null
    if ($LASTEXITCODE -eq 0) {
        $venvPython = $candidate
        break
    }
}
if (-not $venvPython) {
    throw "No working backend virtual environment found. Run npm run setup from the project root first."
}

Write-Host "Running database migrations..."
& $venvPython -m alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    throw "Database migration failed. Run npm run db:setup from the project root, then start the backend again."
}

Write-Host "Starting backend on http://localhost:8000"
$uvicornArgs = @("-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000")
if ($env:CREATIVESTUDIO_BACKEND_RELOAD -eq "1") {
    $uvicornArgs += "--reload"
}
& $venvPython @uvicornArgs
