from __future__ import annotations

import math
import os
from dataclasses import dataclass
from urllib.parse import urlparse


API_KEY_ENVIRONMENT_VARIABLE = "PLANE_API_KEY"
BASE_URL_ENVIRONMENT_VARIABLE = "PLANE_BASE_URL"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
REQUEST_TIMEOUT_ENVIRONMENT_VARIABLE = "PLANE_REQUEST_TIMEOUT_SECONDS"
WORKSPACE_SLUG_ENVIRONMENT_VARIABLE = "PLANE_WORKSPACE_SLUG"


class PlaneConfigurationError(ValueError):
    """Raised when the Plane MCP configuration is invalid."""


@dataclass(frozen=True)
class PlaneSettings:
    api_key: str
    api_v1_url: str
    workspace_slug: str
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS


def build_api_v1_url(final_base_url: str) -> str:
    normalized_url = final_base_url.rstrip("/")
    parsed_url = urlparse(normalized_url)

    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise PlaneConfigurationError(
            f"{BASE_URL_ENVIRONMENT_VARIABLE} must be an absolute HTTP(S) URL ending in /api or /api/v1."
        )

    if normalized_url.endswith("/api/v1"):
        return normalized_url

    if normalized_url.endswith("/api"):
        return f"{normalized_url}/v1"

    return f"{normalized_url}/api/v1"


def _request_timeout_from_environment() -> float:
    final_timeout = os.environ.get(REQUEST_TIMEOUT_ENVIRONMENT_VARIABLE, "").strip()

    if not final_timeout:
        return DEFAULT_REQUEST_TIMEOUT_SECONDS

    try:
        timeout = float(final_timeout)
    except ValueError as error:
        raise PlaneConfigurationError(
            f"{REQUEST_TIMEOUT_ENVIRONMENT_VARIABLE} must be a positive number of seconds."
        ) from error

    if not math.isfinite(timeout) or timeout <= 0:
        raise PlaneConfigurationError(
            f"{REQUEST_TIMEOUT_ENVIRONMENT_VARIABLE} must be a positive number of seconds."
        )

    return timeout


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
        raise PlaneConfigurationError(f"Missing required environment variable(s): {', '.join(missing_names)}.")

    return PlaneSettings(
        api_key=api_key,
        api_v1_url=build_api_v1_url(base_url),
        workspace_slug=workspace_slug,
        request_timeout_seconds=_request_timeout_from_environment(),
    )
