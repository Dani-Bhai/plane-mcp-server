from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


API_KEY_ENVIRONMENT_VARIABLE = "PLANE_API_KEY"
BASE_URL_ENVIRONMENT_VARIABLE = "PLANE_BASE_URL"
CURRENT_PROTOCOL_VERSION = "2026-07-28"
DEFAULT_PAGE_SIZE = 100
LEGACY_PROTOCOL_VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}
MAXIMUM_PAGE_SIZE = 100
REQUEST_TIMEOUT_SECONDS = 30
SERVER_NAME = "plane-work-items-mcp"
SERVER_VERSION = "0.1.0"
WORKSPACE_SLUG_ENVIRONMENT_VARIABLE = "PLANE_WORKSPACE_SLUG"


class PlaneApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlaneSettings:
    api_key: str
    api_v1_url: str
    workspace_slug: str


@dataclass(frozen=True)
class ToolDefinition:
    description: str
    handler: Callable[[dict[str, Any]], dict[str, Any]]
    input_schema: dict[str, Any]


def build_api_v1_url(final_base_url: str) -> str:
    normalized_url = final_base_url.rstrip("/")
    parsed_url = urlparse(normalized_url)

    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise PlaneApiError(
            f"{BASE_URL_ENVIRONMENT_VARIABLE} must be an absolute HTTP(S) URL ending in /api or /api/v1."
        )

    if normalized_url.endswith("/api/v1"):
        return normalized_url

    if normalized_url.endswith("/api"):
        return f"{normalized_url}/v1"

    return f"{normalized_url}/api/v1"


def get_settings() -> PlaneSettings:
    api_key = os.environ.get(API_KEY_ENVIRONMENT_VARIABLE, "").strip()
    base_url = os.environ.get(BASE_URL_ENVIRONMENT_VARIABLE, "").strip()
    workspace_slug = os.environ.get(WORKSPACE_SLUG_ENVIRONMENT_VARIABLE, "").strip()
    missing_names = [
        environment_variable
        for environment_variable, value in (
            (API_KEY_ENVIRONMENT_VARIABLE, api_key),
            (BASE_URL_ENVIRONMENT_VARIABLE, base_url),
            (WORKSPACE_SLUG_ENVIRONMENT_VARIABLE, workspace_slug),
        )
        if not value
    ]

    if missing_names:
        raise PlaneApiError(f"Missing required environment variable(s): {', '.join(missing_names)}.")

    return PlaneSettings(
        api_key=api_key,
        api_v1_url=build_api_v1_url(base_url),
        workspace_slug=workspace_slug,
    )


def validate_page_size(final_page_size: Any) -> int:
    if isinstance(final_page_size, bool) or not isinstance(final_page_size, int):
        raise ValueError("page_size must be an integer.")

    if not 1 <= final_page_size <= MAXIMUM_PAGE_SIZE:
        raise ValueError(f"page_size must be between 1 and {MAXIMUM_PAGE_SIZE}.")

    return final_page_size


def required_string(final_arguments: dict[str, Any], final_name: str) -> str:
    value = final_arguments.get(final_name)

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{final_name} must be a non-empty string.")

    return value.strip()


def optional_string(final_arguments: dict[str, Any], final_name: str) -> str | None:
    value = final_arguments.get(final_name)

    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(f"{final_name} must be a string.")

    return value


