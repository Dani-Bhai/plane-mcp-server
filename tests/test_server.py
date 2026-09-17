from __future__ import annotations

import unittest

from plane_mcp.server import (
    CURRENT_PROTOCOL_VERSION,
    PlaneApiError,
    build_api_v1_url,
    handle_message,
    validate_page_size,
)


class ServerTest(unittest.TestCase):
    def test_build_api_v1_url_adds_missing_api_segments(self) -> None:
        self.assertEqual("https://plane.example.test/api/v1", build_api_v1_url("https://plane.example.test"))

    def test_build_api_v1_url_preserves_api_path(self) -> None:
        self.assertEqual("https://plane.example.test/api/v1", build_api_v1_url("https://plane.example.test/api"))

    def test_build_api_v1_url_rejects_non_http_url(self) -> None:
        with self.assertRaisesRegex(PlaneApiError, "absolute HTTP"):
            build_api_v1_url("plane.example.test")

    def test_validate_page_size_rejects_invalid_values(self) -> None:
        for page_size in (0, 101, True):
            with self.subTest(page_size=page_size):
                with self.assertRaisesRegex(ValueError, "page_size"):
                    validate_page_size(page_size)

    def test_initialize_supports_legacy_clients(self) -> None:
        response = handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}}
        )

        self.assertEqual("2025-11-25", response["result"]["protocolVersion"])
        self.assertEqual({}, response["result"]["capabilities"]["tools"])

    def test_server_discover_supports_current_clients(self) -> None:
        response = handle_message({"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {}})

        self.assertEqual(CURRENT_PROTOCOL_VERSION, response["result"]["supportedVersions"][0])
        self.assertEqual("complete", response["result"]["resultType"])

    def test_tools_list_is_read_only(self) -> None:
        response = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": CURRENT_PROTOCOL_VERSION}},
            }
        )

        tools = response["result"]["tools"]

        self.assertEqual(5, len(tools))
        self.assertTrue(all(tool["annotations"]["readOnlyHint"] for tool in tools))

    def test_unknown_tool_returns_a_tool_error(self) -> None:
        response = handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "delete_project"}}
        )

        self.assertTrue(response["result"]["isError"])
        self.assertIn("Unknown tool", response["result"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
