from __future__ import annotations

import json
import runpy
import unittest
import warnings
from unittest.mock import patch

from mcp import Client

from plane_mcp import server
from plane_mcp.client import PlaneApiError
from plane_mcp.config import PlaneConfigurationError, PlaneSettings


class FakePlaneClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.fail = False
        self.project_payload: dict[str, object] = {
            "results": [
                {"id": "project-1", "identifier": "ENG", "name": "Engineering"},
            ]
        }
        self.resource_payloads: dict[str, dict[str, object]] = {
            "states": {"results": [{"id": "state-done", "name": "Done"}]},
            "labels": {"results": [{"id": "label-bug", "name": "Bug"}]},
        }

    def _record(self, method: str, **kwargs: object) -> dict[str, object]:
        self.calls.append((method, kwargs))
        if self.fail:
            raise PlaneApiError("Plane API is unavailable")
        return {"method": method, "arguments": kwargs}

    def list_projects(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("list_projects", kwargs))
        if self.fail:
            raise PlaneApiError("Plane API is unavailable")
        return self.project_payload if kwargs.get("page_size") == 100 else {"method": "list_projects", "arguments": kwargs}

    def get_project(self, **kwargs: object) -> dict[str, object]:
        return self._record("get_project", **kwargs)

    def list_modules(self, **kwargs: object) -> dict[str, object]:
        return self._record("list_modules", **kwargs)

    def list_project_resources(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("list_project_resources", kwargs))
        if self.fail:
            raise PlaneApiError("Plane API is unavailable")
        resource = str(kwargs.get("resource"))
        return self.resource_payloads.get(resource, {"method": "list_project_resources", "arguments": kwargs})

    def list_workspace_members(self, **kwargs: object) -> dict[str, object]:
        return self._record("list_workspace_members", **kwargs)

    def list_module_work_items(self, **kwargs: object) -> dict[str, object]:
        return self._record("list_module_work_items", **kwargs)

    def get_work_item(self, **kwargs: object) -> dict[str, object]:
        return self._record("get_work_item", **kwargs)

    def list_work_items(self, **kwargs: object) -> dict[str, object]:
        return self._record("list_work_items", **kwargs)

    def search_work_items(self, **kwargs: object) -> dict[str, object]:
        return self._record("search_work_items", **kwargs)

    def list_work_item_comments(self, **kwargs: object) -> dict[str, object]:
        return self._record("list_work_item_comments", **kwargs)