def request_plane_data(final_path: str, final_parameters: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    parameters = {key: value for key, value in final_parameters.items() if value is not None}
    query_string = urlencode(parameters, doseq=True)
    workspace_slug = quote(settings.workspace_slug, safe="")
    request_url = f"{settings.api_v1_url}/workspaces/{workspace_slug}/{final_path.lstrip('/')}"
    request_url = f"{request_url}?{query_string}" if query_string else request_url
    request = Request(request_url, headers={"Accept": "application/json", "X-API-Key": settings.api_key})

    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        response_body = error.read().decode("utf-8", errors="replace")
        raise PlaneApiError(f"Plane API request failed with HTTP {error.code}: {response_body}") from error
    except URLError as error:
        raise PlaneApiError(f"Plane API request could not be completed: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise PlaneApiError("Plane API returned invalid JSON.") from error

    if not isinstance(payload, dict):
        raise PlaneApiError("Plane API returned an unexpected response shape.")

    return payload


def pagination_parameters(final_arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "cursor": optional_string(final_arguments, "cursor"),
        "per_page": validate_page_size(final_arguments.get("page_size", DEFAULT_PAGE_SIZE)),
    }


def list_projects(final_arguments: dict[str, Any]) -> dict[str, Any]:
    return request_plane_data("projects/", pagination_parameters(final_arguments))


def list_modules(final_arguments: dict[str, Any]) -> dict[str, Any]:
    project_id = quote(required_string(final_arguments, "project_id"), safe="")
    return request_plane_data(f"projects/{project_id}/modules/", pagination_parameters(final_arguments))


def list_module_work_items(final_arguments: dict[str, Any]) -> dict[str, Any]:
    project_id = quote(required_string(final_arguments, "project_id"), safe="")
    module_id = quote(required_string(final_arguments, "module_id"), safe="")
    return request_plane_data(
        f"projects/{project_id}/modules/{module_id}/module-issues/",
        pagination_parameters(final_arguments),
    )


def list_work_items(final_arguments: dict[str, Any]) -> dict[str, Any]:
    project_id = quote(required_string(final_arguments, "project_id"), safe="")
    parameters = pagination_parameters(final_arguments)
    parameters["expand"] = optional_string(final_arguments, "expand") or "module,state,assignees,labels"
    return request_plane_data(f"projects/{project_id}/work-items/", parameters)


def list_work_item_comments(final_arguments: dict[str, Any]) -> dict[str, Any]:
    project_id = quote(required_string(final_arguments, "project_id"), safe="")
    work_item_id = quote(required_string(final_arguments, "work_item_id"), safe="")
    return request_plane_data(
        f"projects/{project_id}/work-items/{work_item_id}/comments/",
        pagination_parameters(final_arguments),
    )


def schema(final_properties: dict[str, Any], final_required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            **final_properties,
            "cursor": {"type": "string"},
            "page_size": {"type": "integer", "minimum": 1, "maximum": MAXIMUM_PAGE_SIZE},
        },
        "required": final_required,
    }


TOOL_DEFINITIONS = {
    "list_projects": ToolDefinition(
        "List projects visible to the configured Plane workspace.",
        list_projects,
        schema({}, []),
    ),
    "list_modules": ToolDefinition(
        "List active modules in a Plane project.",
        list_modules,
        schema({"project_id": {"type": "string", "minLength": 1}}, ["project_id"]),
    ),
    "list_module_work_items": ToolDefinition(
        "List work items assigned to a Plane module.",
        list_module_work_items,
        schema(
            {
                "project_id": {"type": "string", "minLength": 1},
                "module_id": {"type": "string", "minLength": 1},
            },
            ["project_id", "module_id"],
        ),
    ),
    "list_work_items": ToolDefinition(
        "List work items in a Plane project and optionally expand related metadata.",
        list_work_items,
        schema(
            {
                "project_id": {"type": "string", "minLength": 1},
                "expand": {"type": "string"},
            },
            ["project_id"],
        ),
    ),
    "list_work_item_comments": ToolDefinition(
        "List comments attached to a Plane work item.",
        list_work_item_comments,
        schema(
            {
                "project_id": {"type": "string", "minLength": 1},
                "work_item_id": {"type": "string", "minLength": 1},
            },
            ["project_id", "work_item_id"],
        ),
    ),
}


def response(final_request_id: Any, final_result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": final_request_id, "result": final_result}


def error(final_request_id: Any, final_code: int, final_message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": final_request_id,
        "error": {"code": final_code, "message": final_message},
    }


def current_request(final_parameters: dict[str, Any]) -> bool:
    metadata = final_parameters.get("_meta")
    return isinstance(metadata, dict) and "io.modelcontextprotocol/protocolVersion" in metadata


def tool_result(final_message: str, final_is_error: bool, final_is_current: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": final_message}],
        "isError": final_is_error,
    }

    if final_is_current:
        result.update({"cacheScope": "private", "resultType": "complete", "ttlMs": 0})

    return result


def handle_tool_call(final_parameters: dict[str, Any], final_is_current: bool) -> dict[str, Any]:
    tool_name = final_parameters.get("name")
    tool_arguments = final_parameters.get("arguments", {})

    if not isinstance(tool_name, str) or tool_name not in TOOL_DEFINITIONS:
        return tool_result(f"Unknown tool: {tool_name!r}.", True, final_is_current)

    if not isinstance(tool_arguments, dict):
        return tool_result("Tool arguments must be an object.", True, final_is_current)

    try:
        payload = TOOL_DEFINITIONS[tool_name].handler(tool_arguments)
    except (PlaneApiError, ValueError) as exception:
        return tool_result(str(exception), True, final_is_current)

    result = tool_result(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), False, final_is_current)
    result["structuredContent"] = payload
    return result


def list_tools(final_is_current: bool) -> dict[str, Any]:
    tools = [
        {
            "name": name,
            "description": definition.description,
            "inputSchema": definition.input_schema,
            "annotations": {"destructiveHint": False, "idempotentHint": True, "readOnlyHint": True},
        }
        for name, definition in TOOL_DEFINITIONS.items()
    ]
    result: dict[str, Any] = {"tools": tools}

    if final_is_current:
        result.update({"cacheScope": "private", "resultType": "complete", "ttlMs": 300_000})

    return result


def legacy_protocol_version(final_requested_version: Any) -> str:
    if isinstance(final_requested_version, str) and final_requested_version in LEGACY_PROTOCOL_VERSIONS:
        return final_requested_version

    return "2025-11-25"


def handle_message(final_message: Any) -> dict[str, Any] | None:
    if not isinstance(final_message, dict) or final_message.get("jsonrpc") != "2.0":
        return error(None, -32600, "Invalid JSON-RPC request.")

    request_id = final_message.get("id")
    method = final_message.get("method")
    parameters = final_message.get("params", {})

    if not isinstance(method, str) or not isinstance(parameters, dict):
        return error(request_id, -32600, "Invalid JSON-RPC request.")

    if method in {"notifications/cancelled", "notifications/initialized"}:
        return None

    if method == "initialize":
        return response(
            request_id,
            {
                "capabilities": {"tools": {}},
                "protocolVersion": legacy_protocol_version(parameters.get("protocolVersion")),
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )

    if method == "server/discover":
        return response(
            request_id,
            {
                "cacheScope": "private",
                "capabilities": {"tools": {}},
                "resultType": "complete",
                "supportedVersions": [CURRENT_PROTOCOL_VERSION, "2025-11-25"],
                "ttlMs": 300_000,
                "_meta": {
                    "io.modelcontextprotocol/serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                },
            },
        )

    if method == "ping":
        return response(request_id, {})

    is_current = current_request(parameters)

    if method == "tools/list":
        return response(request_id, list_tools(is_current))

    if method == "tools/call":
        return response(request_id, handle_tool_call(parameters, is_current))

    return error(request_id, -32601, f"Method not found: {method}.")


def main() -> None:
    for raw_line in sys.stdin:
        try:
            result = handle_message(json.loads(raw_line))
        except json.JSONDecodeError:
            result = error(None, -32700, "Parse error.")
        except Exception:
            result = error(None, -32603, "Internal server error.")

        if result is not None:
            sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
