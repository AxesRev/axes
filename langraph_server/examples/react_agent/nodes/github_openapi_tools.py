"""GitHub REST tools: one FastMCP tool per OpenAPI operation, discovered through Jev search."""

from __future__ import annotations

import functools
import json
import logging
import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

import httpx
import httpx2
from fastmcp import FastMCP
from fastmcp.experimental.transforms.jev_search import JevSearchTransform
from fastmcp.server.providers.openapi import MCPType, RouteMap
from langchain.mcp import MCPAdapter
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.github_installation_token import get_installation_access_token

logger = logging.getLogger(__name__)

_GITHUB_OPENAPI_SPEC_URL = (
    "https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json"
)
_GITHUB_API_URL = "https://api.github.com"
_READ_ONLY_ROUTE_MAPS = [
    RouteMap(methods=["GET"], mcp_type=MCPType.TOOL),
    RouteMap(mcp_type=MCPType.EXCLUDE),
]

_server_cache: dict[tuple[str, bool], FastMCP] = {}


class _InstallationTokenAuth(httpx2.Auth):
    """Sets a fresh GitHub App installation token on every request."""

    def __init__(self, installation_id: str) -> None:
        self._installation_id = installation_id

    def auth_flow(self, request: httpx2.Request) -> Generator[httpx2.Request, httpx2.Response, None]:
        request.headers["Authorization"] = f"Bearer {get_installation_access_token(self._installation_id)}"
        yield request


@functools.cache
def _openapi_spec() -> dict[str, Any]:
    spec_path = os.environ.get("GITHUB_OPENAPI_SPEC_PATH", "").strip()
    if spec_path:
        return json.loads(Path(spec_path).read_text(encoding="utf-8"))
    response = httpx.get(_GITHUB_OPENAPI_SPEC_URL, timeout=60.0)
    response.raise_for_status()
    return response.json()


def _github_server(installation_id: str, *, include_write: bool) -> FastMCP:
    cache_key = (installation_id, include_write)
    cached = _server_cache.get(cache_key)
    if cached is not None:
        return cached

    client = httpx2.AsyncClient(
        base_url=_GITHUB_API_URL,
        headers={
            "X-GitHub-Api-Version": os.environ.get("GITHUB_API_VERSION", "2022-11-28").strip(),
            "Accept": "application/vnd.github+json",
        },
        auth=_InstallationTokenAuth(installation_id),
        timeout=30.0,
    )
    server = FastMCP.from_openapi(
        openapi_spec=_openapi_spec(),
        client=client,
        name="github",
        route_maps=None if include_write else _READ_ONLY_ROUTE_MAPS,
    )
    server.add_transform(
        JevSearchTransform(
            api_key=os.environ["JEV_API_KEY"],
            search_tool_name="search_github_api",
            call_tool_name="call_github_api",
        )
    )
    _server_cache[cache_key] = server
    logger.info(
        "github_openapi_server: initialized (installation_id=%s, include_write=%s)", installation_id, include_write
    )
    return server


async def build_github_api_tools(
    runtime: Runtime[Context],
    *,
    include_read: bool,
    include_write: bool,
) -> list[Any]:
    """Jev search plus call tools over the GitHub REST API (GET-only unless ``include_write``)."""
    if not include_read and not include_write:
        return []
    installation_id = runtime.context.github_installation_id.strip()
    if not installation_id:
        msg = "github_installation_id is required for GitHub API tools"
        raise ValueError(msg)
    return await MCPAdapter(_github_server(installation_id, include_write=include_write)).list_tools()
