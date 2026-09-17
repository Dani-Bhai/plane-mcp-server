from __future__ import annotations

import json
from typing import Annotated, Any, Literal

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
from .query import build_work_item_pql
from .resolution import resolve_named_item


SERVER_NAME = "plane-work-items-mcp"
SERVER_VERSION = "0.3.0"
PageSize = Annotated[int, Field(ge=1, le=MAXIMUM_PAGE_SIZE)]
NonEmptyString = Annotated[str, Field(min_length=1)]
ProjectResource = Literal[
    "cycles",
    "labels",
    "members",
    "milestones",
    "modules",
    "releases",
    "states",
    "work_item_types",
]
Priority = Literal["urgent", "high", "medium", "low", "none"]
READ_ONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
)
RESOURCE_FILTERS = {
    "state": "states",
    "assignee": "members",
    "label": "labels",
    "cycle": "cycles",
    "module": "modules",
    "milestone": "milestones",
}


mcp = MCPServer(
    SERVER_NAME,
    version=SERVER_VERSION,
    description="Read-only tools and resources for a self-hosted Plane workspace.",
    instructions=(
        "Resolve project and metadata names before composing project-scoped queries. "
        "Use project IDs returned by list_projects for project-scoped reads."
    ),
)


def _client() -> PlaneClient:
    return PlaneClient(get_settings())


async def _run_plane_call(method: Any, *arguments: Any, **keywords: Any) -> dict[str, Any]:
    return method(*arguments, **keywords)


def _resolved_item_id(payload: dict[str, Any], query: str, resource: str) -> str:
    resolved = resolve_named_item(payload, query, resource)
    item_id = resolved.get("id", resolved.get("uuid"))

    if not isinstance(item_id, str) or not item_id.strip():
        raise ValueError(f"Resolved {resource} value {query!r} has no usable id.")

    return item_id


def _resolve_filter_ids(
    client: PlaneClient,
    project_id: str,
    filters: dict[str, str | None],
) -> dict[str, str | None]:
    resolved: dict[str, str | None] = {}
    for field, value in filters.items():
        if value is None:
            resolved[field] = None
            continue
        resource = RESOURCE_FILTERS[field]
        payload = client.list_project_resources(
            project_id=project_id,
            resource=resource,
            page_size=MAXIMUM_PAGE_SIZE,
        )
        resolved[field] = _resolved_item_id(payload, value, resource)
    return resolved


