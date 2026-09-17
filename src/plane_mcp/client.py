from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .config import PlaneSettings


DEFAULT_PAGE_SIZE = 100
MAXIMUM_PAGE_SIZE = 100
SERVER_VERSION = "0.3.0"
USER_AGENT = f"plane-work-items-mcp/{SERVER_VERSION}"
PROJECT_RESOURCE_PATHS = {
    "cycles": "cycles/",
    "labels": "labels/",
    "members": "members/",
    "milestones": "milestones/",
    "modules": "modules/",
    "releases": "releases/",
    "states": "states/",
    "work_item_types": "work-item-types/",
}


class PlaneApiError(RuntimeError):
    """Raised when the Plane API cannot provide a valid response."""


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


def pagination_parameters(cursor: str | None, page_size: int) -> dict[str, Any]:
    if cursor is not None and not isinstance(cursor, str):
        raise ValueError("cursor must be a string.")

    return {
        "cursor": cursor,
        "per_page": validate_page_size(page_size),
    }


RequestOpener = Callable[..., Any]


class PlaneClient:
    """Small, injectable client for the Plane v1 workspace API."""

    def __init__(self, settings: PlaneSettings, opener: RequestOpener = urlopen) -> None:
        self.settings = settings
        self._opener = opener

    def _request(self, final_path: str, final_parameters: dict[str, Any]) -> dict[str, Any]:
        parameters = {key: value for key, value in final_parameters.items() if value is not None}
        query_string = urlencode(parameters, doseq=True)
        workspace_slug = quote(self.settings.workspace_slug, safe="")
        request_url = f"{self.settings.api_v1_url}/workspaces/{workspace_slug}/{final_path.lstrip('/')}"
        request_url = f"{request_url}?{query_string}" if query_string else request_url
        request = Request(
            request_url,
            headers={
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
                "X-API-Key": self.settings.api_key,
            },
            method="GET",
        )

        try:
            with self._opener(request, timeout=self.settings.request_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            response_body = error.read().decode("utf-8", errors="replace").strip()
            response_body = response_body[:2000]
            detail = f": {response_body}" if response_body else "."
            raise PlaneApiError(f"Plane API request failed with HTTP {error.code}{detail}") from error
        except URLError as error:
            raise PlaneApiError(f"Plane API request could not be completed: {error.reason}") from error
        except (TimeoutError, OSError) as error:
            raise PlaneApiError(f"Plane API request could not be completed: {error}") from error
        except json.JSONDecodeError as error:
            raise PlaneApiError("Plane API returned invalid JSON.") from error

        if not isinstance(payload, dict):
            raise PlaneApiError("Plane API returned an unexpected response shape.")

        return payload

    def list_projects(self, cursor: str | None = None, page_size: int = DEFAULT_PAGE_SIZE) -> dict[str, Any]:
        return self._request("projects/", pagination_parameters(cursor, page_size))

    def list_modules(
        self,
        project_id: str,
        cursor: str | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        final_project_id = quote(project_id.strip(), safe="")
        return self._request(f"projects/{final_project_id}/modules/", pagination_parameters(cursor, page_size))

    def list_module_work_items(
        self,
        project_id: str,
        module_id: str,
        cursor: str | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        final_project_id = quote(project_id.strip(), safe="")
        final_module_id = quote(module_id.strip(), safe="")
        return self._request(
            f"projects/{final_project_id}/modules/{final_module_id}/module-issues/",
            pagination_parameters(cursor, page_size),
        )

    def list_work_items(
        self,
        project_id: str,
        expand: str | None = None,
        cursor: str | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        pql: str | None = None,
        fields: str | None = None,
    ) -> dict[str, Any]:
        final_project_id = quote(project_id.strip(), safe="")
        parameters = pagination_parameters(cursor, page_size)
        parameters["expand"] = expand or "module,state,assignees,labels"
        parameters["pql"] = pql
        parameters["fields"] = fields
        return self._request(f"projects/{final_project_id}/work-items/", parameters)

    def list_work_item_comments(
        self,
        project_id: str,
        work_item_id: str,
        cursor: str | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        final_project_id = quote(project_id.strip(), safe="")
        final_work_item_id = quote(work_item_id.strip(), safe="")
        return self._request(
            f"projects/{final_project_id}/work-items/{final_work_item_id}/comments/",
            pagination_parameters(cursor, page_size),
        )

    def get_project(self, project_id: str, expand: str | None = None) -> dict[str, Any]:
        final_project_id = quote(project_id.strip(), safe="")
        return self._request(f"projects/{final_project_id}/", {"expand": expand})

    def get_work_item(
        self,
        project_id: str,
        work_item_id: str,
        expand: str | None = None,
        fields: str | None = None,
    ) -> dict[str, Any]:
        final_project_id = quote(project_id.strip(), safe="")
        final_work_item_id = quote(work_item_id.strip(), safe="")
        return self._request(
            f"projects/{final_project_id}/work-items/{final_work_item_id}/",
            {
                "expand": expand or "module,state,assignees,labels,type,project",
                "fields": fields,
            },
        )

    def search_work_items(
        self,
        query: str,
        project_id: str | None = None,
        cursor: str | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        expand: str | None = None,
        fields: str | None = None,
        pql: str | None = None,
    ) -> dict[str, Any]:
        parameters = pagination_parameters(cursor, page_size)
        parameters.update(
            {
                "search": query,
                "project": project_id,
                "expand": expand or "module,state,assignees,labels,type,project",
                "fields": fields,
                "pql": pql,
            }
        )
        return self._request("work-items/search/", parameters)

    def list_project_resources(
        self,
        project_id: str,
        resource: str,
        cursor: str | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        if resource not in PROJECT_RESOURCE_PATHS:
            supported_resources = ", ".join(sorted(PROJECT_RESOURCE_PATHS))
            raise ValueError(f"resource must be one of: {supported_resources}.")

        final_project_id = quote(project_id.strip(), safe="")
        return self._request(
            f"projects/{final_project_id}/{PROJECT_RESOURCE_PATHS[resource]}",
            pagination_parameters(cursor, page_size),
        )

    def list_workspace_members(
        self,
        cursor: str | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        return self._request("members/", pagination_parameters(cursor, page_size))
