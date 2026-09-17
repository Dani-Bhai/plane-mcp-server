from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from plane_mcp.config import (
    API_KEY_ENVIRONMENT_VARIABLE,
    BASE_URL_ENVIRONMENT_VARIABLE,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    REQUEST_TIMEOUT_ENVIRONMENT_VARIABLE,
    WORKSPACE_SLUG_ENVIRONMENT_VARIABLE,
    PlaneConfigurationError,
    build_api_v1_url,
    get_settings,
)


class ConfigTest(unittest.TestCase):
    def test_build_api_v1_url_normalizes_supported_inputs(self) -> None:
        self.assertEqual("https://plane.example.test/api/v1", build_api_v1_url("https://plane.example.test"))
        self.assertEqual("https://plane.example.test/api/v1", build_api_v1_url("https://plane.example.test/"))
        self.assertEqual("https://plane.example.test/api/v1", build_api_v1_url("https://plane.example.test/api"))
        self.assertEqual("https://plane.example.test/api/v1", build_api_v1_url("https://plane.example.test/api/v1/"))

    def test_build_api_v1_url_rejects_non_http_url(self) -> None:
        with self.assertRaisesRegex(PlaneConfigurationError, "absolute HTTP"):
            build_api_v1_url("plane.example.test")

        with self.assertRaisesRegex(PlaneConfigurationError, "absolute HTTP"):
            build_api_v1_url("file:///tmp/plane")

    def test_get_settings_requires_credentials_and_workspace(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(PlaneConfigurationError, "PLANE_API_KEY, PLANE_BASE_URL, PLANE_WORKSPACE_SLUG"):
                get_settings()

    def test_get_settings_uses_default_timeout(self) -> None:
        environment = {
            API_KEY_ENVIRONMENT_VARIABLE: " key ",
            BASE_URL_ENVIRONMENT_VARIABLE: "https://plane.example.test/api",
            WORKSPACE_SLUG_ENVIRONMENT_VARIABLE: " workspace ",
        }

        with patch.dict(os.environ, environment, clear=True):
            settings = get_settings()

        self.assertEqual("key", settings.api_key)
        self.assertEqual("https://plane.example.test/api/v1", settings.api_v1_url)
        self.assertEqual("workspace", settings.workspace_slug)
        self.assertEqual(DEFAULT_REQUEST_TIMEOUT_SECONDS, settings.request_timeout_seconds)

    def test_get_settings_reads_custom_timeout(self) -> None:
        environment = {
            API_KEY_ENVIRONMENT_VARIABLE: "key",
            BASE_URL_ENVIRONMENT_VARIABLE: "https://plane.example.test",
            WORKSPACE_SLUG_ENVIRONMENT_VARIABLE: "workspace",
            REQUEST_TIMEOUT_ENVIRONMENT_VARIABLE: "2.5",
        }

        with patch.dict(os.environ, environment, clear=True):
            settings = get_settings()

        self.assertEqual(2.5, settings.request_timeout_seconds)

    def test_get_settings_rejects_invalid_timeout(self) -> None:
        base_environment = {
            API_KEY_ENVIRONMENT_VARIABLE: "key",
            BASE_URL_ENVIRONMENT_VARIABLE: "https://plane.example.test",
            WORKSPACE_SLUG_ENVIRONMENT_VARIABLE: "workspace",
        }

        for invalid_timeout in ("not-a-number", "0", "-1", "nan", "inf"):
            with self.subTest(invalid_timeout=invalid_timeout):
                with patch.dict(
                    os.environ,
                    {**base_environment, REQUEST_TIMEOUT_ENVIRONMENT_VARIABLE: invalid_timeout},
                    clear=True,
                ):
                    with self.assertRaisesRegex(PlaneConfigurationError, "positive number"):
                        get_settings()


if __name__ == "__main__":
    unittest.main()
