# CreativeStudio AI — MCP Server
#
# Build:  docker build -t creativestudio-mcp .
# Run:    docker run -p 8100:8100 --env-file .env creativestudio-mcp

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt pyproject.toml README.md ./
COPY creativestudio_mcp ./creativestudio_mcp

RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -e .

ENV MCP_TRANSPORT=http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8100

EXPOSE 8100

CMD ["python", "-m", "creativestudio_mcp", "--transport", "http", "--host", "0.0.0.0", "--port", "8100"]
