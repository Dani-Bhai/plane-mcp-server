# Plane MCP

Native, read-only MCP server for a self-hosted Plane workspace. It exposes Plane discovery,
metadata, project, work-item, comment, and context reads through the official MCP Python SDK.

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
- `resolve_project`
- `get_project`
- `list_modules`
- `list_project_resources`
- `list_workspace_members`
- `resolve_project_resource`
- `list_module_work_items`
- `get_work_item`
- `list_work_items`
- `search_work_items`
- `list_work_item_comments`

All tools are read-only and idempotent. Use `resolve_project` with a project name, identifier, or
UUID, then use `resolve_project_resource` for states, labels, cycles, modules, milestones, releases,
members, or work-item types. Project-scoped tools keep the project UUID explicit. Structured
work-item filters resolve names safely and are compiled to Plane PQL; raw PQL remains available for
advanced queries. Use the `next_cursor` returned by Plane as the `cursor` argument for the next page.
`page_size` must be between `1` and `100`.

## Resources

- `plane://workspace` — the configured workspace's project context.
- `plane://projects/{project_id}` — a project context template.
- `plane://projects/{project_id}/work-items/{work_item_id}` — a work-item context template.

The resource payloads preserve the Plane response while providing stable, cacheable MCP resource
URIs. Workspace and project context should be refreshed when project membership or metadata changes;
work-item context should be refreshed after edits made outside the current read flow.

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
- `plane_mcp.resolution` performs bounded, deterministic UUID/identifier/name resolution.
- `plane_mcp.query` compiles structured work-item filters into PQL.
- `plane_mcp.config` validates environment configuration and normalizes the API URL.
- `tests/` covers native MCP discovery/calls, resources, resolution, PQL/filter construction,
  configuration, request construction, pagination, and API failure paths.

## Migration from v0.2

The v0.2 tool names and required `PLANE_*` environment variables are preserved. Replace the
repository-path command with the installed `plane-mcp` command. The v0.3 tools add native
resolution and context reads without changing the existing read-only behavior; hosts should
continue to connect over stdio.
