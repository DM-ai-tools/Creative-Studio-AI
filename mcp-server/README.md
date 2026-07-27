# CreativeStudio AI MCP Server

Connect **Claude Cowork**, Claude Desktop, or Claude Code to your CreativeStudio AI API so Claude can manage brands, briefs, variants, scripts, and Meta exports.

## What you get

| Tool area | Examples |
|---|---|
| Account | `health_check`, `get_me` |
| Brands | `list_brands`, `create_brand`, `get_brand_kit` |
| Briefs | `list_briefs`, `create_brief`, `generate_variants` |
| Variants | `list_variants`, `approve_variant`, `regenerate_variant` |
| Performance | `get_dashboard_stats`, `get_top_performers`, `get_fatigue_alerts` |
| Scripts | `generate_avatar_script`, `generate_strategy_preview`, `generate_website_script` |
| Meta | `get_meta_status`, `export_to_meta` |

## Prerequisites

1. CreativeStudio backend running (`http://localhost:8000` or your deployed API).
2. A CreativeStudio user (email + password), or a JWT access token.
3. Python 3.10+.

## Install

```powershell
cd "mcp-server"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
copy .env.example .env
# Edit .env with your API URL + login
```

## Claude Cowork (remote connector) — recommended

Cowork only supports **remote** MCP servers (public HTTPS). Local stdio servers do **not** work in Cowork.

### 1. Run Streamable HTTP locally (dev)

```powershell
python -m creativestudio_mcp --transport http --port 8100
```

MCP endpoint: `http://localhost:8100/mcp`

### 2. Expose HTTPS for Cowork

Use a tunnel while developing:

```powershell
# Example with ngrok (install from https://ngrok.com)
ngrok http 8100
```

Or deploy the Docker image to Railway / Render / Fly and use the public URL.

### 3. Add the connector in Claude

1. Open [Customize → Connectors](https://claude.ai/customize/connectors) (or Cowork → Settings → Connectors).
2. **Add custom connector** → paste your URL ending in `/mcp`  
   Example: `https://abc123.ngrok-free.app/mcp`
3. Save, enable the connector in the chat **+** menu.

Claude will call your MCP from Anthropic’s cloud — the CreativeStudio API URL in `.env` must also be reachable from the machine (or container) running this MCP server.

### Docker

```powershell
docker build -t creativestudio-mcp .
docker run --rm -p 8100:8100 --env-file .env creativestudio-mcp
```

## Claude Desktop (local stdio)

Edit `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "creativestudio": {
      "command": "C:\\Users\\Humruth\\Desktop\\CreativeStudio AI Code\\CreativeStudio AI Code\\mcp-server\\.venv\\Scripts\\python.exe",
      "args": ["-m", "creativestudio_mcp", "--transport", "stdio"],
      "env": {
        "CREATIVESTUDIO_API_URL": "http://localhost:8000/api/v1",
        "CREATIVESTUDIO_EMAIL": "admin@example.com",
        "CREATIVESTUDIO_PASSWORD": "your-password"
      }
    }
  }
}
```

Restart Claude Desktop. Ask: “List my CreativeStudio brands.”

## Claude Code

```bash
claude mcp add creativestudio --transport stdio -- \
  python -m creativestudio_mcp --transport stdio
```

Set the same env vars in your shell or Claude Code settings.

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `CREATIVESTUDIO_API_URL` | Yes | API base including `/api/v1` |
| `CREATIVESTUDIO_EMAIL` | Yes* | Login email |
| `CREATIVESTUDIO_PASSWORD` | Yes* | Login password |
| `CREATIVESTUDIO_ACCESS_TOKEN` | No | Skip login; use a JWT instead |
| `MCP_HOST` / `MCP_PORT` | No | HTTP bind (default `0.0.0.0:8100`) |

\*Or provide `CREATIVESTUDIO_ACCESS_TOKEN`.

## Example Cowork prompts

- “List my brands and create a brief for [Brand] promoting [offer] to [audience].”
- “Generate a 30s avatar script for our new product launch.”
- “Show dashboard stats and any fatigue alerts.”
- “Approve variant X and export it to Meta as campaign Y.”

## Security notes

- The MCP process holds CreativeStudio credentials and can create/delete briefs and approve variants.
- For Cowork, prefer a private deploy URL and rotate passwords if the tunnel URL leaks.
- Do not commit `.env` with real passwords.
