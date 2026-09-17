# Plane Work Items MCP

Small, dependency-free, read-only MCP server for a self-hosted Plane instance. It lists projects,
modules, work items, and work-item comments through Plane's v1 API.

## Configuration

The server reads credentials only from its process environment:

```text
PLANE_BASE_URL=https://plane.example.com/api
PLANE_WORKSPACE_SLUG=your-workspace
PLANE_API_KEY=plane_api_your_key
```

`PLANE_BASE_URL` may end with the instance host, `/api`, or `/api/v1`; the server normalizes it to
the API v1 root. Do not commit these values.

## Run

```bash
PLANE_BASE_URL=https://plane.example.com/api \
PLANE_WORKSPACE_SLUG=your-workspace \
PLANE_API_KEY=plane_api_your_key \
python3 -u /mnt/sda1/plane/mcp/src/plane_mcp/server.py
```

The server uses newline-delimited JSON-RPC over standard input/output. Standard output is reserved
for MCP messages and no credentials are emitted.

## Codex configuration

```toml
[mcp_servers.plane_work_items]
command = "python3"
args = ["-u", "/mnt/sda1/plane/mcp/src/plane_mcp/server.py"]

[mcp_servers.plane_work_items.env]
PLANE_BASE_URL = "https://plane.example.com/api"
PLANE_WORKSPACE_SLUG = "your-workspace"
PLANE_API_KEY = "plane_api_your_key"
```

## Tools

- `list_projects`
- `list_modules`
- `list_module_work_items`
- `list_work_items`
- `list_work_item_comments`

All tools are read-only. Use `next_cursor` until `next_page_results` is `false`.

## Protocol compatibility

The server supports the current `2026-07-28` MCP `server/discover` flow and the legacy
`initialize` flow used by 2024–2025 hosts. It implements `tools/list`, `tools/call`, and `ping`.

## Test

```bash
PYTHONPATH=/mnt/sda1/plane/mcp/src python3 -m unittest discover \
    -s /mnt/sda1/plane/mcp/tests -v
```
