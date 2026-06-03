$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$sqlFile = Join-Path $root "scripts\setup-database.sql"
$initFile = Join-Path $root "init.sql"

function Get-PsqlPath {
    $command = Get-Command psql -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @(
        "C:\Program Files\PostgreSQL\16\bin\psql.exe",
        "C:\Program Files\PostgreSQL\15\bin\psql.exe",
        "C:\Program Files\PostgreSQL\14\bin\psql.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    throw "psql was not found. Install PostgreSQL or add psql to PATH, then run this script again."
}

$psql = Get-PsqlPath
$venvPython = Join-Path $root "backend\venv\Scripts\python.exe"

function Get-EnvValue {
    param(
        [string]$Key,
        [string]$FilePath
    )

    if (-not (Test-Path $FilePath)) {
        return $null
    }

    $line = Get-Content $FilePath | Where-Object { $_ -match "^$Key=" } | Select-Object -First 1
    if (-not $line) {
        return $null
    }

    return $line.Split("=", 2)[1]
}

$rootEnv = Join-Path $root ".env"
$appPassword = Get-EnvValue -Key "POSTGRES_PASSWORD" -FilePath $rootEnv
$adminPassword = if ($env:POSTGRES_ADMIN_PASSWORD) { $env:POSTGRES_ADMIN_PASSWORD } else { $appPassword }

if (-not $adminPassword) {
    throw "Set POSTGRES_PASSWORD in .env or POSTGRES_ADMIN_PASSWORD before running database setup."
}

Write-Host "Creating PostgreSQL role and database creativestudioai..."
$env:PGPASSWORD = $adminPassword
& $psql -U postgres -w -f $sqlFile

Write-Host "Applying schema from init.sql..."
$env:PGPASSWORD = $appPassword
& $psql -U creativestudioai -d creativestudioai -w -f $initFile

if (Test-Path $venvPython) {
    Write-Host "Marking Alembic migrations as applied..."
    Push-Location (Join-Path $root "backend")
    & $venvPython -m alembic stamp head
    Pop-Location
}

Write-Host "Database setup complete."