def _work_item_pql(
    client: PlaneClient,
    project_id: str,
    *,
    state: str | None,
    assignee: str | None,
    label: str | None,
    cycle: str | None,
    module: str | None,
    milestone: str | None,
    priority: str | None,
    target_date_before: str | None,
    target_date_after: str | None,
    pql: str | None,
) -> str | None:
    resolved = _resolve_filter_ids(
        client,
        project_id,
        {
            "state": state,
            "assignee": assignee,
            "label": label,
            "cycle": cycle,
            "module": module,
            "milestone": milestone,
        },
    )
    return build_work_item_pql(
        state=resolved["state"],
        assignee=resolved["assignee"],
        label=resolved["label"],
        cycle=resolved["cycle"],
        module=resolved["module"],
        milestone=resolved["milestone"],
        priority=priority,
        target_date_before=target_date_before,
        target_date_after=target_date_after,
        pql=pql,
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
async def list_projects(
    cursor: str | None = None,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """List projects visible to the configured Plane workspace."""
    final_page_size = validate_page_size(page_size)
    return await _run_plane_call(_client().list_projects, cursor=cursor, page_size=final_page_size)


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
async def resolve_project(query: NonEmptyString) -> dict[str, Any]:
    """Resolve a project by UUID, identifier, or unique name."""
    final_query = required_string({"query": query}, "query")
    client = _client()
    payload = client.list_projects(page_size=MAXIMUM_PAGE_SIZE)
    return {"query": final_query, "match": resolve_named_item(payload, final_query, "project")}


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
async def get_project(
    project_id: NonEmptyString,
    expand: str | None = None,
) -> dict[str, Any]:
    """Retrieve one Plane project by UUID."""
    final_project_id = required_string({"project_id": project_id}, "project_id")
    final_expand = optional_string({"expand": expand}, "expand")
    return await _run_plane_call(_client().get_project, project_id=final_project_id, expand=final_expand)


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
async def list_project_resources(
    project_id: NonEmptyString,
    resource: ProjectResource,
    cursor: str | None = None,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """List states, labels, cycles, modules, milestones, releases, members, or work-item types."""
    final_project_id = required_string({"project_id": project_id}, "project_id")
    final_page_size = validate_page_size(page_size)
    return await _run_plane_call(
        _client().list_project_resources,
        project_id=final_project_id,
        resource=resource,
        cursor=cursor,
        page_size=final_page_size,
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
async def list_workspace_members(
    cursor: str | None = None,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """List members visible in the configured Plane workspace."""
    final_page_size = validate_page_size(page_size)
    return await _run_plane_call(_client().list_workspace_members, cursor=cursor, page_size=final_page_size)


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
async def resolve_project_resource(
    project_id: NonEmptyString,
    resource: ProjectResource,
    query: NonEmptyString,
) -> dict[str, Any]:
    """Resolve a project resource by UUID or unique name."""
    final_project_id = required_string({"project_id": project_id}, "project_id")
    final_query = required_string({"query": query}, "query")
    payload = _client().list_project_resources(project_id=final_project_id, resource=resource, page_size=MAXIMUM_PAGE_SIZE)
    return {
        "project_id": final_project_id,
        "resource": resource,
        "query": final_query,
        "match": resolve_named_item(payload, final_query, resource),
    }


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
async def get_work_item(
    project_id: NonEmptyString,
    work_item_id: NonEmptyString,
    expand: str | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Retrieve one Plane work item by UUID."""
    final_project_id = required_string({"project_id": project_id}, "project_id")
    final_work_item_id = required_string({"work_item_id": work_item_id}, "work_item_id")
    final_expand = optional_string({"expand": expand}, "expand")
    final_fields = optional_string({"fields": fields}, "fields")
    return await _run_plane_call(
        _client().get_work_item,
        project_id=final_project_id,
        work_item_id=final_work_item_id,
        expand=final_expand,
        fields=final_fields,
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
async def list_work_items(
    project_id: NonEmptyString,
    expand: str | None = None,
    cursor: str | None = None,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
    pql: str | None = None,
    fields: str | None = None,
    state: str | None = None,
    assignee: str | None = None,
    label: str | None = None,
    cycle: str | None = None,
    module: str | None = None,
    milestone: str | None = None,
    priority: Priority | None = None,
    target_date_before: str | None = None,
    target_date_after: str | None = None,
) -> dict[str, Any]:
    """List work items with optional PQL and name-based structured filters."""
    final_project_id = required_string({"project_id": project_id}, "project_id")
    final_expand = optional_string({"expand": expand}, "expand")
    final_pql = optional_string({"pql": pql}, "pql")
    final_fields = optional_string({"fields": fields}, "fields")
    final_page_size = validate_page_size(page_size)
    client = _client()
    final_work_item_pql = _work_item_pql(
        client,
        final_project_id,
        state=state,
        assignee=assignee,
        label=label,
        cycle=cycle,
        module=module,
        milestone=milestone,
        priority=priority,
        target_date_before=target_date_before,
        target_date_after=target_date_after,
        pql=final_pql,
    )
    return await _run_plane_call(
        client.list_work_items,
        project_id=final_project_id,
        expand=final_expand,
        cursor=cursor,
        page_size=final_page_size,
        pql=final_work_item_pql,
        fields=final_fields,
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
async def search_work_items(
    query: NonEmptyString,
    project_id: NonEmptyString | None = None,
    cursor: str | None = None,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
    expand: str | None = None,
    fields: str | None = None,
    state: str | None = None,
    assignee: str | None = None,
    label: str | None = None,
    cycle: str | None = None,
    module: str | None = None,
    milestone: str | None = None,
    priority: Priority | None = None,
    target_date_before: str | None = None,
    target_date_after: str | None = None,
    pql: str | None = None,
) -> dict[str, Any]:
    """Search work items by text and optionally narrow them with project-scoped filters."""
    final_query = required_string({"query": query}, "query")
    final_project_id = optional_string({"project_id": project_id}, "project_id")
    final_expand = optional_string({"expand": expand}, "expand")
    final_fields = optional_string({"fields": fields}, "fields")
    final_pql = optional_string({"pql": pql}, "pql")
    final_page_size = validate_page_size(page_size)
    client = _client()
    filter_values = (state, assignee, label, cycle, module, milestone)
    if any(value is not None for value in filter_values) and final_project_id is None:
        raise ValueError("project_id is required when using state, assignee, label, cycle, module, or milestone filters.")
    final_work_item_pql = None
    if final_project_id is not None:
        final_work_item_pql = _work_item_pql(
            client,
            final_project_id,
            state=state,
            assignee=assignee,
            label=label,
            cycle=cycle,
            module=module,
            milestone=milestone,
            priority=priority,
            target_date_before=target_date_before,
            target_date_after=target_date_after,
            pql=final_pql,
        )
    elif any(value is not None for value in (priority, target_date_before, target_date_after, final_pql)):
        final_work_item_pql = build_work_item_pql(
            priority=priority,
            target_date_before=target_date_before,
            target_date_after=target_date_after,
            pql=final_pql,
        )
    return await _run_plane_call(
        client.search_work_items,
        query=final_query,
        project_id=final_project_id,
        cursor=cursor,
        page_size=final_page_size,
        expand=final_expand,
        fields=final_fields,
        pql=final_work_item_pql,
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


@mcp.resource("plane://workspace")
async def workspace_context() -> str:
    """Workspace project context for the configured Plane workspace."""
    payload = await _run_plane_call(_client().list_projects, page_size=MAXIMUM_PAGE_SIZE)
    return json.dumps({"workspace": payload}, ensure_ascii=False, indent=2, sort_keys=True)


@mcp.resource("plane://projects/{project_id}")
async def project_context(project_id: str) -> str:
    """Project context resource addressed by project UUID."""
    final_project_id = required_string({"project_id": project_id}, "project_id")
    payload = await _run_plane_call(_client().get_project, project_id=final_project_id)
    return json.dumps({"project": payload}, ensure_ascii=False, indent=2, sort_keys=True)


@mcp.resource("plane://projects/{project_id}/work-items/{work_item_id}")
async def work_item_context(project_id: str, work_item_id: str) -> str:
    """Work-item context resource addressed by project and work-item UUID."""
    final_project_id = required_string({"project_id": project_id}, "project_id")
    final_work_item_id = required_string({"work_item_id": work_item_id}, "work_item_id")
    payload = await _run_plane_call(
        _client().get_work_item,
        project_id=final_project_id,
        work_item_id=final_work_item_id,
    )
    return json.dumps({"work_item": payload}, ensure_ascii=False, indent=2, sort_keys=True)


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
    "get_project",
    "get_settings",
    "get_work_item",
    "list_module_work_items",
    "list_modules",
    "list_project_resources",
    "list_projects",
    "list_work_item_comments",
    "list_work_items",
    "list_workspace_members",
    "main",
    "mcp",
    "project_context",
    "resolve_project",
    "resolve_project_resource",
    "search_work_items",
    "workspace_context",
    "work_item_context",
    "optional_string",
    "required_string",
    "validate_page_size",
]


if __name__ == "__main__":
    main()
