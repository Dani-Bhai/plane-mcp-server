# Plane MCP

Native, read-only MCP server for a self-hosted Plane workspace. It exposes Plane project, module,
work-item, and comment reads through the official MCP Python SDK.

## Requirements

- Python 3.10+
- A self-hosted Plane instance with an API key

## Install

From a checkout:

```bash
python3 -m pip install .
```

For development and tests:

```bash
python3 -m pip install '.[dev]'
```

The package installs the `plane-mcp` command.

## Configuration

The server reads credentials only from its process environment:

```text
PLANE_BASE_URL=https://plane.example.com
PLANE_WORKSPACE_SLUG=your-workspace
PLANE_API_KEY=plane_api_your_key
```

`PLANE_BASE_URL` may be the instance host, a URL ending in `/api`, or a URL ending in `/api/v1`.
The server normalizes it to the API v1 root. `PLANE_REQUEST_TIMEOUT_SECONDS` is optional and
defaults to `30`.

Do not commit credentials or place them in tool arguments.

## Run locally

The default transport is stdio:

```bash
PLANE_BASE_URL=https://plane.example.com \
PLANE_WORKSPACE_SLUG=your-workspace \
PLANE_API_KEY=plane_api_your_key \
plane-mcp
```

Standard output is reserved for MCP messages. Diagnostics should not contain credentials.

## Codex configuration

```toml
[mcp_servers.plane]
command = "plane-mcp"

[mcp_servers.plane.env]
PLANE_BASE_URL = "https://plane.example.com"
PLANE_WORKSPACE_SLUG = "your-workspace"
PLANE_API_KEY = "plane_api_your_key"
```

## Tools

- `list_projects`
- `list_modules`
- `list_module_work_items`
- `list_work_items`
- `list_work_item_comments`

All tools are read-only and idempotent. Project-scoped tools require a project UUID. Use the
`next_cursor` returned by Plane as the `cursor` argument for the next page. `page_size` must be
between `1` and `100`.

## Development

The server object is exported as `plane_mcp.server:mcp`, so it can be inspected with the MCP
tooling:

```bash
python3 -m pip install '.[dev]'
mcp dev --with-editable . dev_server.py:mcp
```

Run the automated suite with coverage:

```bash
PYTHONPATH=src python3 -m coverage run --branch -m pytest
python3 -m coverage report -m --include='src/plane_mcp/*.py'
```

## Architecture

- `plane_mcp.server` registers typed MCP tools and owns the stdio entry point.
- `plane_mcp.client` contains the injectable Plane v1 HTTP client and response/error handling.
- `plane_mcp.config` validates environment configuration and normalizes the API URL.
- `tests/` covers native MCP discovery/calls, tool validation, configuration, request construction,
  pagination, and API failure paths.

## Migration from v0.1

The five tool names and the required `PLANE_*` environment variables are preserved. Replace the
repository-path command with the installed `plane-mcp` command. The server now uses the official
MCP SDK for protocol handling; hosts should continue to connect over stdio.
