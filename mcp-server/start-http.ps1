# Start CreativeStudio MCP over Streamable HTTP (Claude Cowork)
Set-Location $PSScriptRoot
if (-not (Test-Path .\.venv\Scripts\python.exe)) {
  Write-Host "Creating venv and installing..."
  python -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -r requirements.txt
  .\.venv\Scripts\python.exe -m pip install -e .
}
if (-not (Test-Path .\.env)) {
  Copy-Item .\.env.example .\.env
  Write-Host "Created .env — edit CREATIVESTUDIO_EMAIL / PASSWORD / API_URL, then re-run."
  exit 1
}
Write-Host "MCP endpoint: http://localhost:8100/mcp"
Write-Host "For Claude Cowork, expose this URL with HTTPS (ngrok / Railway) and add as a custom connector."
.\.venv\Scripts\python.exe -m creativestudio_mcp --transport http --host 0.0.0.0 --port 8100