class ServerTest(unittest.IsolatedAsyncioTestCase):
    async def test_native_client_discovers_all_read_only_tools(self) -> None:
        async with Client(server.mcp) as client:
            self.assertEqual(server.SERVER_NAME, client.server_info.name)
            self.assertEqual(server.SERVER_VERSION, client.server_info.version)
            self.assertIsNotNone(client.server_capabilities.tools)
            result = await client.list_tools()

        tools = {tool.name: tool for tool in result.tools}
        self.assertEqual(
            {
                "list_projects",
                "resolve_project",
                "get_project",
                "list_modules",
                "list_project_resources",
                "list_workspace_members",
                "resolve_project_resource",
                "list_module_work_items",
                "get_work_item",
                "list_work_items",
                "search_work_items",
                "list_work_item_comments",
            },
            set(tools),
        )
        self.assertTrue(all(tool.annotations.read_only_hint for tool in tools.values()))
        self.assertTrue(all(tool.annotations.idempotent_hint for tool in tools.values()))
        self.assertTrue(all(tool.annotations.destructive_hint is False for tool in tools.values()))
        self.assertEqual(["project_id"], tools["list_modules"].input_schema["required"])
        self.assertEqual(1, tools["list_projects"].input_schema["properties"]["page_size"]["minimum"])
        self.assertEqual(100, tools["list_projects"].input_schema["properties"]["page_size"]["maximum"])
        self.assertEqual(
            {"urgent", "high", "medium", "low", "none"},
            set(tools["list_work_items"].input_schema["properties"]["priority"]["anyOf"][0]["enum"]),
        )

    async def test_native_client_calls_all_tools_with_structured_results(self) -> None:
        fake_client = FakePlaneClient()
        arguments = {
            "list_projects": {"cursor": "cursor", "page_size": 2},
            "resolve_project": {"query": "ENG"},
            "get_project": {"project_id": "project", "expand": "members"},
            "list_modules": {"project_id": "project", "cursor": "cursor", "page_size": 2},
            "list_project_resources": {
                "project_id": "project",
                "resource": "states",
                "cursor": "cursor",
                "page_size": 2,
            },
            "list_workspace_members": {"cursor": "cursor", "page_size": 2},
            "resolve_project_resource": {"project_id": "project", "resource": "states", "query": "Done"},
            "list_module_work_items": {
                "project_id": "project",
                "module_id": "module",
                "cursor": "cursor",
                "page_size": 2,
            },
            "get_work_item": {"project_id": "project", "work_item_id": "work-item", "fields": "id,name"},
            "list_work_items": {"project_id": "project", "expand": "state", "cursor": "cursor", "page_size": 2},
            "search_work_items": {"query": "release planning", "page_size": 2},
            "list_work_item_comments": {
                "project_id": "project",
                "work_item_id": "work-item",
                "cursor": "cursor",
                "page_size": 2,
            },
        }

        with patch("plane_mcp.server._client", return_value=fake_client):
            async with Client(server.mcp) as client:
                results = [await client.call_tool(name, values) for name, values in arguments.items()]

        self.assertTrue(all(not result.is_error for result in results))
        self.assertEqual(
            [
                "list_projects",
                "list_projects",
                "get_project",
                "list_modules",
                "list_project_resources",
                "list_workspace_members",
                "list_project_resources",
                "list_module_work_items",
                "get_work_item",
                "list_work_items",
                "search_work_items",
                "list_work_item_comments",
            ],
            [call[0] for call in fake_client.calls],
        )
        self.assertEqual("members", fake_client.calls[2][1]["expand"])
        self.assertEqual("state", fake_client.calls[9][1]["expand"])
        self.assertEqual("work-item", fake_client.calls[11][1]["work_item_id"])
        self.assertEqual("list_projects", results[0].structured_content["method"])

    async def test_work_item_filters_resolve_names_and_forward_pql(self) -> None:
        fake_client = FakePlaneClient()

        with patch("plane_mcp.server._client", return_value=fake_client):
            result = await server.list_work_items(
                "project",
                state="Done",
                label="Bug",
                priority="high",
                target_date_after="2026-01-01",
            )

        self.assertEqual("list_work_items", result["method"])
        self.assertEqual(
            'state = "state-done" AND label = "label-bug" AND priority = "high" AND target_date >= "2026-01-01"',
            fake_client.calls[-1][1]["pql"],
        )
        self.assertEqual(
            ["list_project_resources", "list_project_resources", "list_work_items"],
            [call[0] for call in fake_client.calls],
        )

    async def test_search_filters_require_project_for_project_owned_metadata(self) -> None:
        fake_client = FakePlaneClient()

        with patch("plane_mcp.server._client", return_value=fake_client):
            with self.assertRaisesRegex(ValueError, "project_id is required"):
                await server.search_work_items("text", state="Done")

            result = await server.search_work_items("text", priority="urgent", target_date_before="2026-12-31")

        self.assertEqual('priority = "urgent" AND target_date <= "2026-12-31"', fake_client.calls[-1][1]["pql"])
        self.assertEqual("text", result["arguments"]["query"])

    async def test_search_with_project_without_filters_uses_default_pql(self) -> None:
        fake_client = FakePlaneClient()

        with patch("plane_mcp.server._client", return_value=fake_client):
            result = await server.search_work_items("text", project_id="project")

        self.assertEqual("project", result["arguments"]["project_id"])
        self.assertIsNone(result["arguments"]["pql"])

    def test_resolved_item_id_accepts_uuid_and_rejects_missing_identity(self) -> None:
        self.assertEqual(
            "uuid-1",
            server._resolved_item_id({"results": [{"uuid": "uuid-1", "name": "Module"}]}, "Module", "module"),
        )
        with patch("plane_mcp.server.resolve_named_item", return_value={"name": "Module"}):
            with self.assertRaisesRegex(ValueError, "no usable id"):
                server._resolved_item_id({}, "Module", "module")

    async def test_tool_errors_are_returned_as_native_tool_errors(self) -> None:
        fake_client = FakePlaneClient()
        fake_client.fail = True

        with patch("plane_mcp.server._client", return_value=fake_client):
            async with Client(server.mcp) as client:
                result = await client.call_tool("list_projects", {})

        self.assertTrue(result.is_error)
        self.assertIn("Plane API is unavailable", result.content[0].text)

    async def test_configuration_errors_are_returned_as_native_tool_errors(self) -> None:
        with patch("plane_mcp.server._client", side_effect=PlaneConfigurationError("configuration is missing")):
            async with Client(server.mcp) as client:
                result = await client.call_tool("list_projects", {})

        self.assertTrue(result.is_error)
        self.assertIn("configuration is missing", result.content[0].text)

    async def test_resolution_errors_are_safe_and_actionable(self) -> None:
        fake_client = FakePlaneClient()
        fake_client.project_payload = {
            "results": [
                {"id": "project-1", "identifier": "ENG", "name": "Platform"},
                {"id": "project-2", "identifier": "OPS", "name": "Platform"},
            ]
        }

        with patch("plane_mcp.server._client", return_value=fake_client):
            async with Client(server.mcp) as client:
                ambiguous = await client.call_tool("resolve_project", {"query": "Platform"})
                missing = await client.call_tool("resolve_project", {"query": "missing"})

        self.assertTrue(ambiguous.is_error)
        self.assertIn("More than one project matched", ambiguous.content[0].text)
        self.assertTrue(missing.is_error)
        self.assertIn("project-1", missing.content[0].text)

    async def test_native_client_validates_required_and_unknown_tool_inputs(self) -> None:
        async with Client(server.mcp) as client:
            missing_argument = await client.call_tool("list_modules", {})
            invalid_page_size = await client.call_tool("list_projects", {"page_size": 0})
            unknown_tool = await client.call_tool("unknown_tool", {})

        self.assertTrue(missing_argument.is_error)
        self.assertTrue(invalid_page_size.is_error)
        self.assertTrue(unknown_tool.is_error)

    async def test_handlers_reject_invalid_direct_arguments(self) -> None:
        with self.assertRaisesRegex(ValueError, "page_size"):
            await server.list_projects(page_size=0)
        with self.assertRaisesRegex(ValueError, "expand"):
            await server.list_work_items("project", expand=1)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "query"):
            await server.resolve_project(" ")

    def test_client_factory_constructs_plane_client_from_settings(self) -> None:
        settings = PlaneSettings("key", "https://plane.example.test/api/v1", "workspace")

        with patch("plane_mcp.server.get_settings", return_value=settings) as get_settings:
            with patch("plane_mcp.server.PlaneClient") as plane_client:
                result = server._client()

        self.assertIs(result, plane_client.return_value)
        get_settings.assert_called_once_with()
        plane_client.assert_called_once_with(settings)

    async def test_resources_are_discoverable_and_readable(self) -> None:
        fake_client = FakePlaneClient()

        with patch("plane_mcp.server._client", return_value=fake_client):
            async with Client(server.mcp) as client:
                resources = await client.list_resources()
                templates = await client.list_resource_templates()
                workspace = await client.read_resource("plane://workspace")
                project = await server.project_context("project-1")
                work_item = await server.work_item_context("project-1", "item-1")

        self.assertEqual({"plane://workspace"}, {str(resource.uri) for resource in resources.resources})
        self.assertEqual(
            {
                "plane://projects/{project_id}",
                "plane://projects/{project_id}/work-items/{work_item_id}",
            },
            {str(template.uri_template) for template in templates.resource_templates},
        )
        self.assertIn("workspace", json.loads(workspace.contents[0].text))
        self.assertIn("project", json.loads(project))
        self.assertIn("work_item", json.loads(work_item))

    def test_main_runs_stdio_transport(self) -> None:
        with patch.object(server.mcp, "run") as run:
            server.main()

        run.assert_called_once_with(transport="stdio")

    def test_module_entry_point_runs_main(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            with patch("mcp.server.MCPServer.run") as run:
                runpy.run_module("plane_mcp.server", run_name="__main__")

        run.assert_called_once_with(transport="stdio")


if __name__ == "__main__":
    unittest.main()
