from __future__ import annotations

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

    def _record(self, method: str, **kwargs: object) -> dict[str, object]:
        self.calls.append((method, kwargs))
        if self.fail:
            raise PlaneApiError("Plane API is unavailable")
        return {"method": method, "arguments": kwargs}

    def list_projects(self, **kwargs: object) -> dict[str, object]:
        return self._record("list_projects", **kwargs)

    def list_modules(self, **kwargs: object) -> dict[str, object]:
        return self._record("list_modules", **kwargs)

    def list_module_work_items(self, **kwargs: object) -> dict[str, object]:
        return self._record("list_module_work_items", **kwargs)

    def list_work_items(self, **kwargs: object) -> dict[str, object]:
        return self._record("list_work_items", **kwargs)

    def list_work_item_comments(self, **kwargs: object) -> dict[str, object]:
        return self._record("list_work_item_comments", **kwargs)


class ServerTest(unittest.IsolatedAsyncioTestCase):
    async def test_native_client_discovers_five_read_only_tools(self) -> None:
        async with Client(server.mcp) as client:
            self.assertEqual(server.SERVER_NAME, client.server_info.name)
            self.assertEqual(server.SERVER_VERSION, client.server_info.version)
            self.assertIsNotNone(client.server_capabilities.tools)
            result = await client.list_tools()

        tools = {tool.name: tool for tool in result.tools}
        self.assertEqual(
            {
                "list_projects",
                "list_modules",
                "list_module_work_items",
                "list_work_items",
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

    async def test_native_client_calls_all_tools_with_structured_results(self) -> None:
        fake_client = FakePlaneClient()
        arguments = {
            "list_projects": {"cursor": "cursor", "page_size": 2},
            "list_modules": {"project_id": "project", "cursor": "cursor", "page_size": 2},
            "list_module_work_items": {
                "project_id": "project",
                "module_id": "module",
                "cursor": "cursor",
                "page_size": 2,
            },
            "list_work_items": {
                "project_id": "project",
                "expand": "state",
                "cursor": "cursor",
                "page_size": 2,
            },
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
        self.assertEqual(list(arguments), [call[0] for call in fake_client.calls])
        self.assertEqual("project", fake_client.calls[1][1]["project_id"])
        self.assertEqual("state", fake_client.calls[3][1]["expand"])
        self.assertEqual("work-item", fake_client.calls[4][1]["work_item_id"])
        self.assertEqual("list_projects", results[0].structured_content["method"])

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

    def test_client_factory_constructs_plane_client_from_settings(self) -> None:
        settings = PlaneSettings("key", "https://plane.example.test/api/v1", "workspace")

        with patch("plane_mcp.server.get_settings", return_value=settings) as get_settings:
            with patch("plane_mcp.server.PlaneClient") as plane_client:
                result = server._client()

        self.assertIs(result, plane_client.return_value)
        get_settings.assert_called_once_with()
        plane_client.assert_called_once_with(settings)

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
