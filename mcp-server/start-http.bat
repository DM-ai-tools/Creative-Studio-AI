@echo off
REM Start CreativeStudio MCP over Streamable HTTP (Claude Cowork)
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt ^&^& .venv\Scripts\pip install -e .
  exit /b 1
)
.venv\Scripts\python.exe -m creativestudio_mcp --transport http --host 0.0.0.0 --port 8100
