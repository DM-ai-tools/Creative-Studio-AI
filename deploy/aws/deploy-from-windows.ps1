# Deploy Creative Studio AI to EC2 from Windows (PuTTY plink/pscp + .ppk key).
param(
    [string]$ServerIp = "13.235.37.173",
    [string]$SshUser = "ubuntu",
    [string]$PpkPath = "$env:USERPROFILE\Downloads\DM-Creative-studioppk.ppk",
    [string]$HostKey = "ssh-ed25519 SHA256:jTOaSeVI4b8N91dCskmU0wNyKUR/TsJPI+fFkOa3X7I",
    [string]$PublicOrigin = "http://creativestudio.tools"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$TarPath = Join-Path $env:TEMP "creativestudio-deploy.tar.gz"

function Get-PuttyTool($name) {
    $portable = Join-Path $env:TEMP "putty-portable\$name.EXE"
    if (Test-Path $portable) { return $portable }
    $installed = Join-Path ${env:ProgramFiles} "PuTTY\$name.exe"
    if (Test-Path $installed) { return $installed }
    throw "Missing $name. Download PuTTY portable or install PuTTY."
}

$Plink = Get-PuttyTool "PLINK"
$Pscp = Get-PuttyTool "PSCP"

if (-not (Test-Path $PpkPath)) {
    throw "PPK not found: $PpkPath"
}

$plinkTarget = "${SshUser}@${ServerIp}"
$plinkBase = @("-batch", "-hostkey", $HostKey, "-i", $PpkPath, $plinkTarget)
$pscpBase = @("-batch", "-hostkey", $HostKey, "-i", $PpkPath)

Write-Host "==> Packaging project..."
if (Test-Path $TarPath) { Remove-Item $TarPath -Force }
Write-Host "==> Clearing read-only flags (OneDrive/Windows)..."
cmd /c "attrib -R `"$RepoRoot\*.*`" /S /D" | Out-Null
Push-Location $RepoRoot
tar -czf $TarPath `
  --exclude=node_modules `
  --exclude=frontend/node_modules `
  --exclude=frontend/.next `
  --exclude=backend/venv `
  --exclude=backend/venv313 `
  --exclude=backend/uploads `
  --exclude=mcp-server/.venv `
  --exclude=verification `
  --exclude=.pytest_cache `
  --exclude=backend/.pytest_cache `
  --exclude=backend/tests `
  --exclude=.git `
  --exclude=__pycache__ .
Pop-Location

function Convert-ToUnixLf([string]$text) {
    return ($text -replace "`r`n", "`n" -replace "`r", "`n")
}

Write-Host "==> Bootstrapping server (Docker)..."
$setupScript = Convert-ToUnixLf (Get-Content (Join-Path $PSScriptRoot "setup-server.sh") -Raw)
$setupScript | & $Plink @plinkBase "bash -s"

Write-Host "==> Uploading archive and config..."
& $Pscp @pscpBase $TarPath "${plinkTarget}:/tmp/creativestudio-deploy.tar.gz"

$backendEnv = Join-Path $RepoRoot "backend\.env"
if (-not (Test-Path $backendEnv)) {
    throw "Missing backend/.env - copy from backend/.env.example and add API keys."
}
& $Pscp @pscpBase $backendEnv "${plinkTarget}:/tmp/backend.env"

$deployEnvLocal = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $deployEnvLocal)) {
    $pgPass = -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
    $redisPass = -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
    $lines = @(
        "PUBLIC_ORIGIN=$PublicOrigin"
        "POSTGRES_DB=creativestudio"
        "POSTGRES_USER=csuser"
        "POSTGRES_PASSWORD=$pgPass"
        "REDIS_PASSWORD=$redisPass"
        "NEXT_PUBLIC_APP_NAME=CreativeStudio AI"
    )
    $lines | Set-Content -Path $deployEnvLocal -Encoding ascii
    Write-Host "Created deploy/aws/.env with generated database passwords."
}
& $Pscp @pscpBase $deployEnvLocal "${plinkTarget}:/tmp/deploy.env"

$remoteDeployPath = Join-Path $env:TEMP "remote-deploy-unix.sh"
Convert-ToUnixLf (Get-Content (Join-Path $PSScriptRoot "remote-deploy.sh") -Raw) | Set-Content -Path $remoteDeployPath -NoNewline -Encoding ascii
& $Pscp @pscpBase $remoteDeployPath "${plinkTarget}:/tmp/remote-deploy.sh"

Write-Host "==> Building containers on server (first run may take 10-20 minutes)..."
& $Plink @plinkBase "chmod +x /tmp/remote-deploy.sh && PUBLIC_ORIGIN='$PublicOrigin' bash /tmp/remote-deploy.sh"

Write-Host ""
Write-Host "Done."
Write-Host "  App:    $PublicOrigin"
Write-Host "  API:    $PublicOrigin/api/v1"
Write-Host "  Health: $PublicOrigin/health"
