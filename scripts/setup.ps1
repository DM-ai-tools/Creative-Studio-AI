$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Ensure-FileFromExample {
    param(
        [string]$Target,
        [string]$Example
    )

    if (-not (Test-Path $Target)) {
        if (-not (Test-Path $Example)) {
            throw "Missing example file: $Example"
        }

        Copy-Item $Example $Target
        Write-Host "Created $Target from $Example"
        return
    }

    Write-Host "Using existing $Target"
}

Ensure-FileFromExample -Target (Join-Path $root "backend\.env") -Example (Join-Path $root "backend\.env.example")
Ensure-FileFromExample -Target (Join-Path $root "frontend\.env.local") -Example (Join-Path $root "frontend\.env.example")

$venvPython = Join-Path $root "backend\venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating backend virtual environment..."
    python -m venv (Join-Path $root "backend\venv")
}

$uploadsDir = Join-Path $root "backend\uploads"
if (-not (Test-Path $uploadsDir)) {
    New-Item -ItemType Directory -Path $uploadsDir | Out-Null
    Write-Host "Created $uploadsDir"
}

Write-Host "Installing backend dependencies..."
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $root "backend\requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Backend dependency install failed. Check Python 3.11+ and install Microsoft C++ Build Tools if needed."
}


Write-Host "Installing frontend dependencies..."
npm install --prefix (Join-Path $root "frontend")

if (-not (Test-Path (Join-Path $root "node_modules"))) {
    Write-Host "Installing root dev dependencies..."
    npm install
}

Write-Host "Setup complete."
