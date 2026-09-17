from __future__ import annotations

from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from .client import (
    DEFAULT_PAGE_SIZE,
    MAXIMUM_PAGE_SIZE,
    PlaneApiError,
    PlaneClient,
    optional_string,
    required_string,
    validate_page_size,
)
from .config import (
    PlaneConfigurationError,
    PlaneSettings,
    build_api_v1_url,
    get_settings,
)


SERVER_NAME = "plane-work-items-mcp"
SERVER_VERSION = "0.2.0"
PageSize = Annotated[int, Field(ge=1, le=MAXIMUM_PAGE_SIZE)]
NonEmptyString = Annotated[str, Field(min_length=1)]
READ_ONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
)


mcp = MCPServer(
    SERVER_NAME,
    version=SERVER_VERSION,
    description="Read-only tools for a self-hosted Plane workspace.",
    instructions="Use project IDs returned by list_projects for project-scoped reads.",
)


def _client() -> PlaneClient:
    return PlaneClient(get_settings())


async def _run_plane_call(method: Any, *arguments: Any, **keywords: Any) -> dict[str, Any]:
    return method(*arguments, **keywords)


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
async def list_projects(
    cursor: str | None = None,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """List projects visible to the configured Plane workspace."""
    final_page_size = validate_page_size(page_size)
    return await _run_plane_call(_client().list_projects, cursor=cursor, page_size=final_page_size)


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
async def list_modules(
    project_id: NonEmptyString,
    cursor: str | None = None,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """List active modules in a Plane project."""
    final_project_id = required_string({"project_id": project_id}, "project_id")
    final_page_size = validate_page_size(page_size)
    return await _run_plane_call(
        _client().list_modules,
        project_id=final_project_id,
        cursor=cursor,
        page_size=final_page_size,
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
async def list_module_work_items(
    project_id: NonEmptyString,
    module_id: NonEmptyString,
    cursor: str | None = None,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """List work items assigned to a Plane module."""
    final_project_id = required_string({"project_id": project_id}, "project_id")
    final_module_id = required_string({"module_id": module_id}, "module_id")
    final_page_size = validate_page_size(page_size)
    return await _run_plane_call(
        _client().list_module_work_items,
        project_id=final_project_id,
        module_id=final_module_id,
        cursor=cursor,
        page_size=final_page_size,
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
async def list_work_items(
    project_id: NonEmptyString,
    expand: str | None = None,
    cursor: str | None = None,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """List work items in a Plane project and optionally expand related metadata."""
    final_project_id = required_string({"project_id": project_id}, "project_id")
    final_expand = optional_string({"expand": expand}, "expand")
    final_page_size = validate_page_size(page_size)
    return await _run_plane_call(
        _client().list_work_items,
        project_id=final_project_id,
        expand=final_expand,
        cursor=cursor,
        page_size=final_page_size,
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
async def list_work_item_comments(
    project_id: NonEmptyString,
    work_item_id: NonEmptyString,
    cursor: str | None = None,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """List comments attached to a Plane work item."""
    final_project_id = required_string({"project_id": project_id}, "project_id")
    final_work_item_id = required_string({"work_item_id": work_item_id}, "work_item_id")
    final_page_size = validate_page_size(page_size)
    return await _run_plane_call(
        _client().list_work_item_comments,
        project_id=final_project_id,
        work_item_id=final_work_item_id,
        cursor=cursor,
        page_size=final_page_size,
    )


def main() -> None:
    """Run the Plane MCP server over the default stdio transport."""
    mcp.run(transport="stdio")


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAXIMUM_PAGE_SIZE",
    "PlaneApiError",
    "PlaneConfigurationError",
    "PlaneClient",
    "PlaneSettings",
    "SERVER_NAME",
    "SERVER_VERSION",
    "build_api_v1_url",
    "get_settings",
    "list_module_work_items",
    "list_modules",
    "list_projects",
    "list_work_item_comments",
    "list_work_items",
    "main",
    "mcp",
    "optional_string",
    "required_string",
    "validate_page_size",
]


if __name__ == "__main__":
    main()
