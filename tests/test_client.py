from __future__ import annotations

import io
import json
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

from plane_mcp.client import (
    DEFAULT_PAGE_SIZE,
    MAXIMUM_PAGE_SIZE,
    PlaneApiError,
    PlaneClient,
    optional_string,
    pagination_parameters,
    required_string,
    validate_page_size,
)
from plane_mcp.config import PlaneSettings


class FakeResponse:
    def __init__(self, payload: object) -> None:
        if isinstance(payload, bytes):
            self.body = payload
        else:
            self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class RecordingOpener:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.requests: list[tuple[object, float]] = []

    def __call__(self, request: object, *, timeout: float) -> FakeResponse:
        self.requests.append((request, timeout))
        return FakeResponse(self.payload)


def settings() -> PlaneSettings:
    return PlaneSettings(
        api_key="test-key",
        api_v1_url="https://plane.example.test/api/v1",
        workspace_slug="workspace/one",
        request_timeout_seconds=4.5,
    )


class ClientTest(unittest.TestCase):
    def test_validation_helpers(self) -> None:
        self.assertEqual(1, validate_page_size(1))
        self.assertEqual(MAXIMUM_PAGE_SIZE, validate_page_size(MAXIMUM_PAGE_SIZE))
        self.assertEqual("value", required_string({"name": " value "}, "name"))
        self.assertIsNone(optional_string({}, "expand"))
        self.assertEqual("value", optional_string({"expand": "value"}, "expand"))
        self.assertEqual({"cursor": "next", "per_page": 2}, pagination_parameters("next", 2))

        for invalid_page_size in (0, MAXIMUM_PAGE_SIZE + 1, True, "2"):
            with self.subTest(invalid_page_size=invalid_page_size):
                with self.assertRaisesRegex(ValueError, "page_size"):
                    validate_page_size(invalid_page_size)

        with self.assertRaisesRegex(ValueError, "name"):
            required_string({"name": " "}, "name")
        with self.assertRaisesRegex(ValueError, "name"):
            required_string({}, "name")
        with self.assertRaisesRegex(ValueError, "expand"):
            optional_string({"expand": 1}, "expand")
        with self.assertRaisesRegex(ValueError, "cursor"):
            pagination_parameters(1, DEFAULT_PAGE_SIZE)

    def test_list_projects_builds_authenticated_paginated_request(self) -> None:
        opener = RecordingOpener({"results": [{"id": "project-1"}], "next_cursor": None})
        client = PlaneClient(settings(), opener=opener)

        result = client.list_projects(cursor="next token", page_size=2)

        self.assertEqual({"results": [{"id": "project-1"}], "next_cursor": None}, result)
        request, timeout = opener.requests[0]
        parsed_url = urlparse(request.full_url)
        self.assertEqual(
            "/api/v1/workspaces/workspace%2Fone/projects/",
            parsed_url.path,
        )
        self.assertEqual({"cursor": ["next token"], "per_page": ["2"]}, parse_qs(parsed_url.query))
        self.assertEqual("test-key", request.get_header("X-api-key"))
        self.assertEqual("application/json", request.get_header("Accept"))
        self.assertEqual("plane-work-items-mcp/0.3.0", request.get_header("User-agent"))
        self.assertEqual("GET", request.get_method())
        self.assertEqual(4.5, timeout)

    def test_all_plane_list_methods_use_expected_paths(self) -> None:
        opener = RecordingOpener({"results": []})
        client = PlaneClient(settings(), opener=opener)

        client.list_modules("project/1", cursor="c", page_size=3)
        client.list_module_work_items("project/1", "module 1", cursor="c", page_size=3)
        client.list_work_items("project/1", cursor="c", page_size=3)
        client.list_work_items("project/1", expand="state", cursor="c", page_size=3)
        client.list_work_item_comments("project/1", "work-item/1", cursor="c", page_size=3)

        paths = [urlparse(request.full_url).path for request, _ in opener.requests]
        self.assertEqual(
            [
                "/api/v1/workspaces/workspace%2Fone/projects/project%2F1/modules/",
                "/api/v1/workspaces/workspace%2Fone/projects/project%2F1/modules/module%201/module-issues/",
                "/api/v1/workspaces/workspace%2Fone/projects/project%2F1/work-items/",
                "/api/v1/workspaces/workspace%2Fone/projects/project%2F1/work-items/",
                "/api/v1/workspaces/workspace%2Fone/projects/project%2F1/work-items/work-item%2F1/comments/",
            ],
            paths,
        )
        self.assertEqual(
            {"cursor": ["c"], "per_page": ["3"], "expand": ["module,state,assignees,labels"]},
            parse_qs(urlparse(opener.requests[2][0].full_url).query),
        )
        self.assertEqual(
            {"cursor": ["c"], "per_page": ["3"], "expand": ["state"]},
            parse_qs(urlparse(opener.requests[3][0].full_url).query),
        )

    def test_request_rejects_invalid_response_shapes(self) -> None:
        for payload, message in (
            (["not", "an", "object"], "unexpected response shape"),
            (b"not-json", "invalid JSON"),
        ):
            with self.subTest(payload=payload):
                client = PlaneClient(settings(), opener=RecordingOpener(payload))
                with self.assertRaisesRegex(PlaneApiError, message):
                    client.list_projects()

    def test_request_translates_http_and_network_errors(self) -> None:
        error_with_body = HTTPError(
            "https://plane.example.test",
            503,
            "Unavailable",
            {},
            io.BytesIO(b'{"detail":"down"}'),
        )
        error_without_body = HTTPError("https://plane.example.test", 404, "Not found", {}, io.BytesIO(b""))

        for error, expected in (
            (error_with_body, 'HTTP 503: {"detail":"down"}'),
            (error_without_body, "HTTP 404."),
            (URLError("connection refused"), "could not be completed: connection refused"),
            (TimeoutError("timed out"), "could not be completed: timed out"),
            (OSError("socket closed"), "could not be completed: socket closed"),
        ):
            with self.subTest(error=type(error).__name__):

                def opener(*_: object, **__: object) -> None:
                    raise error

                with self.assertRaisesRegex(PlaneApiError, expected):
                    PlaneClient(settings(), opener=opener).list_projects()

    def test_v03_read_methods_build_expected_requests(self) -> None:
        opener = RecordingOpener({"results": []})
        client = PlaneClient(settings(), opener=opener)

        client.get_project("project/1", expand="members")
        client.get_work_item("project/1", "work-item/1", fields="id,name")
        client.search_work_items(
            "release planning",
            project_id="project/1",
            cursor="next",
            page_size=4,
            pql='priority = "urgent"',
        )
        client.list_project_resources("project/1", "states", cursor="next", page_size=4)
        client.list_workspace_members(cursor="next", page_size=4)

        paths = [urlparse(request.full_url).path for request, _ in opener.requests]
        self.assertEqual(
            [
                "/api/v1/workspaces/workspace%2Fone/projects/project%2F1/",
                "/api/v1/workspaces/workspace%2Fone/projects/project%2F1/work-items/work-item%2F1/",
                "/api/v1/workspaces/workspace%2Fone/work-items/search/",
                "/api/v1/workspaces/workspace%2Fone/projects/project%2F1/states/",
                "/api/v1/workspaces/workspace%2Fone/members/",
            ],
            paths,
        )
        self.assertEqual(
            {"expand": ["members"]},
            parse_qs(urlparse(opener.requests[0][0].full_url).query),
        )
        self.assertEqual(
            {
                "expand": ["module,state,assignees,labels,type,project"],
                "fields": ["id,name"],
            },
            parse_qs(urlparse(opener.requests[1][0].full_url).query),
        )
        self.assertEqual(
            {
                "cursor": ["next"],
                "per_page": ["4"],
                "search": ["release planning"],
                "project": ["project/1"],
                "expand": ["module,state,assignees,labels,type,project"],
                "pql": ['priority = "urgent"'],
            },
            parse_qs(urlparse(opener.requests[2][0].full_url).query),
        )

    def test_work_item_filters_are_forwarded_and_project_resources_are_validated(self) -> None:
        opener = RecordingOpener({"results": []})
        client = PlaneClient(settings(), opener=opener)

        client.list_work_items("project/1", pql='priority = "urgent"', fields="id,name")

        self.assertEqual(
            {
                "per_page": ["100"],
                "expand": ["module,state,assignees,labels"],
                "pql": ['priority = "urgent"'],
                "fields": ["id,name"],
            },
            parse_qs(urlparse(opener.requests[0][0].full_url).query),
        )

        with self.assertRaisesRegex(ValueError, "resource must be one of"):
            client.list_project_resources("project/1", "unknown")

    def test_all_project_resource_names_map_to_explicit_plane_paths(self) -> None:
        opener = RecordingOpener({"results": []})
        client = PlaneClient(settings(), opener=opener)
        resources = {
            "cycles": "cycles",
            "labels": "labels",
            "members": "members",
            "milestones": "milestones",
            "modules": "modules",
            "releases": "releases",
            "states": "states",
            "work_item_types": "work-item-types",
        }

        for resource in resources:
            client.list_project_resources("project/1", resource)

        self.assertEqual(
            [
                f"/api/v1/workspaces/workspace%2Fone/projects/project%2F1/{path}/"
                for path in resources.values()
            ],
            [urlparse(request.full_url).path for request, _ in opener.requests],
        )


if __name__ == "__main__":
    unittest.main()
